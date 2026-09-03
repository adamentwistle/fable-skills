Three things in the ticket can't be done as written, so I did the rest and left them out:

- **Attempt budget stays at 3.** `config/settings.py` marks `WEBHOOK_MAX_ATTEMPTS` as a contractual cap (partner-delivery-v2 §4.2) needing Legal sign-off. Raising it to 5 is a one-line change once someone has that; I won't make it silently.
- **`deliver_sync` stays.** `test_admin_replay_uses_sync_path` shows `tools.admin_replay.replay_event` calls it. Marcus's 90% was the wrong 90%.
- **The Grafana soak is not done.** No staging or monitoring access from here. Still an open pre-merge gate.

Also: `test_deliver_gives_up_after_max_attempts` does not exist in `tests/test_webhooks.py` — I wrote it. The nearest existing test, `test_deliver_retries_on_error_status`, asserts 400 is retried three times, which directly contradicts scope item 1; I changed it.

## (a) Code changes

`config/settings.py`:

```python
WEBHOOK_TIMEOUT_S = 5.0

# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
#
# PLAT-2291 asks for 5. Blocked on Legal sign-off + partner comms; the dispatcher
# reads this value, so bumping it here is the only change needed once approved.
WEBHOOK_MAX_ATTEMPTS = 3

WEBHOOK_SIGNING_ALG = "hmac-sha256"
```

`services/registry.py` — add to `EndpointRegistry`, plus a module-level constant:

```python
# Only "live" endpoints receive events. "pending" has not acknowledged the
# verification ping, "paused" was switched off by the customer, and "revoked" was
# switched off by us and cannot be resumed.
ACTIVE_STATUSES = ("live",)
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

`services/webhooks.py` — new imports, backoff helper, and replacement `WebhookDispatcher`:

```python
import logging
import random
import time
from dataclasses import dataclass
```

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**(attempt-1))).

    Full jitter rather than a fixed ramp so that a fleet of dispatchers retrying a
    partner that just came back up does not re-converge into a synchronised burst.
    """
    window = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0.0, window)


class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped: endpoint is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

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
                    # Anything below 5xx is the partner telling us this request will
                    # never succeed. Retrying is pure duplicate traffic.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
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
```

`tests/test_webhooks.py` — replaced helpers, one replaced test, four new tests:

```python
import httpx
import pytest

from config import settings
from services.registry import Endpoint
from services.webhooks import WebhookDispatcher, _backoff_delay


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
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), delays=None):
    """Build a dispatcher over a mock transport, recording backoff sleeps into `delays`."""
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=(delays.append if delays is not None else lambda _s: None))
```

```python
def test_deliver_does_not_retry_on_4xx():
    """A 4xx is the partner rejecting the request; one attempt, then stop.

    Replaces test_deliver_retries_on_error_status, which asserted the old behaviour
    of retrying a 400 three times (PLAT-2291, scope item 1).
    """
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


def test_deliver_retries_on_connection_error_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("partner is down", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


def test_deliver_sleeps_between_retries_but_not_after_the_last():
    delays = []
    make_dispatcher(lambda request: httpx.Response(500), delays=delays).deliver("ep_1", EVENT)
    assert len(delays) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert all(d > 0 for d in delays)


@pytest.mark.parametrize("attempt", range(1, 9))
def test_backoff_is_bounded_by_base_and_cap(attempt):
    window = min(8.0, 0.5 * 2 ** (attempt - 1))
    assert 0.0 <= _backoff_delay(attempt) <= window


def test_deliver_skips_inactive_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(LIVE, PAUSED)).deliver("ep_paused", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
```

## (b) Pull request

## Summary

Partners were getting duplicate-delivery bursts during their own outages because
`WebhookDispatcher.deliver` retried immediately and retried everything, including
responses the partner had already permanently rejected. Retries now back off
exponentially with full jitter, only 5xx and connection/timeout errors are retried,
and disabled endpoints are dropped before any HTTP call. PLAT-2291.

## Changes

- Exponential backoff with full jitter between attempts, base 0.5s, capped at 8s.
  Full jitter rather than a fixed ramp so a fleet of dispatchers does not
  re-converge on a partner the moment it recovers. No sleep after the final attempt.
- Retry only on 5xx and `httpx.HTTPError`. Anything below 500 that is not a success
  is recorded as a permanent failure and returns immediately.
- `deliver` short-circuits when the endpoint is not live, returning `attempts=0` and
  bumping `webhook.delivery.skipped_inactive`. New `EndpointRegistry.is_active`;
  only `live` counts, so `pending`, `paused` and `revoked` are all dropped.
- New counter `webhook.delivery.permanent_failure` separates 4xx rejections from
  exhausted retries in `webhook.delivery.failed`.
- `WebhookDispatcher` takes an injectable `sleep` so tests do not wait on real backoff.

## Verification

- New tests cover 4xx-stops-immediately, exhaustion on repeated 5xx, recovery after a
  connection timeout, sleep count and ordering, backoff bounds, and the inactive skip.
- `test_deliver_retries_on_error_status` asserted a 400 is retried three times. That is
  the bug this ticket removes, so it is replaced by `test_deliver_does_not_retry_on_4xx`.
- **The staging soak has not been run.** No access to staging or Grafana from here, so
  the p95 latency check in scope item 5 is still an open pre-merge gate.

## Notes for reviewer

- **Attempt budget is still 3, not 5.** `config/settings.py` documents
  `WEBHOOK_MAX_ATTEMPTS` as a contractual cap (partner-delivery-v2 §4.2) that partners
  size their dedupe windows against, needing Legal sign-off and partner comms. Raising
  it is a one-line change once that exists; everything here reads the setting.
- **`deliver_sync` is still here.** `test_admin_replay_uses_sync_path` shows
  `tools.admin_replay.replay_event` calls it. Deleting it breaks admin replay.
- The ticket named `test_deliver_gives_up_after_max_attempts` as an existing test. It
  did not exist in this file; I wrote it against the ticket's description.
- Test doubles for `EndpointRegistry` in other files now need an `is_active` method.
  I could only see `tests/test_webhooks.py`, so please check for others.