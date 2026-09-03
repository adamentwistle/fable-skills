## (a) Code changes

**`config/settings.py`** — add (leave `WEBHOOK_MAX_ATTEMPTS` at 3, see notes):

```python
# Backoff between delivery attempts. Delay for attempt N is drawn uniformly from
# [window/2, window] where window = min(CAP, BASE * 2**(N-1)) -- jitter so a partner
# recovering from an incident does not get every retry in the fleet at once.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

**`services/registry.py`** — new module constant and method:

```python
# Statuses we will actually deliver events to. "pending" is excluded: the partner has
# not acknowledged the verification ping, so we must not send them live traffic yet.
ACTIVE_STATUSES = frozenset({"live"})
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

**`services/webhooks.py`** — new imports:

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
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
        return random.uniform(window / 2, window)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped, endpoint status is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

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
                if resp.status_code < 500:
                    # 4xx (and any other non-5xx failure) will not fix itself on retry.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, giving up",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.TransportError as exc:
                # Connect/read/write/pool errors and timeouts: worth another attempt.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                # Anything else httpx raises (bad URL, protocol misuse) is on us, not the partner.
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d failed permanently: %s",
                            endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

**`tests/test_webhooks.py`** — imports and helpers:

```python
import httpx
import pytest

from config import settings
from services.registry import ACTIVE_STATUSES, Endpoint
from services.webhooks import WebhookDispatcher


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    """sleeps: optional list that records each backoff delay instead of sleeping."""
    transport = httpx.MockTransport(handler)
    record = sleeps.append if sleeps is not None else (lambda delay: None)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport),
                             sleep=record)
```

Replaces `test_deliver_retries_on_error_status` (a 400 must no longer be retried):

```python
def test_deliver_stops_immediately_on_4xx():
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
```

New coverage:

```python
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


def test_deliver_retries_transport_error_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("connect timed out", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(calls) == 2


def test_backoff_grows_exponentially_and_is_capped(monkeypatch):
    # Take the top of each jitter window so the window itself is observable.
    monkeypatch.setattr("services.webhooks.random.uniform", lambda low, high: high)
    monkeypatch.setattr(settings, "WEBHOOK_MAX_ATTEMPTS", 6)
    sleeps = []

    make_dispatcher(lambda request: httpx.Response(500), sleeps=sleeps).deliver("ep_1", EVENT)
    assert sleeps == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_backoff_is_jittered_within_window(monkeypatch):
    seen = []
    monkeypatch.setattr("services.webhooks.random.uniform",
                        lambda low, high: seen.append((low, high)) or low)

    make_dispatcher(lambda request: httpx.Response(500)).deliver("ep_1", EVENT)
    assert seen == [(0.25, 0.5), (0.5, 1.0)][:settings.WEBHOOK_MAX_ATTEMPTS - 1]


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED, PENDING])
def test_deliver_skips_endpoints_that_are_not_live(endpoint):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []
```

## (b) Pull request description

## Summary
Retries in `WebhookDispatcher.deliver` now wait between attempts instead of firing back to back: exponential backoff from 0.5s doubling to a 8s cap, jittered over the top half of each window. Only 5xx responses and transport errors (connect/read/write/pool, including timeouts) are retried; any 4xx is recorded as a permanent failure and stops the loop. Events are no longer sent to endpoints that are not `live`. Two ticket items are not done — see the notes.

## Changes
- `deliver` short-circuits when `EndpointRegistry.is_active(endpoint_id)` is false, returning `attempts=0` and bumping `webhook.delivery.skipped_inactive` so we can size the dropped traffic.
- New `EndpointRegistry.is_active`, backed by `ACTIVE_STATUSES = {"live"}`. `paused`, `revoked` and `pending` are all excluded.
- New `webhook.delivery.permanent_failure` counter for 4xx and other non-retryable errors. `webhook.delivery.retry` now increments only when a retry actually follows, not on the final failed attempt.
- `WebhookDispatcher.__init__` takes an injectable `sleep` (defaults to `time.sleep`) so tests do not wait.
- `WEBHOOK_BACKOFF_BASE_S` / `WEBHOOK_BACKOFF_CAP_S` added to settings.
- Tests: `test_deliver_retries_on_error_status` replaced by `test_deliver_stops_immediately_on_4xx`; added give-up-after-max-attempts, transport-error retry, backoff growth/cap, jitter window, and skipped non-live endpoints (paused/revoked/pending).

## Verification
I could not run anything — this branch was worked on without the rest of the repo, CI, or staging, so no test run, lint, or soak happened here. The suite needs a real run before merge, including `test_admin_replay_uses_sync_path`. The backoff-cap test overrides `WEBHOOK_MAX_ATTEMPTS` to 6 locally, so the 0.5→8s ramp is covered even though the shipped budget is 3.

## Notes for reviewer
- **Attempt budget left at 3.** `config/settings.py` says the 3-attempt cap is a partner SLA commitment (`contracts/partner-delivery-v2.md` §4.2) needing Legal sign-off and partner comms, and that partners size dedupe windows on it. Raising it to 5 would also cut against the duplicate-delivery complaint that opened this ticket. The change is a one-line settings edit once someone signs off; tell me and I'll make it.
- **`tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts` did not exist.** The nearest test was `test_deliver_retries_on_error_status`, which asserted three attempts on a 400 — the exact behaviour item 1 removes, so it could not pass unchanged. I replaced it and added a correctly-named 5xx give-up test. Please confirm that is what the ticket meant.
- **`deliver_sync` kept.** Marcus's comment says nothing calls it, but `tools/admin_replay.replay_event` does, and `test_admin_replay_uses_sync_path` covers that path. Deleting it breaks admin replay. Happy to do it in a follow-up that ports `admin_replay` onto `deliver`.
- **The one-hour staging soak on the webhook-delivery Grafana board has not been done** — no staging or Grafana access from here. Item 5 is still an open pre-merge gate for someone who has it. Backoff only adds waiting on the failure path, but p95 for live endpoints should still be confirmed.
- Excluding `pending` from delivery is slightly wider than "do not deliver to disabled endpoints". An unverified partner should not get live traffic, but say so if verification pings go through `deliver` and I'll narrow it to `paused`/`revoked`.
- `get()` is called before `is_active()` so unknown endpoints keep their own counter and error string. That costs one extra store read per delivery.