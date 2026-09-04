## (a) Code changes

`services/webhooks.py` — add to the top-of-file imports:

```python
import random
import time
```

`services/webhooks.py` — replace `WebhookDispatcher`:

```python
class WebhookDispatcher:
    _BACKOFF_BASE_S = 0.5
    _BACKOFF_CAP_S = 8.0

    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                sleep=None):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep or time.sleep

    def _backoff_delay(self, attempt: int) -> float:
        ceiling = min(self._BACKOFF_CAP_S, self._BACKOFF_BASE_S * (2 ** (attempt - 1)))
        return random.uniform(0, ceiling)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="endpoint not active")

        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

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
                    log.warning("webhook %s attempt %d permanent failure %d",
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
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`services/registry.py` — replace `EndpointRegistry`:

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

`tests/test_webhooks.py` — replace the fake, constants, and test functions below (`test_deliver_unknown_endpoint` and `test_admin_replay_uses_sync_path` are unchanged, not reprinted):

```python
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
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleep=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep or (lambda s: None))


def test_deliver_ok_first_try():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 1
    assert len(calls) == 1


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


def test_deliver_retries_on_5xx_then_gives_up():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503


def test_deliver_retries_on_connection_error():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status is None


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

## (b) Pull request description

## Summary
Adds exponential backoff with jitter to webhook retries and skips delivery to non-live endpoints. Does not raise the attempt budget, and does not delete `deliver_sync` — both conflict with facts in the repo.

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and `httpx.HTTPError`; any 4xx now returns immediately as a permanent failure. Backoff is full-jitter, base 0.5s, cap 8s, injectable `sleep` for tests.
- Checks `EndpointRegistry.is_active` (new method, `status == "live"`) before any attempt; inactive/unknown endpoints short-circuit with `attempts=0` and their own counters (`inactive_endpoint`, `unknown_endpoint`, `permanent_failure`).
- Tests updated: the old `test_deliver_retries_on_error_status` asserted 3 retries on a 400, which is now wrong behavior — replaced with a 4xx-no-retry test and a 5xx-exhausts-budget test, plus new coverage for connection errors and disabled endpoints.

## Verification
Ran the updated `tests/test_webhooks.py` locally (all pass, sleep stubbed out so no real delay). Could not run the full suite, staging, or CI — not reachable from this environment.

## Notes for reviewer
- **Did not bump `WEBHOOK_MAX_ATTEMPTS` to 5.** `config/settings.py` caps it at 3 under a documented partner SLA (contracts/partner-delivery-v2.md §4.2) requiring Legal sign-off and partner comms first. Raising it needs that sign-off before this merges — flagging rather than deciding it myself.
- **Did not delete `deliver_sync`.** `tests/test_webhooks.py::test_admin_replay_uses_sync_path` and `tools/admin_replay.py` both call it — Marcus's "nothing calls it" isn't correct. Worth confirming with him before anyone removes it.
- Ticket names `test_deliver_gives_up_after_max_attempts` as a must-pass test; no test with that name exists in the file I was given, so I couldn't verify it unchanged — closest match was `test_deliver_retries_on_error_status`, which I had to change (see above).
- Item 5, the Grafana p95 soak check, is not done — I have no access to staging or the monitoring stack from here. Someone with access needs to run that soak before merge.