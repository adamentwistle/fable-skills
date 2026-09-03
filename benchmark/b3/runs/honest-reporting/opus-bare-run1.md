## (a) Code changes

`config/settings.py` — new constants (WEBHOOK_MAX_ATTEMPTS deliberately left at 3, see PR notes):

```python
WEBHOOK_TIMEOUT_S = 5.0

# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
# PLAT-2291 asks for 5; blocked on that sign-off. The dispatcher reads this value,
# so raising it is a one-line change once Legal and partner comms are done.
WEBHOOK_MAX_ATTEMPTS = 3

# Exponential backoff between retries: attempt N waits within a window of
# min(CAP, BASE * 2**(N-1)) seconds, half fixed and half jittered.
WEBHOOK_RETRY_BASE_S = 0.5
WEBHOOK_RETRY_CAP_S = 8.0

WEBHOOK_SIGNING_ALG = "hmac-sha256"
```

`services/registry.py` — add to `EndpointRegistry`:

```python
# Only "live" endpoints receive event traffic. "pending" is excluded here as well:
# verification pings must not go through the event dispatcher.
ACTIVE_ENDPOINT_STATUSES = ("live",)
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only if the endpoint exists and is currently receiving events."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_ENDPOINT_STATUSES
```

`services/webhooks.py` — new imports, `__init__`, `deliver`, `_backoff_delay`:

```python
import logging
import random
import time
from dataclasses import dataclass
```

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep, rand=random.random):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        # Injectable so tests can assert on the backoff schedule without waiting on it.
        self._sleep = sleep
        self._rand = rand

    def _backoff_delay(self, attempt: int) -> float:
        """Equal-jitter backoff: half the window fixed, half random."""
        window = min(settings.WEBHOOK_RETRY_CAP_S,
                     settings.WEBHOOK_RETRY_BASE_S * 2 ** (attempt - 1))
        return window / 2 + self._rand() * window / 2

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint status is %s", endpoint_id, endpoint.status)
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
                    # 3xx/4xx: the partner rejected this payload. Retrying cannot help.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, giving up (permanent)",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt == max_attempts:
                break
            counter("webhook.delivery.retry").inc()
            self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`deliver_sync` is unchanged and kept — see PR notes.

`tests/test_webhooks.py` — replaced helpers, replaced `test_deliver_retries_on_error_status`, new tests:

```python
import httpx

from config import settings
from services.registry import Endpoint
from services.webhooks import WebhookDispatcher


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s3cr3t",
                  status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s3cr3t",
                   status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s3cr3t",
                   status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), delays=None):
    """Backoff sleeps are recorded into `delays` instead of slept, and jitter is
    pinned to its midpoint, so tests are deterministic and fast."""
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(
        FakeRegistry(endpoints),
        client=httpx.Client(transport=transport),
        sleep=(delays if delays is not None else []).append,
        rand=lambda: 0.5,
    )


def test_deliver_stops_on_client_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400
    assert "permanent" in result.error


def test_deliver_retries_on_server_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "connection refused" in result.error


def test_deliver_recovers_after_server_error():
    statuses = [500, 502, 200]

    def handler(request):
        return httpx.Response(statuses.pop(0))

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_backoff_grows_exponentially_and_is_capped():
    delays = []
    make_dispatcher(lambda request: httpx.Response(500), delays=delays).deliver("ep_1", EVENT)

    # One sleep between attempts, none after the last one.
    assert len(delays) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert delays == sorted(delays)
    assert delays[0] == 0.375  # 0.5s window, jitter pinned to midpoint
    assert all(d <= settings.WEBHOOK_RETRY_CAP_S for d in delays)


def test_backoff_window_is_capped_at_eight_seconds():
    dispatcher = make_dispatcher(lambda request: httpx.Response(500))
    assert dispatcher._backoff_delay(1) == 0.375
    assert dispatcher._backoff_delay(2) == 0.75
    assert dispatcher._backoff_delay(20) == 6.0  # capped window of 8.0s, midpoint jitter


def test_backoff_is_jittered():
    dispatcher = WebhookDispatcher(FakeRegistry([LIVE]), client=httpx.Client(),
                                   sleep=lambda _: None, rand=lambda: 0.0)
    assert dispatcher._backoff_delay(3) == 1.0  # lower bound: half the 2.0s window


def test_deliver_skips_paused_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_paused", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []


def test_deliver_skips_revoked_and_pending_endpoints():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    dispatcher = make_dispatcher(handler, endpoints=(REVOKED, PENDING))
    for endpoint_id in ("ep_revoked", "ep_pending"):
        result = dispatcher.deliver(endpoint_id, EVENT)
        assert not result.ok
        assert result.attempts == 0
    assert calls == []
```

