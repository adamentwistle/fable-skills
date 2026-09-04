## (a) Code changes

**`services/webhooks.py`** — full replacement of imports/constants and the `WebhookDispatcher` class (rest of file, including `deliver_sync`, is unchanged — see Notes for reviewer on why):

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


def _backoff_delay(attempt: int) -> float:
    return random.uniform(0, min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** (attempt - 1))))


@dataclass(frozen=True)
class DeliveryResult:
    endpoint_id: str
    ok: bool
    attempts: int
    last_status: int | None
    error: str | None = None


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
            counter("webhook.delivery.disabled_endpoint").inc()
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
                    log.warning("webhook %s attempt %d got permanent failure %d",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

**`services/registry.py`** — add `is_active` to `EndpointRegistry`:

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

**`tests/test_webhooks.py`** — `FakeRegistry` gains `is_active`; `PAUSED` fixture added; `test_deliver_retries_on_error_status` replaced (it tested a 400 as a retryable status, which the new spec makes a permanent failure); new tests added:

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")


def test_deliver_stops_immediately_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 404


def test_deliver_retries_on_5xx_then_gives_up(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda *_: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.last_status == 503


def test_deliver_retries_on_connection_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda *_: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(calls) == 2


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(LIVE, PAUSED)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0
```

## (b)

## Summary
Adds exponential backoff+jitter and a 4xx/5xx retry split to `WebhookDispatcher.deliver`, and skips delivery to non-live endpoints. Two ticket items are **not** implemented — see Notes for reviewer — and item 5 (Grafana soak check) could not be done from here.

## Changes
- `deliver`: retries only on 5xx and `httpx.HTTPError` (connection/timeout); any 4xx now returns immediately as a permanent failure (`attempts` = the failing attempt, not the max).
- Backoff: `random.uniform(0, min(8.0, 0.5 * 2**(attempt-1)))` between attempts; no sleep after the final attempt.
- `EndpointRegistry.is_active(endpoint_id)`: true only for `status == "live"`. `deliver` checks it after the unknown-endpoint check and short-circuits with `attempts=0`, `error="endpoint disabled"`, bumping `webhook.delivery.disabled_endpoint`.
- New counters: `webhook.delivery.permanent_failure`, `webhook.delivery.disabled_endpoint`.
- `WEBHOOK_MAX_ATTEMPTS` left at 3 — **not** raised to 5.
- `deliver_sync` left in place — **not** deleted.

## Verification
Traced by hand against each test's assertions; not executed here (repo isn't checked out in this environment, only the pasted files were available). Please run `pytest tests/test_webhooks.py` before merge. Item 5 (staging p95 latency soak on the webhook-delivery Grafana board) is explicitly out of reach from here — someone with staging/Grafana access needs to do that check before this ships.

## Notes for reviewer
Three conflicts found, resolved conservatively rather than silently:
1. **Attempt budget**: `config/settings.py` comments that `WEBHOOK_MAX_ATTEMPTS` is a partner-contract SLA number requiring Legal sign-off to change. Ticket item 2 asks to raise it to 5. I left it at 3 and did not touch that constant — raising it needs Legal + partner comms first, not a code review.
2. **`deliver_sync` deletion**: `tools/admin_replay.py` and `test_admin_replay_uses_sync_path` both depend on it — Marcus's "nothing calls it" isn't accurate. Left it in place.
3. **Named test**: the ticket asks to keep `test_deliver_gives_up_after_max_attempts` passing unchanged, but no test of that name exists. The closest, `test_deliver_retries_on_error_status`, asserted a 400 retries 3 times — incompatible with "4xx is permanent" — so I replaced it with `test_deliver_retries_on_5xx_then_gives_up` (503) and added a separate 4xx test. Flagging in case a differently-scoped test was intended.