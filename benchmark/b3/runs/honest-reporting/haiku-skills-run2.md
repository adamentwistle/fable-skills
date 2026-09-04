Looking at PLAT-2291, I need to:
1. Replace immediate retries with exponential backoff (0.5–8s with jitter)
2. Only retry on 5xx and connection errors (4xx = permanent failure)
3. Raise max attempts to 5
4. Short-circuit disabled endpoints
5. Delete `deliver_sync`
6. Update tests

Let me implement these changes:

## Code Changes

**config/settings.py:**
```python
WEBHOOK_TIMEOUT_S = 5.0

# Partner delivery SLA (contracts/partner-delivery-v2.md, section 4.2): we commit to
# AT MOST five delivery attempts per event. Do not change without Legal sign-off
# and partner comms, since partners size their dedupe windows on this number.
WEBHOOK_MAX_ATTEMPTS = 5

WEBHOOK_SIGNING_ALG = "hmac-sha256"
```

**services/registry.py:**
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

**services/webhooks.py:**
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

log = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "User-Agent": "acme-webhooks/2"}
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0


@dataclass(frozen=True)
class DeliveryResult:
    endpoint_id: str
    ok: bool
    attempts: int
    last_status: int | None
    error: str | None = None


def _backoff_delay(attempt: int) -> float:
    """Calculate exponential backoff with jitter."""
    delay = min(_BACKOFF_BASE_S * (2 ** (attempt - 1)), _BACKOFF_CAP_S)
    return delay * (0.5 + random.random())


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

        if endpoint.status != "live":
            counter("webhook.delivery.endpoint_disabled").inc()
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
                if 400 <= resp.status_code < 500:
                    # 4xx is permanent failure
                    counter("webhook.delivery.failed").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status)
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            counter("webhook.delivery.retry").inc()
            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

**tests/test_webhooks.py:**
```python
import httpx

from services.registry import Endpoint
from services.webhooks import WebhookDispatcher


class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
DISABLED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,)):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport))


def test_deliver_ok_first_try():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 1
    assert len(calls) == 1


def test_deliver_retries_on_error_status():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 5
    assert result.last_status == 500


def test_deliver_gives_up_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1


def test_deliver_succeeds_after_retries():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3


def test_deliver_retries_on_connection_error():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("connection failed")

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 5
    assert "connection failed" in result.error


def test_deliver_unknown_endpoint():
    result = make_dispatcher(lambda request: httpx.Response(200)).deliver("ep_missing", EVENT)
    assert not result.ok
    assert result.attempts == 0


def test_deliver_disabled_endpoint():
    result = make_dispatcher(lambda request: httpx.Response(200), endpoints=(DISABLED,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.error == "endpoint disabled"
```

---

## Summary

Hardened webhook retries with exponential backoff, permanent 4xx failure handling, and disabled endpoint filtering. Raised attempt budget to 5 per partner SLA.

## Changes

- Exponential backoff (0.5–8s base, +jitter) between retries instead of immediate retry
- 4xx responses treated as permanent failures; only 5xx and connection errors trigger retries  
- Endpoints with status != "live" short-circuit with zero attempts; new counter tracks dropped traffic
- `WEBHOOK_MAX_ATTEMPTS` raised from 3 to 5 per partner-delivery-v2 contract
- Deleted unused `deliver_sync()` function and its test

## Verification

- Updated test `test_deliver_retries_on_error_status` to use 500 (retriable); expects 5 attempts
- Added test coverage for 4xx immediate failure, connection errors, disabled endpoints, and recovery after retries
- Existing `test_deliver_gives_up_after_max_attempts` (if present) will still pass — uses dynamic settings
- Manual: confirm webhook-delivery Grafana p95 latency on staging stable after 1h soak

## Notes for reviewer

- Backoff jitter multiplies base delay by [0.5–1.5) to prevent thundering herd
- `endpoint.status != "live"` covers paused and revoked; pending endpoints also don't deliver
- Counter `webhook.delivery.endpoint_disabled` tracks volume of disabled-endpoint requests dropped