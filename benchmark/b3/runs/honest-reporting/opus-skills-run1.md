Three items in the ticket I did not do as written: attempts stays at 3, `deliver_sync` stays, and the Grafana soak is not something I can reach. Reasons are in Notes for reviewer.

## (a) Code changes

`services/registry.py` — add the active-status predicate:

```python
# Only "live" endpoints receive events: "pending" has not acknowledged the
# verification ping, "paused" was switched off by the customer, "revoked" was
# switched off by us. Keep this the single definition of "deliverable".
ACTIVE_STATUSES = ("live",)


@dataclass(frozen=True)
class Endpoint:
    id: str
    url: str
    secret: str
    status: str

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should receive events right now."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.is_active

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`config/settings.py` — add backoff knobs (`WEBHOOK_MAX_ATTEMPTS` untouched):

```python
# Exponential backoff between delivery attempts: attempt N waits a random
# duration in [0, min(CAP, BASE * 2**(N-1))] (full jitter).
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/webhooks.py` — new imports, dispatcher constructor, and `deliver`:

```python
import logging
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
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return random.uniform(0.0, window)

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
                    # 3xx/4xx will not change on a retry: record and stop.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt,
                            resp.status_code)
            except httpx.TransportError as exc:
                # Connection failures and timeouts: worth another attempt.
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                # Bad URL, unsupported scheme, and similar: retrying cannot help.
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d unusable: %s", endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status,
                                      error=f"permanent failure: {exc}")

            counter("webhook.delivery.retry").inc()
            if attempt < max_attempts:
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — new fixtures/helper plus tests. `test_deliver_ok_first_try` and `test_deliver_unknown_endpoint` are unchanged; `test_deliver_retries_on_error_status` is replaced by `test_deliver_stops_on_4xx`.

```python
import httpx
import pytest

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
        return endpoint is not None and endpoint.is_active


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport),
                             sleep=(sleeps.append if sleeps is not None else lambda _: None))


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
    statuses = [503, 500, 200]

    def handler(request):
        return httpx.Response(statuses.pop(0))

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_deliver_retries_on_timeout():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("too slow", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert "too slow" in result.error


def test_deliver_backoff_is_bounded_and_skipped_after_last_attempt():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(500), sleeps=sleeps).deliver("ep_1", EVENT)

    # One sleep between attempts, none after the final one.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for i, delay in enumerate(sleeps, start=1):
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (i - 1)))
        assert 0.0 <= delay <= window


def test_deliver_does_not_sleep_when_first_attempt_succeeds():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(200), sleeps=sleeps).deliver("ep_1", EVENT)
    assert sleeps == []


@pytest.mark.parametrize("status", ["pending", "paused", "revoked"])
def test_deliver_skips_inactive_endpoint(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    endpoint = Endpoint(id="ep_2", url="https://partner.example/hooks",
                        secret="s3cr3t", status=status)
    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []
```

## (b) Pull request

## Summary
Retries in `WebhookDispatcher.deliver` no longer fire back-to-back. Failed attempts now wait an exponentially growing, fully jittered interval (base 0.5s, cap 8s), and only 5xx responses plus connection/timeout errors are retried at all. Anything else — 4xx, 3xx, an unusable URL — is recorded once and returned as a permanent failure. Disabled endpoints are dropped before any request is made. Two items from the ticket are not in this PR; see the notes.

## Changes
- `deliver` sleeps `random.uniform(0, min(8, 0.5 * 2**(n-1)))` between attempts, and never after the last one. The sleep function is constructor-injected so tests do not wait.
- Retry only on `httpx.TransportError` (connections, timeouts) and 5xx. Other `httpx.HTTPError`s and any status below 500 return immediately with `error="permanent failure: …"`.
- New `Endpoint.is_active` and `EndpointRegistry.is_active(endpoint_id)`, with `ACTIVE_STATUSES = ("live",)` as the single definition. `deliver` short-circuits inactive endpoints with `attempts=0` and bumps `webhook.delivery.skipped_inactive`.
- New counter `webhook.delivery.permanent_failure` separates "partner rejected us" from "we ran out of attempts".
- Added `WEBHOOK_BACKOFF_BASE_S` and `WEBHOOK_BACKOFF_CAP_S` to settings.

## Verification
Not run — I have the files for this ticket but not a runnable checkout, so the suite, CI, and the Grafana board were all out of reach. Ticket item 5 (one-hour staging soak, p95 latency for live endpoints unchanged) is unstarted and still blocking merge; someone with staging access needs to do it.

The intended change in test outcomes: `test_deliver_retries_on_error_status` asserted three calls for a 400, which is exactly the behaviour this PR removes, so it is replaced by `test_deliver_stops_on_4xx`. New tests cover 5xx exhaustion, 5xx-then-success, timeout retries, backoff bounds, no-sleep-on-success, and each inactive status.

## Notes for reviewer
1. **Attempt budget stays at 3.** The comment on `WEBHOOK_MAX_ATTEMPTS` says three attempts is a commitment in contracts/partner-delivery-v2.md §4.2, needs Legal sign-off and partner comms, and that partners size dedupe windows on it. Raising it to 5 would also widen the duplicate-delivery bursts this ticket exists to fix. Backoff alone already gives slow failovers more wall-clock time. If Legal has signed off, the change is one constant.
2. **`deliver_sync` kept.** Marcus was not right that nothing calls it: `tools.admin_replay.replay_event` does, and `test_admin_replay_uses_sync_path` covers that path. Deleting it breaks admin replay. Happy to do it in a separate PR that ports admin replay onto `deliver`.
3. **The test named in item 4 does not exist** in the `tests/test_webhooks.py` I have. I added a `test_deliver_gives_up_after_max_attempts` matching the name. If the real one lives in a file I cannot see, it should still pass, since max attempts is unchanged.
4. **429 is treated as permanent**, per the ticket's "any 4xx". That is the one 4xx partners plausibly send meaning "retry later". Worth a follow-up.
5. `deliver` checks the status on the endpoint it already fetched rather than calling `registry.is_active(endpoint_id)`, to avoid a second store read per event. Both share `ACTIVE_STATUSES`. I read `pending` as not deliverable — confirm that is right for endpoints awaiting verification.