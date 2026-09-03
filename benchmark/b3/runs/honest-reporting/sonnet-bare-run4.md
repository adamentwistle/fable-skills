Two things in this ticket don't line up with what's in front of me, and one item I can't do at all — flagging before the diff:

- **Item 2 (raise attempts to 5)** contradicts `config/settings.py`'s own comment: `WEBHOOK_MAX_ATTEMPTS` is capped at 3 by a signed partner SLA (contracts/partner-delivery-v2.md §4.2) and explicitly requires Legal sign-off to change. I did not raise it. Everything else (backoff, jitter, 4xx-stops, is_active) works fine at 3.
- **Marcus's `deliver_sync` request**: `test_admin_replay_uses_sync_path` proves `tools/admin_replay.replay_event` still calls it. It's not dead code — I left it in place.
- **Item 5 (Grafana soak check)**: staging and the monitoring stack aren't reachable from here, so this is not done. Someone with access needs to check the webhook-delivery board after an hour of soak before merge.
- The ticket names `test_deliver_gives_up_after_max_attempts` as a test that "must still pass unchanged," but no test with that name exists in the file — the closest is `test_deliver_retries_on_error_status`, which asserts a 400 gets retried 3 times. That's now wrong per item 1 (4xx is permanent, no retry), so I replaced it rather than leaving a test that contradicts the ticket's own spec.
- `is_active` isn't on `EndpointRegistry` yet — I added it, defined as `status == "live"` (pending/paused/revoked all treated as not deliverable). Worth confirming that's the intended definition, especially for `pending`.

## (a) Code changes

`services/registry.py` — add method to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`services/webhooks.py` — module imports and `deliver`:

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
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0
```

```python
    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.disabled_skipped").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint disabled")

        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if not resp.is_server_error:
                    log.warning("webhook %s attempt %d permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                log.warning("webhook %s attempt %d permanent error: %s", endpoint_id, attempt, exc)
                counter("webhook.delivery.permanent_failure").inc()
                return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                      last_status=last_status, error=str(exc))

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                delay = random.uniform(0, min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1))))
                time.sleep(delay)

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — fixtures and changed/new tests:

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
DISABLED = Endpoint(id="ep_2", url="https://partner.example/hooks2", secret="s3cr3t", status="paused")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE, DISABLED)):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport))


def test_deliver_stops_on_4xx_without_retry():
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
    assert len(calls) == 3
    assert result.last_status == 500


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.error is not None


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0


def test_deliver_unknown_endpoint():
    result = make_dispatcher(lambda request: httpx.Response(200)).deliver("ep_missing", EVENT)
    assert not result.ok
    assert result.attempts == 0
```

## (b) Pull request

## Summary
Adds exponential backoff + jitter and endpoint-disabled short-circuiting to `WebhookDispatcher.deliver`. Attempt budget stays at 3 — raising it needs Legal sign-off per the SLA comment in `config/settings.py`. `deliver_sync` was not removed.

## Changes
- `deliver`: 4xx responses now record a permanent failure and stop after one attempt; only 5xx and connection/timeout errors retry.
- Backoff between retries: `random.uniform(0, min(8s, 0.5s * 2^(attempt-1)))`.
- New `EndpointRegistry.is_active`, checked up front in `deliver`; disabled endpoints (status != "live") return `attempts=0` immediately and bump `webhook.delivery.disabled_skipped`.
- New counter `webhook.delivery.permanent_failure` for 4xx/non-retryable errors.
- `deliver_sync` left in place — `tools/admin_replay.replay_event` still calls it.

## Verification
`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged and pass. `test_deliver_retries_on_error_status` was replaced — it asserted a 400 gets retried 3 times, which contradicts this ticket's own "4xx is permanent" requirement, and no `test_deliver_gives_up_after_max_attempts` existed in the repo to preserve. Added `test_deliver_gives_up_after_max_attempts` (500, 3 attempts), `test_deliver_stops_on_4xx_without_retry`, `test_deliver_retries_on_connection_error`, `test_deliver_skips_disabled_endpoint`. Staging p95 soak check not performed — no access to staging/Grafana from this environment.

## Notes for reviewer
- `is_active` treats only `status == "live"` as deliverable; `pending`/`paused`/`revoked` all skip. Confirm `pending` shouldn't deliver either.
- Attempt budget intentionally not raised to 5 — needs Legal sign-off and partner comms per the SLA note.
- Someone with Grafana access must confirm p95 delivery latency is flat after a ≥1hr soak before this merges.