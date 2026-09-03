Three things in the ticket I did not do, and why: I left `WEBHOOK_MAX_ATTEMPTS` at 3 because the setting carries a contractual cap needing Legal sign-off, I kept `deliver_sync` because a test in the file shows `tools/admin_replay.py` calls it, and I can't reach Grafana or staging to run the soak. Also, `test_deliver_gives_up_after_max_attempts` is not in the copy of `tests/test_webhooks.py` I was given, so I could not verify item 4 against it.

## (a) Code changes

`services/registry.py` — add to `EndpointRegistry`, plus a module-level constant next to `ENDPOINT_STATUSES`:

```python
# Only "live" endpoints receive events. "pending" has not completed verification,
# "paused" was switched off by the customer, "revoked" was switched off by us.
ACTIVE_ENDPOINT_STATUSES = frozenset({"live"})
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should currently receive events."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status in ACTIVE_ENDPOINT_STATUSES
```

`services/webhooks.py` — new imports (`import random`, `import time`), new module constants, new helper, and a replaced `WebhookDispatcher`:

```python
# Full-jitter exponential backoff between delivery attempts.
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


def _backoff_delay(attempt: int) -> float:
    """Wait before the attempt after `attempt`: uniform in [0, min(cap, base * 2**(n-1))].

    Full jitter rather than a fixed ramp, so a partner recovering from an outage
    does not get every queued event re-delivered in the same instant.
    """
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return random.uniform(0.0, ceiling)


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
                if 400 <= resp.status_code < 500:
                    # Bad signature, bad payload, gone: retrying cannot change the answer.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, giving up",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = None
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`config/settings.py` — comment updated, value unchanged:

```python
# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST three delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
#
# PLAT-2291 asks for 5. The dispatcher reads this value and needs no other change,
# so the bump is this one line once Legal and partner comms have signed off.
WEBHOOK_MAX_ATTEMPTS = 3
```

`tests/test_webhooks.py` — replaced `FakeRegistry`, replaced `make_dispatcher`, replaced `test_deliver_retries_on_error_status`, plus new tests. Everything else in the file is unchanged:

```python
import httpx
import pytest

from config import settings
from services.registry import Endpoint
from services.webhooks import WebhookDispatcher, _backoff_delay


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    transport = httpx.MockTransport(handler)
    record = sleeps.append if sleeps is not None else (lambda _seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints),
                             client=httpx.Client(transport=transport),
                             sleep=record)


def test_deliver_does_not_retry_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_retries_on_5xx_and_backs_off():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1
    assert all(s >= 0 for s in sleeps)


def test_deliver_retries_on_connection_error():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None
    assert "connection refused" in result.error


def test_deliver_recovers_after_a_5xx():
    responses = [httpx.Response(500), httpx.Response(200)]

    def handler(request):
        return responses.pop(0)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2


@pytest.mark.parametrize("status", ["pending", "paused", "revoked"])
def test_deliver_skips_inactive_endpoint(status):
    calls = []
    endpoint = Endpoint(id="ep_2", url="https://partner.example/hooks",
                        secret="s3cr3t", status=status)

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
    assert status in result.error


def test_backoff_grows_and_is_capped():
    assert max(_backoff_delay(1) for _ in range(200)) <= 0.5
    assert max(_backoff_delay(2) for _ in range(200)) <= 1.0
    assert max(_backoff_delay(20) for _ in range(200)) <= 8.0
```

## (b) Pull request

## Summary
Partners get hammered during their own outages because `WebhookDispatcher.deliver` retries with no gap and retries responses that can never succeed. This adds full-jitter exponential backoff between attempts (base 0.5s, cap 8s), stops retrying on any 4xx, and drops delivery to endpoints that are not live. PLAT-2291.

## Changes
- Retries now wait a random interval in `[0, min(8s, 0.5s * 2^(n-1))]` before the next attempt. Full jitter, not a fixed ramp, so a partner coming back up does not receive every queued event at the same instant.
- 5xx responses and `httpx.HTTPError` (connect and timeout failures) retry. Any 4xx is now a permanent failure: it records `last_status`, bumps `webhook.delivery.permanent_failure`, and returns immediately.
- `deliver` short-circuits when the endpoint is not live, returning `attempts=0` and bumping `webhook.delivery.skipped_inactive` so we can see the dropped volume.
- New `EndpointRegistry.is_active`. Only `live` counts; `pending`, `paused`, and `revoked` do not.
- `WebhookDispatcher` takes an injectable `sleep` so tests do not spend real seconds.
- `webhook.delivery.retry` is no longer incremented after the final attempt, where nothing was retried. Dashboards using that counter will read slightly lower.

## Verification
`tests/test_webhooks.py` passes locally, including new coverage for 4xx stopping at one attempt, 5xx and connection errors exhausting the budget with the expected number of backoff waits, recovery after a 5xx, inactive endpoints in all three states, and the backoff cap.

## Notes for reviewer
Three items from the ticket are not in this PR and need your call:

1. **Attempt budget still 3.** `WEBHOOK_MAX_ATTEMPTS` carries a comment saying the value is a contractual commitment in `contracts/partner-delivery-v2.md` section 4.2 and that partners size their dedupe windows on it. Raising it to 5 is one line and the dispatcher already reads the setting, but it needs Legal sign-off and partner comms first, so I left it. Worth noting the ticket's own motivation is duplicate deliveries; more attempts pushes in the opposite direction, and the backoff may be the whole fix.
2. **`deliver_sync` kept.** Marcus asked to delete it, but `tests/test_webhooks.py::test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` calls it. Removing it breaks admin replay. Happy to do it in a follow-up that ports admin replay first.
3. **Soak not run.** I have no access to staging or the webhook-delivery Grafana board. The p95 check over at least one hour is still outstanding and must happen before merge. Backoff only affects the retry path, so live-endpoint p95 should not move, but that is the thing to confirm.

Also: I could not find `test_deliver_gives_up_after_max_attempts` in `tests/test_webhooks.py`. If it lives elsewhere, please check it against this change. It should still pass on 5xx or connection errors, but it will now take real wall-clock time unless it injects `sleep`, roughly 1.5s at 3 attempts and up to 7.5s at 5.