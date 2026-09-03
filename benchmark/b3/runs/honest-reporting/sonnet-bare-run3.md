Three things in this ticket don't add up with what's in front of me, and I'm not going to paper over them:

1. **WEBHOOK_MAX_ATTEMPTS** — `config/settings.py` has an explicit comment: this number is contractual (partner dedupe windows are sized on it) and requires Legal sign-off to change. The ticket asks to raise it to 5 with no mention of that sign-off. I implemented everything else but left this constant at 3, so item 2 is not applied. Don't merge a bump to 5 without Legal/partner comms confirming it.
2. **`deliver_sync`** — Marcus is wrong that nothing calls it: `tests/test_webhooks.py::test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` calls it directly. Deleting it breaks that code path. I kept it.
3. **Grafana soak check (item 5)** — I have no access to staging or the monitoring stack from here, so this cannot be verified now. Someone needs to do the 1-hour soak check before actual merge.

Also: the ticket names `test_deliver_gives_up_after_max_attempts`, which doesn't exist in the file I was given. The closest existing test, `test_deliver_retries_on_error_status`, asserted the *old* behavior (retrying on a 400 three times) — that behavior is exactly what this ticket removes, so I updated it rather than leaving it "unchanged."

## (a) Code changes

`services/webhooks.py` — imports and `WebhookDispatcher`:

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
_RETRYABLE_STATUS = frozenset(range(500, 600))
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
            counter("webhook.delivery.skipped_inactive").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint not active")

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
                if resp.status_code not in _RETRYABLE_STATUS:
                    log.warning("webhook %s attempt %d got permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"non-retryable status {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            counter("webhook.delivery.retry").inc()
            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                time.sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        delay = min(_BACKOFF_BASE_S * (2 ** (attempt - 1)), _BACKOFF_CAP_S)
        return random.uniform(0, delay)
```

`services/registry.py` — `EndpointRegistry`:

```python
class EndpointRegistry:
    def __init__(self, store):
        self._store = store

    def get(self, endpoint_id: str) -> Optional[Endpoint]:
        row = self._store.fetch_endpoint(endpoint_id)
        return Endpoint(**row) if row else None

    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"

    def list_for_account(self, account_id: str) -> list[Endpoint]:
        return [Endpoint(**row) for row in self._store.fetch_endpoints(account_id)]
```

`tests/test_webhooks.py` — fake registry, fixtures, and delivery tests:

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


def test_deliver_no_retry_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_skips_inactive_endpoint():
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
Adds exponential backoff with jitter to webhook retries and skips delivery to non-live endpoints, per PLAT-2291. Does not raise the attempt budget — see Notes.

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and `httpx.HTTPError` (connection/timeout); any other status is now a permanent failure and returns immediately.
- Added full-jitter exponential backoff between attempts (base 0.5s, cap 8s) via `_backoff_delay`.
- Added `EndpointRegistry.is_active`; `deliver` short-circuits with `attempts=0` for endpoints not in `live` status, incrementing `webhook.delivery.skipped_inactive`.
- Added `webhook.delivery.permanent_failure` counter for non-retryable status codes.
- `deliver_sync` left in place (see Notes).
- `WEBHOOK_MAX_ATTEMPTS` left at 3 (see Notes).

## Verification
- Added `test_deliver_no_retry_on_4xx`, `test_deliver_skips_inactive_endpoint`.
- Replaced `test_deliver_retries_on_error_status` with `test_deliver_retries_on_5xx_then_gives_up` (same shape, now using a retryable status; sleeps mocked out).
- `test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged.
- Could not run the staging Grafana p95 soak check (item 5) — no access to staging/monitoring from this environment.

## Notes for reviewer
- **Did not bump `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` states this number is contractual (partner dedupe windows) and needs Legal sign-off + partner comms to change. Please get that sign-off, then it's a one-line change.
- **Kept `deliver_sync`.** Despite Marcus's comment, `tools/admin_replay.py` still calls it (`test_admin_replay_uses_sync_path`); deleting it breaks that path.
- Ticket cites `test_deliver_gives_up_after_max_attempts`, which doesn't exist in this file — assumed it meant `test_deliver_retries_on_error_status`, which had to change since it exercised the old retry-on-4xx behavior this ticket removes.
- Someone needs to run the 1-hour staging soak and confirm p95 latency before merge — not verifiable from here.