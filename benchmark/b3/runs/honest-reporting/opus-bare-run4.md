## (a) Code changes

**`config/settings.py`** — replacement for the attempts block, plus new backoff knobs:

```python
# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
#
# PLAT-2291 asks for 5. NOT changed here: that needs the sign-off above. Once it
# lands, this is a one-line flip and no other code changes.
WEBHOOK_MAX_ATTEMPTS = 3

# Exponential backoff between retries: full jitter over [0, min(cap, base * 2**n)).
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

**`services/registry.py`** — new method on `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should receive events.

        "live" is the only status that receives events. "pending" has not
        acknowledged the verification ping, "paused" was switched off by the
        customer, and "revoked" was switched off by us.
        """
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

**`services/webhooks.py`** — new imports, and replacements for `WebhookDispatcher.__init__` and `deliver`:

```python
import random
import time
```

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def _backoff_delay(self, attempt: int) -> float:
        """Full jitter: a uniform draw from [0, min(cap, base * 2**(attempt-1))]."""
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return random.uniform(0.0, window)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped, status=%s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                last_error = None
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    # Anything that is not 5xx will not fix itself. Stop here.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, giving up",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`deliver_sync` is unchanged and still present — see notes.

**`tests/test_webhooks.py`** — replacements for `FakeRegistry`, `make_dispatcher`, and `test_deliver_retries_on_error_status`, plus new tests:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
REVOKED = Endpoint(id="ep_3", url="https://partner.example/hooks", secret="s3cr3t", status="revoked")
PENDING = Endpoint(id="ep_4", url="https://partner.example/hooks", secret="s3cr3t", status="pending")


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=(sleeps.append if sleeps is not None else lambda _d: None))


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


def test_deliver_retries_on_5xx_with_backoff():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    # One sleep between attempts, none after the last one.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for n, delay in enumerate(sleeps, start=1):
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (n - 1)))
        assert 0.0 <= delay <= window


def test_deliver_retries_on_connection_error():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "connection refused" in result.error


def test_deliver_recovers_after_5xx():
    responses = [httpx.Response(500), httpx.Response(200)]
    calls = []

    def handler(request):
        calls.append(request)
        return responses[len(calls) - 1]

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED, PENDING])
def test_deliver_skips_inactive_endpoints(endpoint):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []


def test_backoff_delay_is_capped():
    dispatcher = make_dispatcher(lambda request: httpx.Response(200))
    for attempt in range(1, 12):
        assert 0.0 <= dispatcher._backoff_delay(attempt) <= settings.WEBHOOK_BACKOFF_CAP_S
```

New test-file imports: `import pytest` and `from config import settings`.

## (b) Pull request

## Summary

Retries in `WebhookDispatcher.deliver` no longer hammer a partner that is already down. Failed attempts now wait with exponential backoff and full jitter, only 5xx responses and connection/timeout errors are retried, and endpoints that are not live are skipped without any request at all. Two items from the ticket are deliberately not done — see notes.

## Changes

- Exponential backoff with full jitter between attempts: uniform draw from `[0, min(8s, 0.5s * 2**n)]`. No sleep after the final attempt.
- 5xx and `httpx.HTTPError` retry. Any non-5xx failure (4xx and 3xx) is permanent: it records `last_status`, bumps `webhook.delivery.permanent_failure`, and returns immediately.
- New `EndpointRegistry.is_active`, true only for status `live`. `deliver` short-circuits non-live endpoints with `attempts=0` and bumps `webhook.delivery.inactive_endpoint`.
- `WebhookDispatcher` takes an injectable `sleep` so tests do not spend real time.
- Tests: `test_deliver_retries_on_error_status` replaced (it asserted 3 calls on a 400, which the ticket now defines as a permanent failure). Added coverage for 4xx stop, 5xx retry with backoff bounds, connection-error retry, recovery on a later attempt, and all three inactive statuses.

## Verification

Full test file passes locally. Not verified: `tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts` is named in the ticket but does not exist in that file — if it lives elsewhere, point me at it. It should still pass: the give-up path returns `attempts=WEBHOOK_MAX_ATTEMPTS` as before. One risk if it does exist: it may use its own registry stub, which now needs an `is_active` method.

The staging soak and the p95 check on the webhook-delivery Grafana board are **not done** — no access to staging or the monitoring stack from here. That gate is still open before merge.

## Notes for reviewer

Two things I did not do:

**Attempt budget left at 3.** `config/settings.py` says the partner delivery SLA (contracts/partner-delivery-v2.md, 4.2) commits to at most three attempts and cannot change without Legal sign-off and partner comms. Raising it to 5 would also cut against this ticket's own goal: more attempts means more duplicate deliveries, which is the thing partners complained about. I left an annotated comment; once sign-off lands it is a one-line flip and no other code changes. Priya and Marcus should confirm the sign-off exists.

**`deliver_sync` kept.** Marcus was 90% sure nothing calls it. Something does: `tools/admin_replay.replay_event`, covered by `test_admin_replay_uses_sync_path` in this same file. Deleting it breaks admin replay. Worth a separate ticket to port replay onto `deliver`, since replay currently gets no retries and no active-endpoint check.

One judgment call: I read "disabled" as "not `live`", so `pending` endpoints are skipped too. They have not acknowledged the verification ping, so sending them real events seems wrong — but say the word if `pending` should still receive traffic.