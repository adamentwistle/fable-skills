## (a) Code changes

`config/settings.py` — add (leave `WEBHOOK_MAX_ATTEMPTS` at 3, see notes):

```python
# Full-jitter exponential backoff between delivery attempts.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` — add after `ENDPOINT_STATUSES`:

```python
# Only "live" endpoints receive events. "pending" has not completed verification,
# "paused" was switched off by the customer, "revoked" was switched off by us.
ACTIVE_STATUSES = frozenset({"live"})
```

`services/registry.py` — add to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_STATUSES
```

`services/webhooks.py` — new imports alongside the existing ones:

```python
import random
import time
```

`services/webhooks.py` — replacement for `WebhookDispatcher.__init__` and `deliver`, plus a new helper:

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep, rand=random.random):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep
        self._rand = rand

    def _backoff_delay(self, attempt: int) -> float:
        """Full-jitter backoff: uniform in [0, min(cap, base * 2**(attempt-1))]."""
        window = min(settings.WEBHOOK_BACKOFF_CAP_S,
                     settings.WEBHOOK_BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return window * self._rand()

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
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    # 4xx (and any other non-5xx failure) is permanent: retrying cannot help.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, giving up",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.RequestError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — replacement for `FakeRegistry`, the fixtures block, `make_dispatcher`, and `test_deliver_retries_on_error_status`; the other three existing tests are unchanged:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s", status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s", status="revoked")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(
        FakeRegistry(endpoints),
        client=httpx.Client(transport=transport),
        # Record instead of sleeping, and pin jitter to the top of the window.
        sleep=(sleeps.append if sleeps is not None else (lambda _delay: None)),
        rand=lambda: 1.0,
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
```

`tests/test_webhooks.py` — new tests:

```python
import pytest

from config import settings


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


def test_deliver_retries_on_5xx_then_succeeds():
    statuses = [503, 500, 200]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(statuses[len(calls) - 1])

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectTimeout("timed out", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "timed out" in result.error


def test_backoff_grows_and_is_capped():
    sleeps = []
    dispatcher = make_dispatcher(lambda request: httpx.Response(500), sleeps=sleeps)
    dispatcher.deliver("ep_1", EVENT)

    # One sleep between attempts, none after the last one.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert sleeps == sorted(sleeps)
    assert all(0.0 <= d <= settings.WEBHOOK_BACKOFF_CAP_S for d in sleeps)
    # rand() is pinned to 1.0, so each delay is the top of its window.
    assert sleeps[0] == pytest.approx(settings.WEBHOOK_BACKOFF_BASE_S)


def test_backoff_window_is_capped_for_late_attempts():
    dispatcher = make_dispatcher(lambda request: httpx.Response(500))
    assert dispatcher._backoff_delay(20) == pytest.approx(settings.WEBHOOK_BACKOFF_CAP_S)


def test_jitter_is_applied_below_the_window():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    dispatcher = WebhookDispatcher(FakeRegistry([LIVE]), client=httpx.Client(transport=transport),
                                   sleep=lambda _delay: None, rand=lambda: 0.25)
    assert dispatcher._backoff_delay(1) == pytest.approx(settings.WEBHOOK_BACKOFF_BASE_S * 0.25)


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

## (b) Pull request

## Summary
Outbound webhook retries now back off exponentially with full jitter (base 0.5s, cap 8s) instead of hammering a partner in a tight loop, retry only on 5xx and connection/timeout errors, and skip endpoints that are not live. Closes PLAT-2291 items 1, 3 and 4. Items 2 and 5 are **not** done — see notes; this should not merge until both are resolved.

## Changes
- `WebhookDispatcher.deliver` sleeps `uniform(0, min(8s, 0.5 * 2**(n-1)))` between attempts, and no longer sleeps after the final attempt.
- Any non-5xx failure response (so all 4xx) is now a permanent failure: it returns immediately with `attempts` set to the attempt that failed, and bumps `webhook.delivery.permanent_failure`.
- Retries are caught on `httpx.RequestError` (connect/timeout/network) rather than the broader `httpx.HTTPError`.
- New `EndpointRegistry.is_active`; `deliver` short-circuits non-live endpoints with `attempts=0` and bumps `webhook.delivery.skipped_inactive`.
- `sleep` and `rand` are injectable on the dispatcher so tests are deterministic and instant.
- New settings `WEBHOOK_BACKOFF_BASE_S` / `WEBHOOK_BACKOFF_CAP_S`.
- Tests: `test_deliver_retries_on_error_status` replaced by `test_deliver_stops_on_4xx` (it asserted three attempts on a 400, which is exactly the behaviour this ticket removes); added coverage for 5xx retry, connection-error retry, backoff growth/cap/jitter, and skipping paused/revoked/pending endpoints.

## Verification
- **Nothing has been executed.** I have no repo, CI, staging or monitoring access from here, so the test suite has not been run. Please run `pytest tests/test_webhooks.py` before review; that is the first thing a reviewer should do.
- The ticket asks that `test_deliver_gives_up_after_max_attempts` still pass unchanged. **No such test exists** in `tests/test_webhooks.py`. I have written one under that name against the current attempt budget; if the intended test lives elsewhere, point me at it and I will re-check my version against it.
- Item 5 (one-hour staging soak, p95 on the webhook-delivery Grafana board) is **not done** and is a merge blocker. Backoff adds sleep to the failure path only, so live-endpoint p95 should be flat, but that is a prediction, not a measurement.

## Notes for reviewer
- **Attempt budget left at 3, deliberately.** `config/settings.py` documents `WEBHOOK_MAX_ATTEMPTS = 3` as a contractual cap from `contracts/partner-delivery-v2.md` §4.2, needing Legal sign-off and partner comms, because partners size their dedupe windows on it. Raising it to 5 would send more duplicates to partners — the problem this ticket is fixing. Change the one constant once Legal signs off; nothing else needs to change.
- **`deliver_sync` kept.** `tools/admin_replay.replay_event` calls it, and `test_admin_replay_uses_sync_path` covers that. Deleting it breaks admin replay.
- **Judgement call:** `is_active` treats only `live` as active, so `pending` endpoints are dropped too, not just `paused`/`revoked`. Verification-unacknowledged endpoints should not get real events. If pending should instead be queued, say so and I will split it out.
- The unknown-endpoint check still runs before the active check, so `webhook.delivery.unknown_endpoint` keeps its current meaning.
- `webhook.delivery.retry` now counts gaps between attempts, not failed attempts — it drops by one per fully-failed delivery. Check no dashboard alerts on its absolute value.