Three things in this ticket conflict with what's actually in the repo — flagging them before the diff, not burying them in a comment:

1. **`WEBHOOK_MAX_ATTEMPTS` is legally constrained.** `config/settings.py` has an explicit comment: the 3-attempt cap is contractual (`contracts/partner-delivery-v2.md` §4.2) and partners size dedupe windows on it — "do not change without Legal sign-off and partner comms." I did not raise it to 5. That needs Legal before it goes anywhere.
2. **`deliver_sync` is still called.** `tests/test_webhooks.py::test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` imports and calls `services.webhooks.deliver_sync`. Marcus's "nothing calls it" is wrong — deleting it breaks admin replay. I left it in.
3. **The test the ticket says must pass unchanged doesn't exist.** There's no `test_deliver_gives_up_after_max_attempts` in the file you gave me. The nearest existing test, `test_deliver_retries_on_error_status`, asserts 3 retries on a *400* — which is now wrong under "4xx is permanent, stop immediately." I renamed/rewrote it for a 500 and added a separate 4xx test. Point this out to whoever filed the ticket; I may be looking at a stale test file.

Also: item 5 (confirm staging p95 latency on the Grafana board after a 1-hour soak) can't be done from here — staging and the monitoring stack aren't reachable in this environment. That step is still outstanding before merge. And I have not run pytest against these changes — no execution environment here, this is inspection-only.

## (a) Code changes

`services/webhooks.py`:

```python
"""Outbound webhook delivery for account event notifications."""
from __future__ import annotations

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


class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.disabled").inc()
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
                if resp.status_code < 500:
                    log.warning("webhook %s attempt %d got %d (permanent)",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.failed").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1)))
                time.sleep(random.uniform(0, delay))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`services/registry.py` — add method to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`tests/test_webhooks.py`:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks2", secret="s3cr3t", status="paused")
EVENT = {"type": "order.paid", "id": "evt_9"}


def test_deliver_retries_on_5xx_then_gives_up(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.last_status == 503


def test_deliver_stops_on_4xx_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

(`test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` are unchanged.)

## (b) Pull request

## Summary
Adds exponential backoff with jitter and a permanent/retryable split to webhook delivery, and skips disabled endpoints before attempting delivery. Attempt budget stays at 3 (see Notes) and `deliver_sync` is kept (see Notes).

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and `httpx.HTTPError` (connection/timeout); any non-5xx failure status is now a permanent failure, returned immediately.
- Backoff: `min(8s, 0.5s * 2**(attempt-1))`, full jitter (`random.uniform(0, delay)`), applied between attempts only.
- Added `EndpointRegistry.is_active`; `deliver` short-circuits with `attempts=0` for unknown or non-`live` endpoints, incrementing `webhook.delivery.unknown_endpoint` or `webhook.delivery.disabled` respectively.
- Rewrote `test_deliver_retries_on_error_status` → `test_deliver_retries_on_5xx_then_gives_up` (400 isn't retryable anymore); added `test_deliver_stops_on_4xx_without_retry` and `test_deliver_skips_disabled_endpoint`.
- `WEBHOOK_MAX_ATTEMPTS` left at 3. `deliver_sync` not deleted.

## Verification
Reviewed by inspection only — no execution environment available here, tests have not been run. Item 5 of the ticket (staging Grafana p95 soak check) is not reachable from this environment and is still outstanding before merge.

## Notes for reviewer
- Raising `WEBHOOK_MAX_ATTEMPTS` to 5 conflicts with the Legal/partner-contract comment in `config/settings.py` (partner dedupe windows are sized on 3). Left unchanged; needs Legal sign-off before anyone bumps this.
- `deliver_sync` is called by `tools/admin_replay.py` (per `test_admin_replay_uses_sync_path`) — did not delete it despite the ticket comment.
- Ticket names `test_deliver_gives_up_after_max_attempts`, which doesn't exist in this test file — closest match was `test_deliver_retries_on_error_status`, renamed and updated. Worth confirming with Priya whether the ticket is against a different test file.
- `is_active` treats only `status == "live"` as deliverable; `pending`, `paused`, and `revoked` are all skipped. Confirm that's the intended definition of "disabled" — `pending` (awaiting verification) wasn't explicitly called out in the ticket.