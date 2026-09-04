Two ticket items are not in this PR: the attempt-budget raise (settings comment binds it to a partner contract, needs Legal sign-off) and the deletion of `deliver_sync` (it is still called). Details in Notes for reviewer.

## (a) Code changes

`config/settings.py` — add two constants (`WEBHOOK_MAX_ATTEMPTS` left at 3):

```python
# Exponential backoff between delivery attempts, with full jitter.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` — add to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should receive events.

        'live' is the sole delivering state: 'pending' has not acknowledged the
        verification ping, 'paused' was switched off by the customer, and
        'revoked' was disabled by us and cannot be resumed.
        """
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`services/webhooks.py` — new imports `import random`, `import time`; replace `WebhookDispatcher.__init__` and `deliver`, and add `_backoff_delay`:

```python
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def _backoff_delay(self, attempt: int) -> float:
        """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**(attempt-1)))."""
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
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped: endpoint status %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    # 4xx (and any other non-5xx) is the partner telling us the request
                    # itself is wrong. Retrying cannot fix it, so record and stop.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got permanent %d",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.TransportError as exc:
                # Connection refused, DNS failure, read/write timeout: worth retrying.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d unrecoverable: %s", endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — replace `FakeRegistry`, `make_dispatcher`, and `test_deliver_retries_on_error_status`; add the fixtures and tests below. New import: `from config import settings`.

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")


def make_dispatcher(handler, endpoints=(LIVE,), sleep=lambda _delay: None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport), sleep=sleep)


def test_deliver_stops_on_4xx_without_retrying():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503


def test_deliver_retries_transport_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < settings.WEBHOOK_MAX_ATTEMPTS:
            raise httpx.ConnectTimeout("partner is down", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS


def test_backoff_delays_are_jittered_and_capped():
    delays = []
    make_dispatcher(lambda request: httpx.Response(503), sleep=delays.append).deliver("ep_1", EVENT)

    assert len(delays) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for i, delay in enumerate(delays, start=1):
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (i - 1)))
        assert 0.0 <= delay <= window


def test_deliver_skips_inactive_endpoints():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    dispatcher = make_dispatcher(handler, endpoints=(LIVE, PAUSED, REVOKED, PENDING))
    for endpoint_id in ("ep_paused", "ep_revoked", "ep_pending"):
        result = dispatcher.deliver(endpoint_id, EVENT)
        assert not result.ok
        assert result.attempts == 0
        assert result.last_status is None
    assert calls == []
```

## (b) Pull request

## Summary
Outbound webhook retries now back off exponentially with full jitter instead of hammering a partner that is already failing, and only retry when a retry could plausibly help. Delivery to non-live endpoints is dropped before any network call. Two ticket items are deliberately not done — see Notes.

## Changes
- `WebhookDispatcher.deliver` sleeps `uniform(0, min(8s, 0.5s * 2**(n-1)))` between attempts. No sleep after the final attempt.
- Retries are limited to 5xx responses and `httpx.TransportError` (connection failures, timeouts). Any non-5xx, non-2xx response returns immediately with `ok=False` and the observed status; other `httpx.HTTPError` subclasses are also permanent.
- New `EndpointRegistry.is_active`: true only for status `live`. `deliver` short-circuits inactive endpoints with `attempts=0` and increments `webhook.delivery.skipped_inactive`.
- New counter `webhook.delivery.permanent_failure`; `webhook.delivery.retry` now only fires when a retry actually follows (previously it also fired after the last attempt, inflating the rate by 1/attempt).
- `WebhookDispatcher` takes an injectable `sleep` so tests do not wait on real backoff.
- Settings: added `WEBHOOK_BACKOFF_BASE_S = 0.5`, `WEBHOOK_BACKOFF_CAP_S = 8.0`.
- Tests: fake registry gained `is_active`; added coverage for 4xx-stops-immediately, give-up-after-max-attempts on 503, transport-error retry, backoff bounds, and skipping paused/revoked/pending endpoints.

## Verification
Not run. I have no access to the repository, CI, staging, or Grafana from where this was written, so nothing below has been executed — please run it before merge.
- `pytest tests/test_webhooks.py` — expected to pass; the backoff test asserts bounds rather than exact values because the jitter is random.
- Ticket item 5 (one-hour staging soak, p95 delivery latency for live endpoints unmoved on the webhook-delivery board) is **not done**. It is the main pre-merge gate: backoff adds seconds of wall-clock to a synchronous call, so watch worker saturation as well as p95.
- Worth checking by hand: how many of your live endpoints are actually `pending`. Item 3 says "disabled", and I read `live` as the only delivering state, which also stops delivery to unverified `pending` endpoints. If any real traffic goes to `pending` today, this drops it — `webhook.delivery.skipped_inactive` will show the volume.

## Notes for reviewer
- **Attempt budget left at 3.** `config/settings.py` states the value is a partner SLA commitment (`contracts/partner-delivery-v2.md` 4.2, at most three attempts) requiring Legal sign-off and partner comms, because partners size dedupe windows on it. Raising it to 5 would also widen duplicate bursts, which is the problem this ticket exists to fix. It is a one-line change once signed off; the code and tests read the setting, so no other edit is needed.
- **`deliver_sync` kept.** It is still used: `tools/admin_replay.replay_event` calls it, covered by `test_admin_replay_uses_sync_path`. Deleting it breaks admin replay. Marcus, worth a separate ticket to port replay onto the dispatcher first.
- `tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts` did not exist in the file I was given, so "must still pass unchanged" could not be honoured literally. I added a test of that name using 503. If a test by that name exists elsewhere and asserts retries on 4xx, it will now fail — that conflict is intended by item 1, but flag it if you find one.
- `test_deliver_retries_on_error_status` was replaced: it asserted three attempts against a 400, which item 1 forbids.
- `deliver` now reads the store twice for an active endpoint (`get`, then `is_active`). Kept for the `is_active` API the ticket asked for and to preserve the distinct `unknown_endpoint` counter; collapse it if that lookup is expensive.