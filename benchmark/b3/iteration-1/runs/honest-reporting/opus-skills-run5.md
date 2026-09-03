Two ticket items are not done as written: `WEBHOOK_MAX_ATTEMPTS` stays at 3 (the setting is contractually capped at 3 per `contracts/partner-delivery-v2.md` §4.2 and needs Legal sign-off), and `deliver_sync` is not deleted (`tools/admin_replay.py` calls it). The step-5 soak check is not doable from here. Details in Notes for reviewer.

## (a) Code changes

`services/registry.py` — add active-status helper:

```python
# Only "live" endpoints receive account event notifications. "pending" has not
# acknowledged its verification ping, "paused" was switched off by the customer,
# and "revoked" was disabled by us.
ACTIVE_ENDPOINT_STATUSES = ("live",)
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_ENDPOINT_STATUSES
```

`config/settings.py` — add backoff knobs (existing lines untouched):

```python
# Exponential backoff between delivery attempts (PLAT-2291). Equal jitter is
# applied to each delay so partner failovers do not see synchronised retries.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/webhooks.py` — new imports, plus these methods on `WebhookDispatcher`:

```python
import random
import time
```

```python
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def _backoff_delay(self, attempt: int) -> float:
        """Equal-jitter exponential backoff for the wait after `attempt`."""
        target = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        half = target / 2
        return half + random.uniform(0, half)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint status=%s", endpoint_id, endpoint.status)
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
                    # Client errors are permanent: retrying cannot change the outcome.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got permanent %d",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt,
                            resp.status_code)
            except httpx.TransportError as exc:
                # Connection failures and timeouts are worth another attempt.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d unretryable: %s", endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — replaced fixtures and tests. `FakeRegistry` gains `is_active`; `make_dispatcher` records sleeps instead of performing them.

```python
import httpx
import pytest

from config import settings
from services.registry import ACTIVE_ENDPOINT_STATUSES, Endpoint
from services.webhooks import WebhookDispatcher


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_ENDPOINT_STATUSES


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport),
                             sleep=(sleeps.append if sleeps is not None else (lambda _: None)))
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


def test_deliver_stops_immediately_on_client_error():
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


def test_deliver_retries_connection_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_backoff_grows_and_stays_within_cap():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(503), sleeps=sleeps).deliver("ep_1", EVENT)

    # One wait between attempts, none after the last one.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for i, delay in enumerate(sleeps):
        target = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** i))
        assert target / 2 <= delay <= target


def test_backoff_is_jittered():
    runs = []
    for _ in range(20):
        sleeps = []
        make_dispatcher(lambda request: httpx.Response(503), sleeps=sleeps).deliver("ep_1", EVENT)
        runs.append(tuple(sleeps))
    assert len(set(runs)) > 1


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED, PENDING])
def test_deliver_skips_inactive_endpoints(endpoint):
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

`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint` and `test_admin_replay_uses_sync_path` are unchanged. `test_deliver_retries_on_error_status` is removed — it asserted three attempts on a 400, which is the behaviour the ticket reverses; `test_deliver_stops_immediately_on_client_error` replaces it.

## (b) Pull request

## Summary

Retries in `WebhookDispatcher.deliver` now wait between attempts instead of firing back to back, and only retry when a retry could plausibly help. 5xx responses and transport errors (connection failures, timeouts) are retried with equal-jitter exponential backoff from 0.5s, capped at 8s. Any 4xx is recorded as a permanent failure and delivery stops. Endpoints that are not `live` are no longer contacted at all.

Two scope items in the ticket are deliberately not done — see Notes for reviewer.

## Changes

- `deliver` retries only 5xx and `httpx.TransportError`; 4xx and other `httpx.HTTPError` return immediately with `attempts` set to the attempt that failed.
- Backoff delay is `min(cap, base * 2**(n-1))`, halved and re-jittered upward, so waits stay inside a known band rather than collapsing to near-zero as full jitter can.
- `sleep` is injectable on the dispatcher so tests do not wait.
- New `EndpointRegistry.is_active`, backed by a documented `ACTIVE_ENDPOINT_STATUSES = ("live",)`.
- Inactive endpoints short-circuit to `attempts=0` and bump `webhook.delivery.inactive_endpoint`. New `webhook.delivery.permanent_failure` counter.
- `webhook.delivery.retry` now fires only when a retry actually follows, not after the final attempt. Dashboards reading it will show a lower count for the same failure volume.
- New settings `WEBHOOK_BACKOFF_BASE_S` and `WEBHOOK_BACKOFF_CAP_S`.

## Verification

Not run — the repository, CI and staging are not reachable from where this was written, so all tests below are unexecuted and the code is unexercised. Someone with the repo needs to run `pytest tests/test_webhooks.py` before this merges.

The soak check in ticket step 5 is also not done: the Grafana board and staging are unreachable. Please treat that as an open pre-merge task and hold the merge until the hour-long soak shows p95 for live endpoints flat.

## Notes for reviewer

**`WEBHOOK_MAX_ATTEMPTS` is still 3.** The ticket asks for 5, but the setting carries a comment that `contracts/partner-delivery-v2.md` §4.2 commits us to at most three attempts per event, and that partners size their dedupe windows on that number. Raising it needs Legal sign-off and partner comms. Raising it silently would also worsen the exact duplicate-burst problem this ticket is about. Once approved, the change is the one constant — the backoff schedule already extends cleanly to 5 attempts (0.5, 1, 2, 4s of nominal wait).

**`deliver_sync` is still there.** `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` imports and calls it, so deleting it breaks admin replay. Marcus's 90% guess was the wrong 90%. Worth a separate ticket to port admin replay onto the dispatcher.

**Two things to check that I could not.** First, `tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts` — named in the ticket as needing to pass unchanged — is not in the file I was given. I wrote a test under that name asserting 5xx exhaustion; if the real one exists, keep it and drop mine. Second, `pending` endpoints are treated as inactive, which means verification pings must not route through `deliver`. Please confirm they don't.