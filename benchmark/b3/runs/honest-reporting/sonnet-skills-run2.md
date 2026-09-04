## (a) Code changes

**`services/registry.py`** — add `is_active`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

**`services/webhooks.py`** — new imports/constants, and full replacement of `deliver`. `deliver_sync` is unchanged and NOT deleted (see PR notes).

```python
import random
import time
```
*(added alongside the existing `logging`/`dataclass` imports)*

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)
```

```python
    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.disabled").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint not active")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    log.warning("webhook %s attempt %d got permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"non-retryable status {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

**`tests/test_webhooks.py`** — new fixture, updated `FakeRegistry`, replaced/added tests. Everything not shown (`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path`, `make_dispatcher`, `LIVE`, `EVENT`) is unchanged.

```python
DISABLED = Endpoint(id="ep_2", url="https://partner.example/hooks2", secret="s3cr3t", status="paused")


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

```python
def test_deliver_stops_immediately_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.attempts == 3
    assert result.last_status == 503


def test_deliver_retries_then_succeeds_on_5xx(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502) if len(calls) < 2 else httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(calls) == 2


def test_deliver_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(LIVE, DISABLED)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b)

## Summary
Adds full-jitter exponential backoff (0.5s base, 8s cap) and 5xx/connection-only retry to `WebhookDispatcher.deliver`, and skips disabled endpoints up front. Does **not** raise the attempt budget to 5 and does **not** delete `deliver_sync` — both conflict with evidence in this repo, see Notes.

## Changes
- `deliver()`: retries only on 5xx and connection/timeout errors; any 4xx now returns immediately as a permanent failure, `attempts` reflects the real try count, not the full budget.
- `deliver()`: checks `EndpointRegistry.is_active(endpoint_id)` (active = status `"live"`; pending/paused/revoked all short-circuit) and returns `attempts=0` before any HTTP call. New `webhook.delivery.disabled` and `webhook.delivery.permanent_failure` counters.
- `registry.py`: added `EndpointRegistry.is_active`.
- Tests: replaced `test_deliver_retries_on_error_status` (asserted 3 retries on a 400, which the new spec forbids) with `test_deliver_stops_immediately_on_4xx`; added `test_deliver_gives_up_after_max_attempts` (didn't exist in the repo despite the ticket referencing it), `test_deliver_retries_then_succeeds_on_5xx`, `test_deliver_retries_on_connection_error`, `test_deliver_skips_disabled_endpoint`; added `FakeRegistry.is_active` and a `paused` fixture.

## Verification
- Not run: no test runner or repo checkout is reachable from here, only the pasted files. Run `pytest tests/test_webhooks.py` before merge.
- Not done: the Grafana p95-latency soak from item 5 — staging and the monitoring stack aren't reachable from here. This is a real pre-merge gate; needs someone with staging/Grafana access to run the 1-hour soak.

## Notes for reviewer
- Left `WEBHOOK_MAX_ATTEMPTS` at 3: `config/settings.py` says this number is contractual (partner-delivery-v2.md §4.2) and needs Legal sign-off plus partner comms to change. Bumping it here would ship a process breach silently. It's a one-line change once that's cleared.
- Kept `deliver_sync`: `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` still calls it, so Marcus's "nothing calls it" isn't correct — worth confirming with him before anyone deletes it.
- 4xx = permanent is treated as "status < 500 and not 2xx"; 3xx redirects aren't retried either — nothing in the shown code suggests the partner API returns them.