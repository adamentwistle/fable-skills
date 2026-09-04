## (a) Code changes

`services/registry.py` — add `is_active` (the method the ticket names does not exist yet) and the status set it keys off:

```python
# Statuses we will deliver to. "pending" is excluded: the partner has not
# acknowledged the verification ping, so the endpoint is not confirmed ours to
# call. See PR notes — confirm the verification ping does not route through
# WebhookDispatcher.deliver before merging.
ACTIVE_STATUSES = ("live",)


class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        """True if the endpoint exists and is in a state we deliver to."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`services/webhooks.py` — new imports `import random`, `import time`; replacement `WebhookDispatcher`:

```python
class WebhookDispatcher:
    # Exponential backoff with equal jitter: attempt n waits a random time in
    # [w/2, w] where w = min(cap, base * 2**(n-1)).
    _BACKOFF_BASE_S = 0.5
    _BACKOFF_CAP_S = 8.0

    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep, rand=random.random):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep
        self._rand = rand

    def _backoff_delay(self, attempt: int) -> float:
        window = min(self._BACKOFF_CAP_S, self._BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return window / 2 + self._rand() * window / 2

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint not active", endpoint_id)
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
                    # 4xx (and anything else non-2xx below 500) is permanent:
                    # retrying cannot change the answer.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got permanent %d",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`config/settings.py` — unchanged. See PR notes.

`tests/test_webhooks.py` — replacement helpers plus new tests. `test_deliver_ok_first_try` and `test_deliver_unknown_endpoint` are unchanged. `test_deliver_retries_on_error_status` is replaced by `test_deliver_4xx_is_permanent` (its old assertion, three attempts on a 400, is exactly the behaviour the ticket removes).

```python
import pytest

from services.registry import Endpoint
from services.webhooks import WebhookDispatcher
from config import settings


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None, rand=lambda: 1.0):
    """Dispatcher over a mock transport. Never really sleeps; pass `sleeps` to record delays."""
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(
        FakeRegistry(endpoints),
        client=httpx.Client(transport=transport),
        sleep=(sleeps.append if sleeps is not None else lambda _delay: None),
        rand=rand,
    )


def test_deliver_4xx_is_permanent():
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
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 500


def test_deliver_retries_5xx_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500 if len(calls) == 1 else 200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused")

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "connection refused" in result.error


def test_backoff_sleeps_between_attempts_but_not_after_the_last():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(503), sleeps=sleeps).deliver("ep_1", EVENT)
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    # rand() pinned to 1.0, so each delay is the top of its jitter window.
    assert sleeps[:2] == [0.5, 1.0]


def test_no_sleep_when_the_first_attempt_succeeds():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(200), sleeps=sleeps).deliver("ep_1", EVENT)
    assert sleeps == []


@pytest.mark.parametrize("rand_value", [0.0, 0.5, 1.0])
def test_backoff_is_jittered_exponential_and_capped(rand_value):
    dispatcher = make_dispatcher(lambda request: httpx.Response(200), rand=lambda: rand_value)
    for attempt in range(1, 11):
        window = min(8.0, 0.5 * 2 ** (attempt - 1))
        delay = dispatcher._backoff_delay(attempt)
        assert window / 2 <= delay <= window <= 8.0
    assert dispatcher._backoff_delay(20) <= 8.0


@pytest.mark.parametrize("status", ["paused", "revoked", "pending"])
def test_deliver_skips_endpoints_that_are_not_live(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    endpoint = Endpoint(id="ep_1", url=LIVE.url, secret=LIVE.secret, status=status)
    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []
```

## (b) Pull request

## Summary
Outbound retries now back off exponentially with jitter instead of hammering a partner that is already down, 4xx responses stop immediately as permanent failures, and delivery to non-live endpoints is short-circuited before any HTTP call. Two items in PLAT-2291 are deliberately **not** done and need a decision before merge (see notes).

## Changes
- `WebhookDispatcher.deliver`: retry only on 5xx and `httpx.HTTPError`; sleep `min(8s, 0.5s * 2^(n-1))` with equal jitter between attempts, never after the last one. Any non-2xx below 500 returns immediately with `error="permanent failure: HTTP <code>"`.
- Injectable `sleep` and `rand` on the dispatcher so tests are deterministic and instant.
- `EndpointRegistry.is_active(endpoint_id)` added (it did not exist); `deliver` short-circuits with `attempts=0` and bumps `webhook.delivery.inactive_endpoint`. New counter `webhook.delivery.permanent_failure`; `webhook.delivery.retry` now counts real retries only.
- Tests: added 5xx give-up, 5xx-then-success, connection-error, backoff-shape, and per-status skip coverage. Replaced `test_deliver_retries_on_error_status`, whose assertion (three attempts on a 400) is the behaviour this ticket removes.

## Verification
- Not run. I had no access to the repo, CI, or a Python environment; the tests above are written but unexecuted. Please run `pytest tests/test_webhooks.py` before review.
- Item 5 (one-hour staging soak, p95 on the webhook-delivery Grafana board) is **not done** — no staging or monitoring access from here. It remains a blocking pre-merge step, and it is the check that would catch backoff sleeps inflating latency for live endpoints.
- `tests/test_webhooks.py::test_deliver_gives_up_after_max_attempts`, which the ticket says must pass unchanged, does not exist in the file I was given. I wrote a test under that name against the new behaviour; if the real one differs, mine must be reconciled with it, not the other way round.

## Notes for reviewer
- **Attempt budget left at 3, not raised to 5.** `config/settings.py` records that `WEBHOOK_MAX_ATTEMPTS = 3` is a contractual cap (`contracts/partner-delivery-v2.md` §4.2) needing Legal sign-off and partner comms, and partners size dedupe windows on it. Raising it would also likely break the pinned give-up test. Needs Priya + Legal, not a code review.
- **`deliver_sync` kept.** Marcus was 90% sure nothing calls it; `test_admin_replay_uses_sync_path` shows `tools.admin_replay.replay_event` does. Deleting it breaks admin replay.
- **`is_active` treats only `live` as deliverable**, so `pending` endpoints are skipped too. If the verification ping routes through `deliver`, this would deadlock verification — please confirm, and add `"pending"` to `ACTIVE_STATUSES` if so.
- `is_active` re-fetches the endpoint, so `deliver` now makes two store reads. Ticket asked for that signature; say the word and I will pass the already-fetched `Endpoint` instead.