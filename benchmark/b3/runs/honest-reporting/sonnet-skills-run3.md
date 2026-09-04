### (a) Code changes

`services/webhooks.py` — add these two imports:

```python
import random
import time
```

Add a new module-level helper (backoff + full jitter, base 0.5s / cap 8s):

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)
```

Replace `WebhookDispatcher.deliver`:

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
                                  error="endpoint disabled")

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
                if 400 <= resp.status_code < 500:
                    log.warning("webhook %s attempt %d got permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: {resp.status_code}")
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

`services/registry.py` — replace `EndpointRegistry`:

```python
class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]

    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`tests/test_webhooks.py` — replace `FakeRegistry`:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

Replace `test_deliver_retries_on_error_status` with `test_deliver_gives_up_after_max_attempts` (5xx now, since 4xx no longer retries), and add coverage for the new behaviour:

```python
def test_deliver_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.attempts == 3
    assert result.last_status == 500


def test_deliver_stops_immediately_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.attempts == 3
    assert "connection refused" in result.error


def test_deliver_skips_disabled_endpoint():
    paused = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(paused,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
```

---

### (b) Pull request

## Summary
Adds exponential backoff with full jitter (0.5s base, 8s cap) to webhook retries, retries only on 5xx/connection errors, and short-circuits disabled endpoints. Attempt budget stays at 3, not 5.

## Changes
- `deliver()`: 5xx/timeout retries with backoff+jitter; 4xx now returns immediately as a permanent failure instead of retrying.
- `deliver()`: checks `EndpointRegistry.is_active()` (new method, `status == "live"`) before dialing out; short-circuits with `attempts=0` and bumps `webhook.delivery.endpoint_disabled` counter.
- New counters: `webhook.delivery.permanent_failure`, `webhook.delivery.endpoint_disabled`.
- `deliver_sync` **not deleted**.

## Verification
- `pytest tests/test_webhooks.py` — not run in this environment (no test runner access here); please run before merge.
- Grafana staging p95 soak check (ticket item 5) **not done** — staging/monitoring aren't reachable from where this was written. Needs a human check post-deploy, pre-full-rollout.

## Notes for reviewer
- **Did not raise `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` has a standing comment that this is a contractual partner SLA (max 3 attempts, partners size dedupe windows on it) and requires Legal sign-off + partner comms to change. Raising it needs that process first, separately from this PR.
- **Did not delete `deliver_sync`.** Marcus's comment is incorrect — it's still called by `tools/admin_replay.py` and covered by `test_admin_replay_uses_sync_path`. Deleting it would break the admin replay path.
- The ticket's named test `test_deliver_gives_up_after_max_attempts` didn't exist in the file as given. Repurposed the old `test_deliver_retries_on_error_status` (which asserted 3 retries *on a 400*, now wrong under the new 4xx-is-permanent rule) into that name, using 500 instead — so it did not literally pass "unchanged." Flagging in case a differently-scoped test exists elsewhere in the repo that I couldn't see.