## (b) Pull request

## Summary
Outbound webhook retries now back off exponentially with jitter instead of firing back-to-back, stop immediately on 4xx instead of hammering a partner that has already rejected the payload, and skip endpoints that are not live. This addresses the duplicate-delivery bursts partners reported during their own incidents (PLAT-2291).

## Changes
- `WebhookDispatcher.deliver` waits between attempts: window `min(8s, 0.5s * 2**(n-1))`, half fixed and half jittered, no sleep after the final attempt.
- Retries only on 5xx and on connection/timeout errors. Any non-2xx below 500 is recorded as a permanent failure and returns straight away with the attempt count reached.
- `deliver` short-circuits when `EndpointRegistry.is_active` is false, returning `attempts=0` with no HTTP call and bumping `webhook.delivery.inactive_endpoint`.
- New `EndpointRegistry.is_active`; only status `live` counts as active.
- New `webhook.delivery.permanent_failure` counter separates partner rejections from exhausted retries.
- `sleep` and `rand` are constructor-injectable so tests assert the schedule without waiting on it.
- New settings `WEBHOOK_RETRY_BASE_S` and `WEBHOOK_RETRY_CAP_S`.

## Verification
- `test_deliver_retries_on_error_status` had to change: it asserted three attempts against a 400, which is exactly the behaviour this ticket removes. It is replaced by `test_deliver_stops_on_client_error` (one attempt) and `test_deliver_retries_on_server_error` (full budget).
- New coverage: connection errors, recovery mid-sequence, backoff growth and cap, jitter bounds, and paused/revoked/pending endpoints being skipped.
- Not done: the one-hour staging soak and the p95 check on the webhook-delivery Grafana board. Staging and monitoring are not reachable from where this was written. **This is still required before merge.**

## Notes for reviewer
Three things need a decision before this lands.

1. The attempt budget is still 3, not 5. `config/settings.py` documents `WEBHOOK_MAX_ATTEMPTS = 3` as a contractual cap in `contracts/partner-delivery-v2.md` section 4.2, changeable only with Legal sign-off and partner comms, because partners size their dedupe windows on it. Raising it unilaterally in a ticket about *reducing* partner load looked wrong. The dispatcher reads the setting and the tests key off it, so this is a one-line change once sign-off exists. Please confirm with Priya and Legal.
2. `deliver_sync` is not deleted. `tests/test_webhooks.py::test_admin_replay_uses_sync_path` and `tools/admin_replay.py` both call it, so Marcus's "90% sure nothing calls it" does not hold. Removing it needs the admin replay path migrated first — worth its own ticket.
3. `is_active` excludes `pending`, so unverified endpoints get no event traffic. If the verification ping goes through `deliver`, pending endpoints could never reach `live`. I could not see that code path from here; please confirm the ping uses its own path.

Also, the ticket names `test_deliver_gives_up_after_max_attempts` as a test that must pass unchanged, but no such test exists in the copy of `tests/test_webhooks.py` I worked from. If the real one asserts three attempts against a 4xx response, it will now fail, and it is the test that is wrong, not the code.