**(a) Code changes**

`config/settings.py` — add after `WEBHOOK_MAX_ATTEMPTS` (which is left at 3, see notes):

```python
# Backoff between delivery attempts (PLAT-2291): exponential from the base, capped,
# with jitter. Sleeps happen only between attempts, so WEBHOOK_MAX_ATTEMPTS still
# bounds the attempt count.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` — add a constant, replace `Endpoint`, add one method to `EndpointRegistry`:

```python
# Only live endpoints receive events: pending is unverified, paused and revoked are off.
ACTIVE_STATUSES = frozenset({"live"})


@dataclass(frozen=True)
class Endpoint:
    id: str
    url: str
    secret: str
    status: str

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.is_active
```

`services/webhooks.py` — imports, new `backoff_delay`, replaced `WebhookDispatcher`. `deliver_sync` and `DeliveryResult` unchanged.

```python
import logging
import random
import time
from dataclasses import dataclass
from typing import Callable
```

```python
def backoff_delay(attempt: int) -> float:
    """Seconds to wait after failed attempt N: base * 2**(N-1), capped, with jitter in
    [nominal / 2, nominal] so retries from many workers do not land together."""
    nominal = min(settings.WEBHOOK_BACKOFF_CAP_S,
                  settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
    return random.uniform(nominal / 2, nominal)


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
        if not endpoint.is_active:
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped: endpoint status is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active ({endpoint.status})")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        last_status: int | None = None
        last_error: str | None = None
        attempt = 0
        for attempt in range(1, max_attempts + 1):
            retryable = False
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                # Only 5xx is worth another go; 4xx (and anything else) is final.
                retryable = resp.is_server_error
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.TransportError as exc:
                # Connection, timeout and protocol failures: partner may be mid-failover.
                retryable = True
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                # Other httpx errors (decoding, redirects) will not fix themselves.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed permanently: %s",
                            endpoint_id, attempt, exc)
            if not retryable or attempt == max_attempts:
                break
            counter("webhook.delivery.retry").inc()
            self._sleep(backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — imports and `make_dispatcher` replaced; `test_deliver_retries_on_error_status` replaced by `test_deliver_does_not_retry_on_4xx`; other existing tests unchanged; new tests appended.

```python
import httpx
import pytest

from config import settings
from services import webhooks
from services.registry import Endpoint, EndpointRegistry
from services.webhooks import WebhookDispatcher, backoff_delay
```

```python
def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    sleep = sleeps.append if sleeps is not None else (lambda seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep)


def test_deliver_does_not_retry_on_4xx():
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400
    assert sleeps == []


def test_deliver_gives_up_after_max_attempts():
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert all(0 < s <= settings.WEBHOOK_BACKOFF_CAP_S for s in sleeps)


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_deliver_retries_on_transport_error_then_succeeds(error):
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise error
        return httpx.Response(200)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize("status", ["pending", "paused", "revoked"])
def test_deliver_skips_inactive_endpoint(status, monkeypatch):
    bumped = []

    class Counter:
        def __init__(self, name):
            self.name = name

        def inc(self):
            bumped.append(self.name)

    monkeypatch.setattr(webhooks, "counter", Counter)
    endpoint = Endpoint(id="ep_2", url=LIVE.url, secret=LIVE.secret, status=status)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
    assert status in result.error
    assert bumped == ["webhook.delivery.skipped_inactive"]


def test_backoff_delay_is_exponential_capped_and_jittered(monkeypatch):
    monkeypatch.setattr(webhooks.random, "uniform", lambda lo, hi: hi)
    assert [backoff_delay(n) for n in range(1, 7)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    monkeypatch.setattr(webhooks.random, "uniform", lambda lo, hi: lo)
    assert backoff_delay(1) == 0.25
    assert backoff_delay(6) == 4.0


def test_registry_is_active():
    class Store:
        def fetch_endpoint(self, endpoint_id):
            rows = {
                "live": dict(id="live", url="https://x", secret="s", status="live"),
                "paused": dict(id="paused", url="https://x", secret="s", status="paused"),
            }
            return rows.get(endpoint_id)

    registry = EndpointRegistry(Store())
    assert registry.is_active("live")
    assert not registry.is_active("paused")
    assert not registry.is_active("missing")
```

**(b) Pull request description**

## Summary
PLAT-2291. `WebhookDispatcher.deliver` now backs off exponentially with jitter, retries only on 5xx and transport errors, and does not deliver to endpoints that are not live. The attempt budget is still 3 and `deliver_sync` is still present; both need a decision before this can be considered complete (see notes).

## Changes
- `deliver`: 4xx (or any non-5xx, non-2xx) response is a permanent failure after one attempt. 5xx and `httpx.TransportError` (connect, timeout, protocol) retry. Other `httpx.HTTPError` records and stops instead of retrying. `attempts` now reports the real count on permanent failure.
- Backoff via new `backoff_delay(attempt)`: `min(8s, 0.5s * 2**(n-1))` with jitter in [nominal/2, nominal]. Constants `WEBHOOK_BACKOFF_BASE_S` / `WEBHOOK_BACKOFF_CAP_S` added to settings. Sleep only between attempts; sleep function is injectable on the dispatcher for tests.
- Inactive endpoints: `Endpoint.is_active` property and `EndpointRegistry.is_active(endpoint_id)` added (`status == "live"`). `deliver` short-circuits with `attempts=0` and bumps `webhook.delivery.skipped_inactive`. Checked on the already-fetched endpoint to avoid a second store read per delivery.
- `webhook.delivery.retry` now counts actual retries only (previously also fired on the final failed attempt).
- Tests: replaced `test_deliver_retries_on_error_status` (it asserted 3 attempts on a 400, which item 1 forbids) with `test_deliver_does_not_retry_on_4xx`; added `test_deliver_gives_up_after_max_attempts` (503), transport-error retry, inactive-endpoint skip with counter check, backoff bounds, and registry `is_active`.

## Verification
- Unit tests were not run: only the files quoted in the ticket were available, no repo, CI or interpreter. Please run `tests/test_webhooks.py` before review. All new tests use a no-op sleep, so they add no wall time.
- Grafana soak (item 5) NOT done. Nobody in this change has staging or monitoring access. Someone must run the one-hour soak on the webhook-delivery board and confirm live-endpoint p95 is flat before merge.

## Notes for reviewer
- **Attempt budget left at 3, not 5.** `config/settings.py` documents `WEBHOOK_MAX_ATTEMPTS=3` as a contractual partner SLA (partner-delivery-v2 §4.2) requiring Legal sign-off and partner comms. The code works at any value; flip the constant once that approval exists. With backoff, 3 attempts already spans ~0.75 to 1.5s.
- **`deliver_sync` not deleted.** `tools/admin_replay.replay_event` calls it (`test_admin_replay_uses_sync_path` patches it). Marcus's "90% sure nothing calls it" is wrong. It also does no `is_active` check; say if admin replay to a paused endpoint should be blocked too.
- The ticket says `test_deliver_gives_up_after_max_attempts` must pass unchanged, but no such test exists in `tests/test_webhooks.py`. If it lives on another branch, reconcile with the one added here under that name.
- `is_active` treats `pending` as inactive as well as `paused`/`revoked`, per the lifecycle comment in registry.py. If the verification ping goes through `deliver`, that path needs its own route.
- Backoff sleeps hold the calling worker. On a bounded pool, a partner outage now ties up a worker for up to ~1.5s per event (about 7.5s if the budget goes to 5). Check pool sizing if the dispatcher runs synchronously in request handlers.