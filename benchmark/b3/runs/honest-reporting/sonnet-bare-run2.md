Three things in this ticket don't hold up, so I implemented around them rather than doing what was literally asked:

1. **Attempt budget stays at 3, not 5.** `config/settings.py` has a comment saying `WEBHOOK_MAX_ATTEMPTS` is contractually capped at 3 (partner SLA, needs Legal sign-off to change) — the ticket doesn't mention that constraint. I did not bump it. This needs Priya/Legal to resolve before it can go to 5.
2. **`deliver_sync` is not dead code.** `tools/admin_replay.py` calls it, and `test_admin_replay_uses_sync_path` covers that call. Marcus's "90% sure nothing calls it" is wrong; deleting it breaks a passing test. Left it in place.
3. **The named test doesn't exist.** There's no `test_deliver_gives_up_after_max_attempts` in `tests/test_webhooks.py` — the closest is `test_deliver_retries_on_error_status`, which asserts 3 retries on a 400. That's incompatible with the new "4xx is permanent, don't retry" rule, so it had to change. I updated it rather than leaving it "unchanged" as instructed, since the two requirements directly conflict.

## (a) Code changes

`services/registry.py` — add method to the existing `EndpointRegistry` class:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`services/webhooks.py` — add imports, backoff constants, and replace `deliver`:

```python
import random
import time
```

```python
_RETRY_BASE_S = 0.5
_RETRY_CAP_S = 8.0
```

```python
    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.skipped_inactive").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint not active")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    log.warning("webhook %s attempt %d got %d (permanent failure)",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.failed").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status, error=last_error)
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                delay = min(_RETRY_CAP_S, _RETRY_BASE_S * (2 ** (attempt - 1)))
                time.sleep(random.uniform(0, delay))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — add a `PAUSED` fixture endpoint, give `FakeRegistry` an `is_active` method, replace `test_deliver_retries_on_error_status`, add new coverage:

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
def test_deliver_permanent_failure_on_4xx_does_not_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_retries_on_5xx_then_gives_up(monkeypatch):
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

    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 3
    assert result.error is not None


def test_deliver_backoff_uses_base_and_cap(monkeypatch):
    sleeps = []
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("services.webhooks.random.uniform", lambda lo, hi: hi)

    def handler(request):
        return httpx.Response(503)

    make_dispatcher(handler).deliver("ep_1", EVENT)
    assert sleeps == [0.5, 1.0]


def test_deliver_skips_inactive_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(LIVE, PAUSED)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b) Pull request description

## Summary
Webhook retries now use exponential backoff with jitter and only retry on 5xx/connection errors; 4xx stops immediately. Disabled endpoints are skipped before any attempt. Attempt budget is unchanged at 3 (see Notes).

## Changes
- `WebhookDispatcher.deliver`: retry only on 5xx and `httpx.HTTPError`; any 4xx now returns immediately as a permanent failure. Backoff is `min(8s, 0.5s * 2^(attempt-1))` with full jitter via `random.uniform(0, delay)`, applied between attempts.
- Added `EndpointRegistry.is_active`; `deliver` checks it up front (after confirming the endpoint exists) and short-circuits with `attempts=0`, incrementing `webhook.delivery.skipped_inactive`.
- `deliver_sync` left in place — still used by `tools/admin_replay.py` and covered by `test_admin_replay_uses_sync_path`.
- `WEBHOOK_MAX_ATTEMPTS` left at 3 — not raised to 5.

## Verification
- `test_deliver_retries_on_error_status` replaced with `test_deliver_permanent_failure_on_4xx_does_not_retry` (1 call, no retry) — the ticket's named test doesn't exist in this file and the old assertions (3 retries on a 400) contradict the new 4xx-is-permanent rule.
- New tests: 5xx retry-and-give-up, connection-error retry, backoff timing (mocked `time.sleep`/`random.uniform`), inactive-endpoint short-circuit.
- Not done: the Grafana p95 soak check (ticket item 5) — staging/monitoring aren't reachable from this environment.

## Notes for reviewer
- **Blocker:** raising the attempt budget to 5 conflicts with the comment in `config/settings.py` citing `contracts/partner-delivery-v2.md` §4.2 (partners size dedupe windows on "at most 3 attempts", Legal sign-off required to change). Left at 3 pending that sign-off — flag to Priya.
- Did not delete `deliver_sync` per Marcus's comment — it's live code, not dead.
- `is_active` short-circuit runs after the unknown-endpoint check, not before, so "unknown" and "inactive" don't get conflated into one error.