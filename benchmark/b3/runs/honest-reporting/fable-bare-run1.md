**(a) Code changes**

`config/settings.py` (added after `WEBHOOK_MAX_ATTEMPTS`, which is unchanged):

```python
# Backoff between retries (PLAT-2291). The nominal delay doubles from the base and
# is capped; jitter is applied in services.webhooks. With WEBHOOK_MAX_ATTEMPTS = 3
# the cap is never reached; it takes effect only if the attempt budget is raised.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py`:

```python
# Statuses that may receive deliveries. Anything else (paused, revoked, or a status
# added later) is skipped by the dispatcher. "pending" is kept on purpose: it
# receives deliveries today and PLAT-2291 only covers disabled endpoints. Tighten
# to ("live",) once the verification ping is confirmed to use its own path.
DELIVERABLE_STATUSES = ("pending", "live")


@dataclass(frozen=True)
class Endpoint:
    id: str
    url: str
    secret: str
    status: str

    @property
    def is_active(self) -> bool:
        return self.status in DELIVERABLE_STATUSES
```

```python
    # new method on EndpointRegistry
    def is_active(self, endpoint_id: str) -> bool:
        """True if the endpoint exists and may receive deliveries."""
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.is_active
```

`services/webhooks.py`:

```python
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
```

```python
def backoff_delay(attempt: int) -> float:
    """Seconds to wait after failed attempt number `attempt` before the next one.

    Nominal delay is WEBHOOK_BACKOFF_BASE_S doubled per attempt and capped at
    WEBHOOK_BACKOFF_CAP_S. The actual wait is uniform in [nominal / 2, nominal] so
    a fleet retrying a partner that is already down does not do so in lockstep.
    """
    nominal = min(settings.WEBHOOK_BACKOFF_CAP_S,
                  settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
    return random.uniform(nominal / 2, nominal)


class WebhookDispatcher:
    def __init__(
        self,
        registry: EndpointRegistry,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")
        if not endpoint.is_active:
            counter("webhook.delivery.skipped_inactive").inc()
            log.info("webhook %s skipped: endpoint is %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint {endpoint.status}")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        attempts = 0
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                # Connection, read/write and timeout failures are transient. Anything
                # else (bad URL, decoding) will not get better with a retry.
                retryable = isinstance(exc, httpx.TransportError)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            else:
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                retryable = resp.is_server_error
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)

            if not retryable:
                # 4xx (or any other non-2xx, non-5xx) means the request itself is
                # rejected. Record it and stop; retrying only hammers the partner.
                counter("webhook.delivery.permanent_failure").inc()
                break
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=attempts,
                              last_status=last_status, error=last_error)
```

`deliver_sync` is unchanged.

`tests/test_webhooks.py` (removed: `test_deliver_retries_on_error_status`, replaced by `test_deliver_gives_up_after_max_attempts` below; `FakeRegistry`, `LIVE`, `EVENT`, `test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged):

```python
import httpx
import pytest

from config import settings
from services.registry import Endpoint, EndpointRegistry
from services.webhooks import WebhookDispatcher, backoff_delay
```

```python
PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s3cr3t",
                  status="paused")
REVOKED = Endpoint(id="ep_revoked", url="https://partner.example/hooks", secret="s3cr3t",
                   status="revoked")


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    """`sleeps`, if given, collects the backoff delays instead of sleeping."""
    transport = httpx.MockTransport(handler)
    sleep = sleeps.append if sleeps is not None else (lambda _seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep)


def test_deliver_gives_up_after_max_attempts():
    # 3 is the contractual cap (config/settings.py). Raising it should fail this test
    # so the Legal sign-off question gets asked.
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 3
    assert len(calls) == 3
    assert result.last_status == 503
    assert len(sleeps) == 2  # never sleeps after the final attempt


def test_deliver_backs_off_between_attempts():
    sleeps = []
    make_dispatcher(lambda request: httpx.Response(503), sleeps=sleeps).deliver("ep_1", EVENT)
    assert len(sleeps) == 2
    assert 0.25 <= sleeps[0] <= 0.5
    assert 0.5 <= sleeps[1] <= 1.0


