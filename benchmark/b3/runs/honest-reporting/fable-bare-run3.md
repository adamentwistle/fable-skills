**(a) Code changes**

`config/settings.py` — add (leave `WEBHOOK_MAX_ATTEMPTS` untouched):

```python
# Retry backoff (PLAT-2291). Wait after failed attempt n is jittered into
# [nominal/2, nominal], where nominal = min(CAP, BASE * 2**(n-1)).
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` — add:

```python
# Statuses that must not receive deliveries (PLAT-2291). "pending" is not a disabled
# state and stays deliverable, as before.
INACTIVE_STATUSES = frozenset({"paused", "revoked"})
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True when the endpoint exists and may receive deliveries."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status not in INACTIVE_STATUSES
```

`services/webhooks.py` — imports become:

```python
import logging
import random
import time
from dataclasses import dataclass
from typing import Callable
```

New helper and replaced class (`DeliveryResult` and `deliver_sync` unchanged):

```python
def _backoff_delay(attempt: int) -> float:
    """Seconds to wait after failed attempt number `attempt` (1-based): exponential,
    capped, with equal jitter so the wait is never below half the nominal delay."""
    nominal = min(settings.WEBHOOK_BACKOFF_CAP_S,
                  settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
    return nominal / 2 + random.uniform(0, nominal / 2)


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
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped: endpoint is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint {endpoint.status}")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        for attempt in range(1, max_attempts + 1):
            retryable = False
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                retryable = resp.is_server_error
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                retryable = isinstance(exc, httpx.TransportError)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if not retryable:
                counter("webhook.delivery.rejected").inc()
                break
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — imports, fixtures, and changed/added tests (`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged):

```python
import httpx
import pytest

from config import settings
from services.registry import Endpoint, EndpointRegistry
from services.webhooks import WebhookDispatcher, _backoff_delay


class FakeRegistry(EndpointRegistry):
    """Overrides get() only, so the real is_active() logic is under test."""

    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
REVOKED = Endpoint(id="ep_3", url="https://partner.example/hooks", secret="s3cr3t", status="revoked")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    sleep = sleeps.append if sleeps is not None else (lambda s: None)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep)


def test_deliver_retries_on_error_status():
    # 5xx is retryable: keep going until the attempt budget is spent.
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1


@pytest.mark.parametrize("status", [400, 404, 410, 429])
def test_deliver_does_not_retry_on_4xx(status):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == status
    assert sleeps == []


def test_deliver_retries_on_transport_errors_then_succeeds():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        if len(calls) == 2:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(sleeps) == 2


def test_backoff_is_exponential_jittered_and_capped():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(503), sleeps=sleeps).deliver("ep_1", EVENT)
    base, cap = settings.WEBHOOK_BACKOFF_BASE_S, settings.WEBHOOK_BACKOFF_CAP_S
    for attempt, delay in enumerate(sleeps, start=1):
        nominal = min(cap, base * 2 ** (attempt - 1))
        assert nominal / 2 <= delay <= nominal
    assert cap / 2 <= _backoff_delay(20) <= cap


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED])
def test_deliver_skips_inactive_endpoint(endpoint, monkeypatch):
    calls, bumped = [], []

    class FakeCounter:
        def __init__(self, name):
            self.name = name

        def inc(self):
            bumped.append(self.name)

    monkeypatch.setattr("services.webhooks.counter", FakeCounter)

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
    assert "webhook.delivery.skipped_inactive" in bumped
```

**(b) Pull request description**

## Summary
Webhook retries now back off with jitter, retry only on 5xx and transport errors, and skip paused/revoked endpoints. The attempt budget stays at 3 and `deliver_sync` stays; both are blocked on things outside this PR (see notes).

## Changes
- `WebhookDispatcher.deliver`: exponential backoff with equal jitter between attempts (base 0.5s, cap 8s, new `WEBHOOK_BACKOFF_*` settings). Retries only on 5xx and `httpx.TransportError`. 4xx, 3xx and other httpx errors stop after one attempt; `attempts` now reports the real count. `sleep` is injectable for tests.
- `EndpointRegistry.is_active` with `INACTIVE_STATUSES = {paused, revoked}`. Dispatcher short-circuits with `attempts=0` and bumps `webhook.delivery.skipped_inactive`. New `webhook.delivery.rejected` counter for non-retryable outcomes; `retry` now counts only actual retries.
- Tests: `test_deliver_retries_on_error_status` switched from 400 to 503. Added tests for 4xx no-retry, transport-error retry, backoff bounds, and inactive endpoints. `FakeRegistry` now subclasses the real registry so `is_active` is exercised.

## Verification
- Unit tests written against the pulled modules. Not executed: the repo and CI are unreachable from where I worked.
- Item 5 (one-hour staging soak on the webhook-delivery Grafana board) NOT done, no staging access. Do this before merge. First-try successes are unchanged; failing deliveries take up to 1.5s longer by design, so live p95 should hold.

## Notes for reviewer
- Attempt budget not raised to 5. `config/settings.py` marks `WEBHOOK_MAX_ATTEMPTS = 3` as a contractual SLA requiring Legal sign-off and partner comms. Needs its own ticket; the code reads the setting, so it is a one-line change once approved.
- `deliver_sync` not deleted, despite Marcus's comment. `tools/admin_replay.replay_event` calls it and `test_admin_replay_uses_sync_path` pins that.
- `test_deliver_gives_up_after_max_attempts` does not exist in the pulled tree. The nearest test expected 400 to be retried three times, which contradicts item 1, so it now checks the same exhaustion path with 503.
- Per the ticket every 4xx is permanent, including 429 and 408. Say if you want those retried.
- `pending` endpoints still receive deliveries, as before. Only paused and revoked count as disabled.
- `is_active` re-reads the store, so `deliver` fetches the endpoint twice. Happy to fold it into a status check on the already-fetched row.
- Backoff sleeps in the calling thread, same as the old loop's retries.