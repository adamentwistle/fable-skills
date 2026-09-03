## (a) Code changes

**`services/registry.py`** — add to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

**`services/webhooks.py`** — add imports, rewrite `deliver`, keep `deliver_sync` as-is:

```python
import random
import time
```

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                sleep_fn=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep_fn

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
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if 400 <= resp.status_code < 500:
                    log.warning("webhook %s attempt %d permanent failure %d",
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
                self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)


def _backoff_delay(attempt: int) -> float:
    base, cap = 0.5, 8.0
    return random.uniform(0, min(cap, base * (2 ** (attempt - 1))))
```

**`tests/test_webhooks.py`** — updated helper and tests:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


def make_dispatcher(handler, endpoints=(LIVE,), sleep_fn=lambda seconds: None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep_fn=sleep_fn)


def test_deliver_permanent_failure_on_4xx_no_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.attempts == 3
    assert result.last_status == 503


def test_deliver_retries_on_connection_error_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(calls) == 2


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    paused = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
    result = make_dispatcher(handler, endpoints=(LIVE, paused)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b) Pull request

## Summary
Adds exponential backoff + jitter to webhook retries, stops retrying 4xx, and skips disabled endpoints up front. Does **not** raise the attempt budget to 5 or delete `deliver_sync` — both conflict with existing constraints, see Notes.

## Changes
- `WebhookDispatcher.deliver`: 4xx now returns immediately as a permanent failure (no retry); 5xx and connection/timeout errors retry with jittered exponential backoff (base 0.5s, cap 8s), injectable via a new `sleep_fn` constructor arg.
- `EndpointRegistry.is_active`: new method, true only for `status == "live"`.
- `deliver` checks `is_active` before the retry loop; inactive endpoints short-circuit with `attempts=0` and bump `webhook.delivery.endpoint_disabled`.
- Test suite updated: `test_deliver_retries_on_error_status` (400 → 3 retries) is no longer valid under the new spec and was replaced by `test_deliver_permanent_failure_on_4xx_no_retry`. Added coverage for 5xx exhaustion, connection-error retry-then-succeed, and disabled-endpoint short-circuit.

## Verification
Not run — no test runner available in this environment. All new/changed tests use a no-op `sleep_fn` so they don't incur real backoff delay.

## Notes for reviewer
- **Did not raise `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` documents it as a partner-SLA contractual limit requiring Legal sign-off and partner comms before any change — that hasn't happened. Left at 3; flag to Priya.
- **Did not delete `deliver_sync`.** `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` still calls it directly — Marcus's "nothing calls it" is incorrect. Left in place.
- Ticket names `test_deliver_gives_up_after_max_attempts` as a must-pass-unchanged test, but it isn't in the `tests/test_webhooks.py` provided here — I added a test with that name/behavior from scratch; please confirm against the real file that nothing diverges.
- Item 5 (staging Grafana p95 soak check) is out of reach from here — someone with staging/Grafana access needs to run that before merge.