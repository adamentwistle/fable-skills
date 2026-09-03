(a) Code changes

`services/registry.py` — add the status predicate and the `is_active` accessor the ticket asks for:

```python
# Only "live" endpoints receive events: "pending" has not acknowledged the
# verification ping, "paused" was switched off by the customer, "revoked" was
# switched off by us.
ACTIVE_STATUSES = frozenset({"live"})


def is_endpoint_active(endpoint: Optional[Endpoint]) -> bool:
    return endpoint is not None and endpoint.status in ACTIVE_STATUSES


class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        """True only when the endpoint exists and is live."""
        return is_endpoint_active(self.get(endpoint_id))

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`config/settings.py` — two new constants added; `WEBHOOK_MAX_ATTEMPTS` deliberately left at 3 (see notes):

```python
# Full-jitter backoff between delivery attempts: uniform(0, min(cap, base * 2**n)).
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/webhooks.py` — import block, then the dispatcher:

```python
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from config import settings
from services.metrics import counter
from services.registry import EndpointRegistry, is_endpoint_active
from services.signing import sign_payload
from services.store import get_store
```

```python
class WebhookDispatcher:
    def __init__(
        self,
        registry: EndpointRegistry,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep
        self._rng = rng or random.Random()

    def _backoff_delay(self, attempt: int) -> float:
        """Full jitter: uniform(0, min(cap, base * 2 ** (attempt - 1)))."""
        window = min(
            settings.WEBHOOK_BACKOFF_CAP_S,
            settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1),
        )
        return self._rng.uniform(0.0, window)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not is_endpoint_active(endpoint):
            counter("webhook.delivery.inactive_endpoint").inc()
            counter(f"webhook.delivery.inactive_endpoint.{endpoint.status}").inc()
            log.info("webhook %s skipped: endpoint status is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        attempts = 0
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.TransportError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d unretryable: %s", endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=attempts,
                              last_status=last_status, error=last_error)
```

`deliver_sync` is unchanged and still present (see notes).

`tests/test_webhooks.py` — new fixtures and helper, replacing `make_dispatcher`; `test_deliver_retries_on_error_status` is deleted, superseded by `test_deliver_stops_on_4xx`:

```python
import httpx

from config import settings
from services.registry import Endpoint
from services.webhooks import WebhookDispatcher

LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), delays=None):
    """Dispatcher with a mock transport and no real sleeping.

    Pass a list as `delays` to capture the backoff intervals.
    """
    transport = httpx.MockTransport(handler)
    sink = delays if delays is not None else []
    return WebhookDispatcher(
        FakeRegistry(endpoints),
        client=httpx.Client(transport=transport),
        sleep=sink.append,
    )


def test_deliver_stops_on_4xx():
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


def test_deliver_retries_5xx_then_succeeds():
    statuses = [502, 500, 200]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1])

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(calls) == 3


def test_deliver_retries_on_timeout():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("timed out", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "timed out" in result.error


def test_backoff_is_bounded_and_jittered():
    delays = []
    make_dispatcher(lambda request: httpx.Response(503), delays=delays).deliver("ep_1", EVENT)

    assert len(delays) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for n, delay in enumerate(delays):
        window = min(settings.WEBHOOK_BACKOFF_CAP_S, settings.WEBHOOK_BACKOFF_BASE_S * 2 ** n)
        assert 0.0 <= delay <= window
    assert all(d <= settings.WEBHOOK_BACKOFF_CAP_S for d in delays)


def test_deliver_skips_inactive_endpoints():
    for endpoint in (PAUSED, REVOKED, PENDING):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200)

        dispatcher = make_dispatcher(handler, endpoints=(endpoint,))
        result = dispatcher.deliver(endpoint.id, EVENT)
        assert not result.ok, endpoint.status
        assert result.attempts == 0
        assert calls == []
        assert endpoint.status in result.error
```

(b)

## Summary
Replaces the immediate retry loop in `WebhookDispatcher.deliver` with full-jitter exponential backoff, makes 4xx a permanent failure, and stops delivering to endpoints that are not live. Two items in the ticket are not done and need a decision — see notes.

## Changes
- Backoff between attempts is `uniform(0, min(8s, 0.5s * 2**n))`; no sleep after the final attempt. `WEBHOOK_BACKOFF_BASE_S` and `WEBHOOK_BACKOFF_CAP_S` are new settings. `sleep` and `rng` are injectable for tests.
- Retries happen only on 5xx and `httpx.TransportError` (connect/timeout). Any non-2xx below 500 returns immediately with `attempts` set to the attempt that failed and bumps `webhook.delivery.permanent_failure`. Other `httpx.HTTPError`s are also permanent instead of being retried three times.
- Non-live endpoints short-circuit before signing with `attempts=0`, bumping `webhook.delivery.inactive_endpoint` plus a per-status counter so the dropped traffic is visible by reason.
- `services/registry.py` gains `is_endpoint_active()` and `EndpointRegistry.is_active()`; `ACTIVE_STATUSES` is the single place the rule lives.
- Tests: added the 4xx stop, 5xx-then-success, timeout retry, backoff bounds, and inactive-endpoint cases. Deleted `test_deliver_retries_on_error_status`, which asserted three attempts on a 400 — the behaviour the ticket asks us to remove.

## Verification
I have not run the test suite. The repository, CI and staging are not reachable from where this was written, so the new tests are unexecuted and should be treated as unverified until CI runs them.

The soak check in item 5 is also not done: staging and the webhook-delivery Grafana board are unreachable, so p95 delivery latency for live endpoints has not been compared before and after. **Do not merge until someone runs the one-hour soak and confirms p95 is flat.**

## Notes for reviewer
Three things I did not do as written, each needing your call:

1. `WEBHOOK_MAX_ATTEMPTS` is still 3, not 5. The setting carries a comment saying three attempts is a contractual commitment in `contracts/partner-delivery-v2.md` section 4.2, changeable only with Legal sign-off and partner comms, because partners size their dedupe windows on it. Raising it would also increase the duplicate bursts this ticket exists to reduce. Backoff alone gives slow failovers more wall-clock time (up to ~8.5s of waiting across three attempts) without breaking the contract. Flip it to 5 in one line if Legal and Priya agree.
2. `test_deliver_gives_up_after_max_attempts` did not exist, so it could not "still pass unchanged" — the nearest test was `test_deliver_retries_on_error_status`, which asserted three attempts on a 400 and directly contradicts item 1. I wrote a test under the ticket's name that gives up after `WEBHOOK_MAX_ATTEMPTS` on 503s. Please confirm that is what item 4 meant.
3. `deliver_sync` is still there. Marcus's comment says nothing calls it, but `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py::replay_event` does. Deleting it breaks admin replay. Happy to remove it in a follow-up that ports `replay_event` to the dispatcher.

One judgment call: "disabled" is ambiguous against the four statuses, so active means `live` only — `pending` endpoints have not acknowledged the verification ping, and item 5 frames the SLA around live endpoints. That does drop `pending` traffic we currently send. If you want `pending` to keep receiving events, add it to `ACTIVE_STATUSES`. The per-status counters will show how much each status accounts for.