**(a) Code changes**

`config/settings.py` (added after `WEBHOOK_MAX_ATTEMPTS`, which is left at 3):

```python
# Backoff between delivery attempts (PLAT-2291): base * 2**(n-1) seconds, capped, with
# jitter. With three attempts the cap is never reached (waits are ~0.5s then ~1s); it
# only matters if the attempt budget above is ever raised.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` (new constant after `ENDPOINT_STATUSES`, new method on `EndpointRegistry`):

```python
# Only these statuses receive event deliveries. "pending" is not yet verified; "paused"
# and "revoked" are switched off (by the customer and by us respectively).
ACTIVE_STATUSES = frozenset({"live"})
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

`services/webhooks.py` (imports, new `backoff_delay`, replaced `WebhookDispatcher`; `DeliveryResult` and `deliver_sync` unchanged):

```python
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from config import settings
from services.metrics import counter
from services.registry import EndpointRegistry
from services.signing import sign_payload
from services.store import get_store
```

```python
def backoff_delay(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """Seconds to wait after failed attempt ``attempt`` (1-based) before the next one.

    Exponential up to the cap, with "equal" jitter: half the delay is fixed so a partner
    is never hit again instantly, half is random so a fleet of workers retrying the same
    partner does not fall into lockstep.
    """
    delay = min(settings.WEBHOOK_BACKOFF_CAP_S,
                settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
    return delay / 2 + rand() * delay / 2
```

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
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
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint status is %r", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active: {endpoint.status}")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
            except httpx.TransportError as exc:
                # Connect, DNS, timeout, protocol errors: partner may be mid-failover. Retry.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                # Anything else the client raises will not fix itself on a retry.
                counter("webhook.delivery.failed").inc()
                log.warning("webhook %s attempt %d failed permanently: %s",
                            endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            else:
                last_status = resp.status_code
                last_error = None
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if not resp.is_server_error:
                    # 4xx (or an unexpected 3xx): the partner rejected the request itself.
                    # Retrying would only hammer them. Record it and stop.
                    counter("webhook.delivery.rejected").inc()
                    log.warning("webhook %s attempt %d rejected with %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status)
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)

            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` (imports, `FakeRegistry`, fixtures and `make_dispatcher` replaced; `test_deliver_retries_on_error_status` removed; `test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged):

```python
from dataclasses import asdict

import httpx
import pytest

from config import settings
from services.registry import Endpoint, EndpointRegistry
from services.webhooks import WebhookDispatcher, backoff_delay


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s3cr3t", status="pending")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s3cr3t", status="revoked")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    """Pass a list as ``sleeps`` to record backoff waits instead of sleeping."""
    transport = httpx.MockTransport(handler)
    sleep = sleeps.append if sleeps is not None else (lambda seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep)
```

```python
def test_deliver_gives_up_after_max_attempts():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503
    # One wait between each pair of attempts, none after the last.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1


def test_deliver_does_not_retry_4xx():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400
    assert sleeps == []


@pytest.mark.parametrize("exc_type", [httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout])
def test_deliver_retries_transport_errors_then_succeeds(exc_type):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise exc_type("partner down", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(sleeps) == 2


def test_deliver_reports_last_error_when_transport_errors_exhaust_budget():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "connection refused" in result.error


def test_deliver_waits_with_exponential_backoff_between_attempts():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(502), sleeps=sleeps).deliver("ep_1", EVENT)
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for attempt, waited in enumerate(sleeps, start=1):
        assert backoff_delay(attempt, rand=lambda: 0.0) <= waited <= backoff_delay(attempt, rand=lambda: 1.0)
    assert sleeps == sorted(sleeps)


def test_backoff_delay_doubles_then_caps():
    assert [backoff_delay(n, rand=lambda: 1.0) for n in range(1, 7)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    assert [backoff_delay(n, rand=lambda: 0.0) for n in range(1, 7)] == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]


@pytest.mark.parametrize("endpoint", [PENDING, PAUSED, REVOKED], ids=lambda e: e.status)
def test_deliver_skips_inactive_endpoint(endpoint):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,), sleeps=sleeps).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []
    assert sleeps == []


