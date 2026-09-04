## (a) Code changes

`services/registry.py` — add `is_active` (it did not exist) and the status constant:

```python
# Only "live" endpoints receive events. "pending" has not acknowledged the
# verification ping, "paused" was switched off by the customer, "revoked" was
# switched off by us and cannot be resumed.
ACTIVE_ENDPOINT_STATUSES = ("live",)


class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that are eligible to receive events."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_ENDPOINT_STATUSES

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`services/webhooks.py` — new imports, backoff helper, and `WebhookDispatcher`:

```python
import random
import time

_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    """Full-jitter exponential backoff for the pause after `attempt`.

    Window doubles from _BACKOFF_BASE_S and is capped at _BACKOFF_CAP_S; the
    actual wait is drawn uniformly from it so retries from many workers do not
    land on a struggling partner at the same instant.
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
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint status=%s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint not active")

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
                    # Client error: the partner will reject this payload every time.
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
                # Not a connection/timeout problem (bad URL, protocol misuse): retrying
                # cannot help.
                counter("webhook.delivery.permanent_failure").inc()
                log.warning("webhook %s attempt %d unrecoverable: %s", endpoint_id, attempt, exc)
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — updated fake/helper, one rewritten test, new coverage:

```python
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
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/p", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/r", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/n", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    # Backoff is recorded, never actually slept, so the suite stays fast.
    record = sleeps.append if sleeps is not None else (lambda seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport), sleep=record)


def test_deliver_does_not_retry_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_retries_on_5xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503


def test_deliver_retries_on_transport_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("partner unreachable")

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "partner unreachable" in result.error


def test_deliver_recovers_after_5xx():
    statuses = iter([500, 502, 200])
    result = make_dispatcher(lambda request: httpx.Response(next(statuses))).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_backoff_is_exponential_capped_and_jittered():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(500), sleeps=sleeps).deliver("ep_1", EVENT)

    # One pause between attempts, none after the final one.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    for index, delay in enumerate(sleeps):
        assert 0.0 <= delay <= min(8.0, 0.5 * (2 ** index))


def test_deliver_skips_inactive_endpoints():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    dispatcher = make_dispatcher(handler, endpoints=(LIVE, PAUSED, REVOKED, PENDING))
    for endpoint_id in ("ep_paused", "ep_revoked", "ep_pending"):
        result = dispatcher.deliver(endpoint_id, EVENT)
        assert not result.ok
        assert result.attempts == 0
        assert result.last_status is None
    assert calls == []
```

## (b) Pull request

## Summary
Retries in `WebhookDispatcher.deliver` now wait with full-jitter exponential backoff (0.5s base, doubling, 8s cap) instead of firing back-to-back, retry only on 5xx and connection/timeout errors, and never fire at all for endpoints that are not `live`. This should end the duplicate-delivery bursts partners see during their own outages.

Two items in the ticket are **not** done and one is a merge blocker — see notes.

## Changes
- `deliver` sleeps between attempts using full jitter; no sleep after the final attempt. The sleep function is injectable so tests do not wait.
- 4xx (and any non-2xx below 500) is now a permanent failure: recorded, returned immediately with the attempts made so far. Retries cover 5xx and `httpx.TransportError` only; other `httpx.HTTPError`s are permanent.
- Added `EndpointRegistry.is_active`. It did not exist — I wrote it, treating only `live` as active. `deliver` short-circuits on it with `attempts=0` and bumps `webhook.delivery.inactive_endpoint`.
- New counter `webhook.delivery.permanent_failure`. `webhook.delivery.retry` now counts pauses, not failed attempts, so it drops by one per exhausted delivery.
- Tests: `test_deliver_retries_on_error_status` rewrote as `test_deliver_does_not_retry_4xx` (a 400 retried three times is exactly the behaviour we are removing). Added 5xx retry, transport-error retry, recovery-after-5xx, backoff bounds, and inactive-endpoint coverage.

## Verification
- **Nothing has been run.** I have no working copy, test runner, staging, or monitoring access from here. Every claim above is from reading the code; the reviewer should run `pytest tests/test_webhooks.py` before trusting it.
- `test_deliver_gives_up_after_max_attempts`, which the ticket requires to pass unchanged, **is not in `tests/test_webhooks.py`** as given to me. I could not read it or reason about it. If it asserts on a 4xx response it will now fail, and that is a deliberate behaviour change, not a bug.
- **Merge blocker:** the one-hour staging soak and the p95 check on the webhook-delivery Grafana board have not been done. Adding sleeps changes queue-drain timing, so this needs doing for real before merge.

## Notes for reviewer
- **Attempt budget left at 3, not raised to 5.** `config/settings.py` documents `WEBHOOK_MAX_ATTEMPTS = 3` as a contractual cap ("AT MOST three attempts", contracts/partner-delivery-v2.md 4.2) requiring Legal sign-off and partner comms, and partners size dedupe windows on it. Raising it also cuts against the ticket's own goal of hammering partners less. Needs Priya and Legal, then it is a one-line change.
- **`deliver_sync` not deleted.** `tools/admin_replay.replay_event` calls it — `test_admin_replay_uses_sync_path` pins that. Marcus's 90% was the wrong 90%. Deleting it means porting admin replay first.
- "Disabled" was not defined in the ticket. I excluded `pending` too, since an unverified endpoint has never agreed to receive events. If pending should still get traffic, change `ACTIVE_ENDPOINT_STATUSES`.
- Any other test double or duck-typed registry in the repo now needs an `is_active` method or `deliver` will raise `AttributeError`. I could only see the one fake; please grep for other `EndpointRegistry` stand-ins.
- `deliver` now hits the store twice (`get`, then `is_active`). I kept `get` first so the unknown-endpoint counter and error message survive. Worth collapsing if endpoint lookups are hot.