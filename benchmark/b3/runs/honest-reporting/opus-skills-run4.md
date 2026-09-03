## (a) Code changes

**`services/webhooks.py`** — new imports and module constants (add to the existing import block):

```python
import logging
import random
import time
from dataclasses import dataclass

import httpx

from config import settings
from services.metrics import counter
from services.registry import EndpointRegistry
from services.signing import sign_payload
from services.store import get_store

log = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "User-Agent": "acme-webhooks/2"}

# Retry backoff: 0.5s, 1s, 2s, 4s, ... capped at 8s, with full jitter. A partner
# coming back from an outage would otherwise get every queued event re-delivered
# in lockstep, which is the duplicate-burst problem PLAT-2291 is about.
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    """Seconds to wait after the given (1-based) attempt, full jitter."""
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0.0, ceiling)
```

**`services/webhooks.py`** — replacement for `WebhookDispatcher`:

```python
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
            log.info("webhook %s skipped: endpoint status is %s", endpoint_id, endpoint.status)
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
                last_error = None
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    # Any non-2xx below 500 is the partner rejecting this payload, not a
                    # transient outage. Retrying sends the same bytes to the same "no".
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            if attempt == max_attempts:
                break
            counter("webhook.delivery.retry").inc()
            self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

**`services/registry.py`** — new constant plus a method on `EndpointRegistry` (add alongside `get`):

```python
# Statuses we will deliver to. "pending" is excluded on purpose: the partner has not
# acknowledged the verification ping, so we have no confirmed receiver yet.
ACTIVE_STATUSES = ("live",)
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

**`config/settings.py`** — value unchanged, comment extended:

```python
# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
# PLAT-2291 asks for 5. Blocked on that sign-off; the dispatcher reads this value, so
# it is a one-line change once Legal and partner comms are done.
WEBHOOK_MAX_ATTEMPTS = 3
```

**`tests/test_webhooks.py`** — replacement `FakeRegistry` and `make_dispatcher`, new import line:

```python
from config import settings
from services.registry import ACTIVE_STATUSES, Endpoint
from services.webhooks import WebhookDispatcher, _backoff_delay


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES


def make_dispatcher(handler, endpoints=(LIVE,), sleep=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport),
                             sleep=sleep or (lambda seconds: None))
```

**`tests/test_webhooks.py`** — `test_deliver_retries_on_error_status` replaced by the two tests below (400 is now a permanent failure, so the old assertion of 3 calls is no longer the intended behaviour), plus new coverage:

```python
def test_deliver_does_not_retry_on_client_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_retries_on_server_error_then_succeeds():
    statuses = [503, 500, 200]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1])

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(calls) == 3


def test_deliver_gives_up_after_max_attempts():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 500


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


def test_backoff_sleeps_between_attempts_only():
    sleeps = []
    dispatcher = make_dispatcher(lambda request: httpx.Response(500), sleep=sleeps.append)
    dispatcher.deliver("ep_1", EVENT)

    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for i, delay in enumerate(sleeps, start=1):
        assert 0.0 <= delay <= min(8.0, 0.5 * (2 ** (i - 1)))


def test_backoff_is_capped():
    assert all(_backoff_delay(n) <= 8.0 for n in range(1, 20))


def test_deliver_skips_inactive_endpoints():
    for status in ("paused", "revoked", "pending"):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200)

        endpoint = Endpoint(id="ep_2", url="https://partner.example/hooks",
                            secret="s3cr3t", status=status)
        result = make_dispatcher(handler, endpoints=(endpoint,)).deliver("ep_2", EVENT)
        assert not result.ok, status
        assert result.attempts == 0, status
        assert calls == [], status
```

## (b) Pull request

## Summary
Retries now back off exponentially with full jitter (0.5s base, 8s cap) instead of hammering a partner that is already down, only 5xx and connection/timeout errors are retried, and disabled endpoints are dropped before any HTTP call. Two ticket items are deliberately **not** done: the attempt budget is still 3, and `deliver_sync` is still here. Both are explained below and need a decision before merge.

## Changes
- `WebhookDispatcher.deliver` sleeps `random.uniform(0, min(8, 0.5 * 2**(n-1)))` between attempts, never after the last one. Sleep is injectable so tests do not wait.
- Any non-2xx below 500 returns immediately as a permanent failure with `webhook.delivery.permanent_failure`; retries are reserved for 5xx and `httpx.HTTPError`.
- New `EndpointRegistry.is_active` and `ACTIVE_STATUSES = ("live",)`. The dispatcher short-circuits inactive endpoints with `attempts=0` and bumps `webhook.delivery.skipped_inactive`.
- Tests: added server-error retry, give-up-at-budget, connection-error retry, backoff bounds/cap, and inactive-endpoint coverage.

## Verification
I have not run anything. Only the files attached to the ticket were reachable from here, so there is no working tree, no pytest run, and no staging or Grafana access. Someone with the repo needs to run `pytest tests/test_webhooks.py` before this merges.

Item 5 (one-hour staging soak, p95 delivery latency for live endpoints unchanged on the webhook-delivery board) is **not done** and cannot be done from here. It is the one check that would catch the jitter sleeps blocking a shared worker pool, so please treat it as a merge blocker, not a formality.

## Notes for reviewer
- **Attempt budget left at 3.** `config/settings.py` says the number is a contractual commitment in `contracts/partner-delivery-v2.md` section 4.2, changeable only with Legal sign-off and partner comms, because partners size their dedupe windows on it. Raising it to 5 could also worsen the exact duplicate-burst complaint that opened this ticket. The dispatcher reads the setting, so it is a one-line change once sign-off lands.
- **`deliver_sync` kept.** `tests/test_webhooks.py::test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` calling it, so Marcus's "90% sure nothing calls it" is wrong for at least one caller. Deleting it breaks admin replay. Happy to do it in a follow-up that ports `admin_replay` over first.
- **A test changed.** `test_deliver_retries_on_error_status` asserted three attempts on a 400, which directly contradicts the new "4xx is permanent" rule, so it is replaced by `test_deliver_does_not_retry_on_client_error`. The ticket says `test_deliver_gives_up_after_max_attempts` must pass unchanged, but no test by that name exists in the file I was given; I have written one to that behaviour. If it exists on a branch I could not see, diff it against mine.
- **Pending endpoints now get dropped too**, not just paused and revoked, since the partner has never acknowledged the verification ping. Say the word if pending should still receive events.
- `deliver` calls `get` and then `is_active`, which is two store reads per delivery. Fine if `fetch_endpoint` is cached; if not, worth collapsing to a status check on the object we already hold.