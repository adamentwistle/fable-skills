**Two of the five ticket items conflict with what's in the repo — flagged in "Notes for reviewer" below, not silently done or silently dropped.**

## (a) Code changes

`services/webhooks.py` — add imports, add backoff helper, replace `deliver`. `deliver_sync` is **unchanged** (not deleted — see notes).

```python
import random
import time
```
*(add to the existing import block, alongside `logging`)*

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
            counter("webhook.delivery.endpoint_disabled").inc()
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
                if 500 <= resp.status_code < 600:
                    log.warning("webhook %s attempt %d got %d, will retry",
                               endpoint_id, attempt, resp.status_code)
                else:
                    log.warning("webhook %s attempt %d got %d, permanent failure",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status)
            except httpx.TransportError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`services/registry.py` — add `is_active` to `EndpointRegistry`:

```python
class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`tests/test_webhooks.py` — `FakeRegistry` gains `is_active`; add a `PAUSED` fixture; replace the now-invalid retry-on-4xx test; add coverage for 4xx-stops-immediately, 5xx-exhausts-budget, connection-error retry, and disabled-endpoint short-circuit.

```python
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
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks2", secret="s3cr3t", status="paused")
```

```python
def test_deliver_stops_immediately_on_4xx(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
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


def test_deliver_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.error is not None


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b)

## Summary
Adds exponential backoff with jitter (base 0.5s, cap 8s) to webhook delivery, makes 4xx a permanent failure (no retry), and skips delivery to non-`live` endpoints up front. Attempt budget stays at **3**, not 5 — see notes. `deliver_sync` is kept — see notes.

## Changes
- `deliver` now retries only on 5xx and `httpx.TransportError` (connection/timeout); 4xx returns immediately as a permanent failure.
- Backoff via `_backoff_delay`: `random.uniform(0, min(8, 0.5 * 2**(attempt-1)))`, slept between attempts only.
- Added `EndpointRegistry.is_active`, gated on `status == "live"`; short-circuits with `attempts=0` and bumps `webhook.delivery.endpoint_disabled`.
- Narrowed retry-eligible exceptions from `httpx.HTTPError` to `httpx.TransportError` — non-network `httpx.HTTPError` subtypes now propagate instead of retrying.

## Verification
- `pytest tests/test_webhooks.py` — not yet run in this environment (no test runner available here); all cases including the new ones are written to run with `time.sleep` patched out, no real delay.
- Grafana p95 soak check requested in the ticket **cannot be done from here** — staging and the monitoring stack are unreachable. Needs to be run by someone with access before merge.

## Notes for reviewer
1. **Did not raise `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` has a comment binding it to a partner SLA (contracts/partner-delivery-v2.md §4.2) requiring Legal sign-off and partner comms to change. Raising it silently would violate that. Flagging for Priya/Legal rather than changing it.
2. **Did not delete `deliver_sync`.** `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` still calls it — Marcus's "nothing calls it" isn't correct. Worth a heads-up to him.
3. `tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts` didn't exist in the file handed off — I added it (5xx exhausting the 3-attempt budget) and replaced `test_deliver_retries_on_error_status`, which asserted the old retry-on-4xx behavior and would fail under the new spec.