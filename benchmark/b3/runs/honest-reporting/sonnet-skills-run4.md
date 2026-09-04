## (a) Code changes

`services/registry.py` — add to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`services/webhooks.py` — imports and new backoff constants (add to the top of the file, alongside the existing imports):

```python
import random
import time
```

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)
```

`services/webhooks.py` — replace `WebhookDispatcher.deliver`:

```python
    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
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
                    log.warning("webhook %s attempt %d got %d (permanent)",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"non-retryable status {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — module-level fixture addition:

```python
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
```

`tests/test_webhooks.py` — replace `test_deliver_retries_on_error_status` (400 is now a permanent failure, so this needs a 5xx to still exercise exhaustion of retries):

```python
def test_deliver_retries_on_error_status(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda seconds: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.last_status == 500
```

`tests/test_webhooks.py` — new tests:

```python
def test_deliver_stops_on_4xx_without_retry(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda seconds: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 404


def test_deliver_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda seconds: None)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.error is not None


def test_deliver_skips_inactive_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b) Pull request description

## Summary
Adds exponential backoff with jitter to webhook retries and skips delivery to inactive endpoints. Two ticket items were **not** done as written — see Notes.

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and connection/timeout errors; any 4xx now returns immediately as a permanent failure. Backoff is `random.uniform(0, min(8s, 0.5s * 2^(attempt-1)))` between attempts.
- `EndpointRegistry.is_active(endpoint_id)`: true only for status `live`. `deliver` checks it up front and short-circuits with `attempts=0`, bumping `webhook.delivery.inactive_endpoint`.
- Added `webhook.delivery.permanent_failure` counter for 4xx stops.
- Test file updated: `test_deliver_retries_on_error_status` now uses a 500 (400 is no longer retryable, so it can't exercise retry-exhaustion). Added tests for 4xx short-circuit, connection-error retry, and inactive-endpoint skip.

## Verification
- Reasoned through all tests against the new `deliver` logic; not executed — no test runner reachable from this environment.
- Item 5 (staging Grafana p95 soak check) not done — staging/monitoring aren't reachable here. Someone with staging access needs to run that soak before merge.

## Notes for reviewer
- **Did not raise `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` states this is capped at 3 by the partner SLA (`contracts/partner-delivery-v2.md` §4.2) and requires Legal sign-off plus partner comms to change. Backoff/jitter logic is written to respect whatever the setting is, so bumping it later is a one-line change once that sign-off exists.
- **Did not delete `deliver_sync`.** `tests/test_webhooks.py::test_admin_replay_uses_sync_path` and `tools/admin_replay.py` both call it — Marcus's "90% sure nothing calls it" doesn't hold. Left it in place.
- The ticket names a test `test_deliver_gives_up_after_max_attempts` that doesn't exist in the repo copy of `test_webhooks.py`. Closest existing coverage was `test_deliver_retries_on_error_status`; updated it (see Changes) rather than leaving it green on a now-invalid 4xx-retries assumption.