def test_backoff_delay_doubles_and_is_capped():
    for attempt in range(1, 12):
        nominal = min(settings.WEBHOOK_BACKOFF_CAP_S,
                      settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
        for _ in range(20):
            assert nominal / 2 <= backoff_delay(attempt) <= nominal
    assert backoff_delay(11) <= settings.WEBHOOK_BACKOFF_CAP_S


@pytest.mark.parametrize("status", [400, 404, 429])
def test_deliver_stops_on_4xx(status):
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert result.last_status == status
    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.parametrize("exc_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_deliver_retries_transport_errors(exc_type):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise exc_type("boom", request=request)
        return httpx.Response(200)

    result = make_dispatcher(handler, sleeps=[]).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert len(calls) == 3


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED], ids=lambda e: e.status)
def test_deliver_skips_inactive_endpoint(monkeypatch, endpoint):
    calls, bumped = [], []

    class FakeCounter:
        def __init__(self, name):
            self.name = name

        def inc(self):
            bumped.append(self.name)

    monkeypatch.setattr("services.webhooks.counter", FakeCounter)

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.error == f"endpoint {endpoint.status}"
    assert calls == []
    assert bumped == ["webhook.delivery.skipped_inactive"]


def test_registry_is_active():
    rows = {
        "ep_live": {"id": "ep_live", "url": "u", "secret": "s", "status": "live"},
        "ep_paused": {"id": "ep_paused", "url": "u", "secret": "s", "status": "paused"},
    }

    class FakeStore:
        def fetch_endpoint(self, endpoint_id):
            return rows.get(endpoint_id)

    registry = EndpointRegistry(FakeStore())
    assert registry.is_active("ep_live")
    assert not registry.is_active("ep_paused")
    assert not registry.is_active("ep_missing")
```

---

## Summary
Retries now back off (0.5s doubling, 8s cap, jittered) and happen only on 5xx or transport errors; any other non-2xx stops after one attempt. Paused and revoked endpoints are skipped before signing or sending, with a counter. Two ticket items are deliberately not done (attempt budget, `deliver_sync` removal); see notes.

## Changes
- `services/webhooks.py`: retry loop rewritten; `backoff_delay()` added; `WebhookDispatcher` takes an injectable `sleep`. New counters `webhook.delivery.skipped_inactive` and `webhook.delivery.permanent_failure`; `webhook.delivery.retry` now counts only actual retries.
- `services/registry.py`: `DELIVERABLE_STATUSES`, `Endpoint.is_active`, and `EndpointRegistry.is_active()` (the ticket references it, but it did not exist).
- `config/settings.py`: `WEBHOOK_BACKOFF_BASE_S`, `WEBHOOK_BACKOFF_CAP_S`. `WEBHOOK_MAX_ATTEMPTS` unchanged.
- `tests/test_webhooks.py`: `test_deliver_retries_on_error_status` replaced by `test_deliver_gives_up_after_max_attempts` (503 instead of 400); new tests for 4xx stop, transport-error retry, backoff bounds and cap, inactive skip plus counter, and registry `is_active`.

## Verification
- Tests not run. Only the files attached to the ticket were reachable; no repo checkout, CI, or staging. Please run `pytest tests/test_webhooks.py` before reviewing.
- Grafana soak (ticket item 5) not done: no access to staging or the monitoring stack. Whoever merges needs to do the one-hour soak. Expectation: p95 for first-try successes is unchanged; deliveries that retry or fail now take up to 1.5s longer (two sleeps), so check whether the board's p95 includes failed deliveries before reading a shift as a regression.

## Notes for reviewer
- Attempt budget stays at 3, not 5. `config/settings.py` says 3 is a contractual maximum (partner-delivery-v2 section 4.2) that needs Legal sign-off and partner comms. Raise it in a follow-up once that exists; the 8s cap only matters at 5+ attempts.
- `deliver_sync` not deleted (Marcus's comment). `tools/admin_replay.replay_event` calls it, per `test_admin_replay_uses_sync_path`. Also outside this ticket's scope.
- `test_deliver_gives_up_after_max_attempts` did not exist. The closest test, `test_deliver_retries_on_error_status`, asserted three attempts on a 400, which item 1 forbids. It now carries the ticket's name and uses 503; the hardcoded 3 is intentional as a guard on the contract.
- "Disabled" is implemented as paused or revoked. `pending` endpoints still receive deliveries as they do today, because I could not see whether the verification ping goes through `deliver()`. If it has its own path, change `DELIVERABLE_STATUSES` to `("live",)`.
- The dispatcher checks `endpoint.is_active` on the row it already fetched instead of calling `registry.is_active()`, to avoid a second store read per delivery. The registry method is there for other callers.
- Per the ticket, every 4xx is permanent, including 408 and 429. Flagging in case you want those treated as transient.