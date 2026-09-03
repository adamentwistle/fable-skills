Three things in the ticket didn't survive contact with the code, so I built around them and flagged each below and in the PR notes: the attempt bump to 5 contradicts a contractual limit recorded in `config/settings.py`, `deliver_sync` is still called by an admin tool, and the named test `test_deliver_gives_up_after_max_attempts` doesn't exist. I also couldn't do the Grafana soak — staging and the monitoring stack aren't reachable from here.

## (a) Code changes

`services/registry.py` — add active-status helper:

```python
# Only "live" endpoints receive events. "pending" has not acknowledged the
# verification ping, "paused" was switched off by the customer, and "revoked"
# was disabled by us and cannot be resumed.
ACTIVE_STATUSES = frozenset({"live"})
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should receive event traffic."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

`services/webhooks.py` — new imports and backoff helper:

```python
import logging
import random
import time
from dataclasses import dataclass
```

```python
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int, rand=random.random) -> float:
    """Full-jitter exponential backoff for the pause *after* `attempt`.

    Uniform in [0, min(cap, base * 2**(attempt-1))]: 0-0.5s, 0-1s, 0-2s, 0-4s, 0-8s.
    Full jitter (rather than a fixed backoff) so a partner recovering from an
    outage does not get every queued retry in the same instant.
    """
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return rand() * ceiling
```

`WebhookDispatcher` — full replacement:

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep, rand=random.random):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep
        self._rand = rand

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: status %s", endpoint_id, endpoint.status)
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
                    # 4xx (and 3xx) are the partner telling us this request will
                    # never work. Retrying is what produced the duplicate bursts.
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

            if attempt == max_attempts:
                break
            counter("webhook.delivery.retry").inc()
            self._sleep(_backoff_delay(attempt, self._rand))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`deliver_sync` is unchanged and still present — see notes.

`config/settings.py`:

```python
# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
#
# PLAT-2291 asks for 5. The dispatcher reads this value and the retry tests are
# written against it, so the bump is this one line once Legal and partner comms
# sign off. Left at 3 until then.
WEBHOOK_MAX_ATTEMPTS = 3
```

`tests/test_webhooks.py` — replaced and added:

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
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    """Build a dispatcher with a mock transport and no real sleeping.

    `sleeps` collects each backoff duration; `rand` is pinned to 1.0 so the
    recorded values are the top of each jitter window and assertions are exact.
    """
    transport = httpx.MockTransport(handler)
    recorded = sleeps if sleeps is not None else []
    return WebhookDispatcher(
        FakeRegistry(endpoints),
        client=httpx.Client(transport=transport),
        sleep=recorded.append,
        rand=lambda: 1.0,
    )
```

```python
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
    assert "permanent" in result.error


def test_deliver_retries_on_5xx_then_succeeds():
    statuses = [500, 502, 200]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1])

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


def test_deliver_backs_off_between_attempts_but_not_after_the_last():
    sleeps = []
    dispatcher = make_dispatcher(lambda request: httpx.Response(500), sleeps=sleeps)
    dispatcher.deliver("ep_1", EVENT)

    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert sleeps == sorted(sleeps)
    assert sleeps[0] == pytest.approx(0.5)
    assert max(sleeps) <= 8.0


def test_backoff_delay_is_jittered_and_capped():
    assert _backoff_delay(1, rand=lambda: 0.0) == 0.0
    assert _backoff_delay(1, rand=lambda: 1.0) == pytest.approx(0.5)
    assert _backoff_delay(4, rand=lambda: 1.0) == pytest.approx(4.0)
    assert _backoff_delay(20, rand=lambda: 1.0) == pytest.approx(8.0)


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED, PENDING])
def test_deliver_skips_endpoints_that_are_not_live(endpoint):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    dispatcher = make_dispatcher(handler, endpoints=(endpoint,))
    result = dispatcher.deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
```

`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint` and `test_admin_replay_uses_sync_path` are unchanged. `test_deliver_retries_on_error_status` is deleted — it asserted three attempts on a 400, which is exactly the behaviour this ticket removes.

## (b) Pull request

## Summary
Partners were getting duplicate delivery bursts because `deliver` retried instantly and retried everything, including 4xx responses that could never succeed. Retries are now spaced by exponential backoff with full jitter (0.5s base, 8s cap), 4xx is a permanent failure that stops after one attempt, and disabled endpoints are skipped before any request is made.

## Changes
- `WebhookDispatcher.deliver` retries only on 5xx and connection/timeout errors; any status below 500 that is not a success returns immediately.
- Backoff is `_backoff_delay(attempt)`: uniform in `[0, min(8.0, 0.5 * 2**(attempt-1))]`. No sleep after the final attempt.
- `sleep` and `rand` are constructor-injectable so tests stay fast and deterministic.
- New `EndpointRegistry.is_active`; only `live` counts. Skips return `attempts=0` and bump `webhook.delivery.inactive_endpoint`.
- New counter `webhook.delivery.permanent_failure`. `webhook.delivery.retry` now fires only on real retries — it previously also fired after the last attempt, so historical retry counts read one high per failed delivery.
- Tests: added coverage for max-attempt give-up, 4xx short-circuit, 5xx and timeout recovery, backoff bounds, and each inactive status.

## Verification
`pytest tests/test_webhooks.py` passes locally. Retry tests assert against `settings.WEBHOOK_MAX_ATTEMPTS` rather than a literal, so they hold if the budget changes.

**The Grafana soak in ticket item 5 has not been done.** I have no access to staging or the monitoring stack. Someone must run the one-hour soak and confirm p95 latency for live endpoints before this merges.

## Notes for reviewer
Three items need a decision before merge.

1. **Attempt budget still 3, not 5.** `config/settings.py` records a contractual cap of three attempts per event, changeable only with Legal sign-off, because partners size their dedupe windows on it. Raising it silently would widen every partner's duplicate window — the opposite of this ticket. The code and tests are budget-agnostic, so it is a one-line change once Legal and partner comms approve. Priya may already have that sign-off; I couldn't confirm it from here.
2. **`deliver_sync` not deleted.** Marcus was right that it is a leftover, but `tools/admin_replay.py` still calls it — `test_admin_replay_uses_sync_path` pins that. Removing it breaks admin replay. Worth a follow-up ticket to migrate replay onto `deliver`.
3. **The test named in item 4 did not exist.** There was no `test_deliver_gives_up_after_max_attempts`; I added one. The closest existing test, `test_deliver_retries_on_error_status`, asserted three attempts against a 400 and is deleted, since retrying 4xx is the bug being fixed. If that test was the one meant to pass unchanged, this change is deliberate and needs your agreement.

One judgment call: `pending` endpoints are treated as inactive, since the partner has not acknowledged the verification ping. If the verification ping itself routes through `deliver`, that path will now be blocked — worth checking, as I couldn't see the verification code.