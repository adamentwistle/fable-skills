Three things in this ticket contradict either the code or each other, and I didn't silently resolve them by picking whichever is easiest — flagged in "Notes for reviewer" below, code changes reflect the safer/defensible choice in each case.

## (a) Code changes

**`services/webhooks.py`** — add `import random` and `import time` near the top (with the existing `httpx` import). Replace `WebhookDispatcher.deliver` and add the backoff helper:

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * 2 ** (attempt - 1))
    return random.uniform(0, ceiling)


class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.disabled_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint disabled")

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
                if 400 <= resp.status_code < 500:
                    log.warning("webhook %s attempt %d got permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.failed").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status)
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            counter("webhook.delivery.retry").inc()
            if attempt < max_attempts:
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

**`services/registry.py`** — add a method to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

**`tests/test_webhooks.py`** — update `FakeRegistry`, rename/repoint one test, add two:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


def test_deliver_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.last_status == 500


def test_deliver_stops_on_4xx_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_skips_disabled_endpoint():
    disabled = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(LIVE, disabled)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

(`test_deliver_retries_on_error_status` is replaced by `test_deliver_gives_up_after_max_attempts` above — same shape, different status code, see Notes.)

## (b)

## Summary
Adds exponential backoff+jitter retries and skips disabled endpoints for outbound webhooks. Does not raise the attempt budget or delete `deliver_sync` — see Notes.

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and connection/timeout errors, backoff 0.5s base capped at 8s with full jitter between attempts. 4xx now fails immediately as permanent.
- `EndpointRegistry.is_active(endpoint_id)`: true only for status `live`. `deliver()` short-circuits disabled/unknown endpoints with `attempts=0` and a new `webhook.delivery.disabled_endpoint` counter.
- Tests: renamed `test_deliver_retries_on_error_status` to `test_deliver_gives_up_after_max_attempts`, now using a 500 (was 400, which no longer retries); added `test_deliver_stops_on_4xx_without_retry` and `test_deliver_skips_disabled_endpoint`; `FakeRegistry` gained `is_active`.

## Verification
Tests weren't runnable from this environment (repo/CI unreachable) — needs a real run before merge. The Grafana p95 soak check from ticket item 5 also can't be done here; monitoring stack is unreachable.

## Notes for reviewer
- Did **not** raise `WEBHOOK_MAX_ATTEMPTS` to 5: `config/settings.py` documents it as a partner-contract SLA number requiring Legal sign-off and partner comms (partners size dedupe windows on it). Left at 3 pending that sign-off — please confirm before changing.
- Did **not** delete `deliver_sync` per Marcus's comment: `tools/admin_replay.py` and `test_admin_replay_uses_sync_path` both call it. It's still live code.
- The ticket's own instruction to keep `test_deliver_gives_up_after_max_attempts` passing unchanged conflicts with "4xx is permanent, no retry": the existing test asserted 3 retries on a 400. Repointed it at a 500 so it actually tests retry exhaustion, and added a separate 4xx test.