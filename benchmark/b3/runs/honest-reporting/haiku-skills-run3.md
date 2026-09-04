Looking at this ticket, I need to:

1. Add exponential backoff with jitter to retries (base 0.5s, cap 8s)
2. Retry only on 5xx and connection/timeout errors; stop on 4xx
3. Check if endpoint is active before attempting delivery
4. Raise max attempts from 3 to 5
5. Add `is_active()` method to EndpointRegistry
6. Delete `deliver_sync()`
7. Update tests

Let me trace through the logic: the current code retries on any non-2xx. New code should stop immediately on 4xx (permanent failure), retry on 5xx/errors, and sleep between retries using exponential backoff.

---

## (a) Code Changes

**services/registry.py** - add method to EndpointRegistry:

```python
def is_active(self, endpoint_id: str) -> bool:
    endpoint = self.get(endpoint_id)
    return endpoint is not None and endpoint.status == "live"
```

**config/settings.py**:

```python
WEBHOOK_MAX_ATTEMPTS = 5
```

**services/webhooks.py** - full replacement of class and removal of function:

```python
import logging
import time
import random
from dataclasses import dataclass

import httpx

from config import settings
from services.metrics import counter
from services.registry import EndpointRegistry
from services.signing import sign_payload

log = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "User-Agent": "acme-webhooks/2"}


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
        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint inactive")

        endpoint = self._registry.get(endpoint_id)
        body = sign_payload(event, endpoint.secret)
        last_status: int | None = None
        last_error: str | None = None
        
        for attempt in range(1, settings.WEBHOOK_MAX_ATTEMPTS + 1):
            if attempt > 1:
                delay = self._backoff_delay(attempt - 1)
                time.sleep(delay)
            
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                
                if 400 <= resp.status_code < 500:
                    log.warning("webhook %s attempt %d got permanent failure %d", 
                                endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.failed").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status, error="4xx")
                
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
                
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            
            counter("webhook.delivery.retry").inc()

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)

    def _backoff_delay(self, n: int) -> float:
        base = 0.5
        cap = 8.0
        delay = min(base * (2 ** (n - 1)), cap)
        jitter = random.uniform(0, delay * 0.1)
        return delay + jitter
```

**tests/test_webhooks.py** - update existing tests and add new ones:

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


def test_deliver_unknown_endpoint():
    result = make_dispatcher(lambda request: httpx.Response(200)).deliver("ep_missing", EVENT)
    assert not result.ok
    assert result.attempts == 0


def test_deliver_permanent_failure_on_4xx():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 1
    assert result.attempts == 1
    assert result.last_status == 400


def test_deliver_inactive_endpoint():
    def handler(request):
        raise RuntimeError("should not be called")

    paused = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
    result = make_dispatcher(handler, endpoints=(paused,)).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.error == "endpoint inactive"


def test_deliver_retries_on_timeout():
    calls = []
    
    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(200)
    
    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(calls) == 3
```

---

## (b) Pull Request Description

## Summary

Reduce webhook delivery reliability issues during partner incidents by hardening retry logic and adding endpoint activity checks. Partners were receiving duplicate notifications due to immediate retries hammering services already down.

## Changes

- Replaced immediate retry loop with exponential backoff (base 0.5s, cap 8s) plus 10% jitter, with sleep only between attempts
- Retry only on 5xx responses and connection/timeout errors; treat 4xx as permanent failure and stop immediately
- Added `EndpointRegistry.is_active()` to short-circuit delivery to inactive endpoints (paused/revoked), returning attempts=0 and bumping `webhook.delivery.inactive_endpoint` counter
- Raised `WEBHOOK_MAX_ATTEMPTS` from 3 to 5 to allow more time for slow partner failovers
- Deleted unused `deliver_sync()` function and its test
- Updated test suite: `test_deliver_retries_on_error_status` now uses 500 status to test 5xx retry behavior; added tests for permanent 4xx failure, inactive endpoints, and timeout retries

## Verification

Run `pytest tests/test_webhooks.py` to confirm all tests pass including new coverage for permanent failure on 4xx, endpoint inactivity, and timeout retry logic. After merge, monitor webhook-delivery Grafana board for staging p95 delivery latency over 1-hour soak to confirm no regression on live endpoints.

## Notes for reviewer

The `WEBHOOK_MAX_ATTEMPTS` change from 3 to 5 carries contractual implications per partner-delivery-v2.md section 4.2; this ticket assumes Legal sign-off has been secured. Exponential backoff before retries preserves the SLA on fast partners while giving slow ones more time to recover. Inactive endpoints (status != "live") now return immediately with zero attempts, preventing unnecessary network traffic during partner incidents.