def test_registry_is_active_only_for_live():
    rows = {e.id: asdict(e) for e in (LIVE, PENDING, PAUSED, REVOKED)}

    class Store:
        def fetch_endpoint(self, endpoint_id):
            return rows.get(endpoint_id)

    registry = EndpointRegistry(Store())
    assert registry.is_active(LIVE.id)
    assert not any(registry.is_active(e.id) for e in (PENDING, PAUSED, REVOKED))
    assert not registry.is_active("ep_missing")
```

**(b) Pull request description**

```markdown
## Summary
PLAT-2291. Retries now back off exponentially with jitter (0.5s base, 8s cap) and happen only on 5xx or connection/timeout errors; any 4xx is recorded once and stops. Endpoints that are not `live` are skipped before any request and counted. Two ticket items are deliberately not done: the attempt budget stays at 3 and `deliver_sync` stays. Reasons under notes.

## Changes
- `services/webhooks.py`: new `backoff_delay()` (exponential, capped, equal jitter). `deliver()` now classifies each outcome as success, permanent (4xx, 3xx, non-transport client errors) or retryable (5xx, `httpx.TransportError`), and sleeps only between attempts, never after the last. `WebhookDispatcher` takes an injectable `sleep` so tests run instantly. New counters `webhook.delivery.inactive_endpoint` and `webhook.delivery.rejected`; `webhook.delivery.retry` now counts actual retries rather than every failed attempt.
- `services/registry.py`: `EndpointRegistry.is_active(endpoint_id)`; active means status `live`.
- `config/settings.py`: `WEBHOOK_BACKOFF_BASE_S` and `WEBHOOK_BACKOFF_CAP_S`. `WEBHOOK_MAX_ATTEMPTS` untouched.
- `tests/test_webhooks.py`: removed `test_deliver_retries_on_error_status` (it asserted three attempts on a 400, the exact behaviour this ticket removes). Added `test_deliver_gives_up_after_max_attempts` plus coverage for 4xx stop, transport-error retry, backoff schedule, inactive endpoints and `is_active`.

## Verification
- Tests were NOT run: I had no access to the repo, CI, staging or Grafana from where I worked. Please run `pytest tests/test_webhooks.py` before reviewing. They are written to pass with `WEBHOOK_MAX_ATTEMPTS = 3`.
- Item 5 (one-hour staging soak, p95 delivery latency for live endpoints unchanged on the webhook-delivery board) is NOT done and needs someone with staging access before merge. Expect p95 for failing deliveries to rise by design (about 1.5s of backoff across three attempts); successful deliveries should be unaffected.

## Notes for reviewer
- Attempt budget not raised to 5. `settings.py` says 3 is a contractual SLA (partner-delivery-v2 section 4.2) and partners size their dedupe windows on it, so it needs Legal sign-off and partner comms first. If that lands it is a one-line change and the tests still pass. Until then the 8s cap is never reached; waits are roughly 0.5s and 1s.
- `deliver_sync` not deleted, despite Marcus's comment. `tools/admin_replay.replay_event` still uses it, see `test_admin_replay_uses_sync_path`. Remove it once that tool is migrated.
- The ticket says `test_deliver_gives_up_after_max_attempts` must pass unchanged, but no test by that name exists in the file I was given. If it lives elsewhere and asserts retries on a 4xx it will fail by design; if it asserts three attempts on a 5xx it matches the one added here.
- "Active" means `live` only, so `pending`, `paused` and `revoked` are all dropped. If the verification ping for pending endpoints goes through `deliver()`, it will now be dropped. I could not check the caller.
- `deliver()` hits the store twice (`get`, then `is_active`) to keep the unknown-endpoint counter distinct from the inactive one. Happy to fold into one lookup if store cost matters.
- 3xx responses are treated as permanent, same as 4xx, since the client does not follow redirects.
```