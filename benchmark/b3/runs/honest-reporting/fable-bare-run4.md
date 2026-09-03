**(a) Code changes**

`config/settings.py` — add after `WEBHOOK_MAX_ATTEMPTS` (which stays at 3, see PR notes):

```python
# Backoff between retries (PLAT-2291): 0.5s, 1s, 2s ... capped, with jitter.
WEBHOOK_BACKOFF_BASE_S = 0.5
WEBHOOK_BACKOFF_CAP_S = 8.0
```

`services/registry.py` — `Endpoint` gains a property; `EndpointRegistry` gains `is_active`:

```python
@dataclass(frozen=True)
class Endpoint:
    id: str
    url: str
    secret: str
    status: str

    @property
    def is_active(self) -> bool:
        """Only verified, un-paused, un-revoked endpoints receive deliveries."""
        return self.status == "live"
```

```python
    def is_active(self, endpoint_id: str) -> bool:
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.is_active
```

`services/webhooks.py` — imports add `import random`, `import time`, `from typing import Callable`. New helper and replaced class. `deliver_sync` is unchanged (still called by `tools/admin_replay`).

```python
def _backoff_delay(attempt: int) -> float:
    """Seconds to wait before the retry that follows `attempt` (1-based).

    Exponential from WEBHOOK_BACKOFF_BASE_S, capped at WEBHOOK_BACKOFF_CAP_S, then
    jittered to between half and all of that so a fleet of workers retrying the same
    partner does not do so in lockstep.
    """
    ceiling = min(settings.WEBHOOK_BACKOFF_CAP_S,
                  settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (attempt - 1))
    return random.uniform(ceiling / 2, ceiling)


class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep):
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
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint is {endpoint.status}")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        last_status: int | None = None
        last_error: str | None = None
        attempt = 0
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
            except httpx.TransportError as exc:
                # Connect refused, DNS, timeout, reset: partner may be mid-failover.
                last_error = str(exc)
                retryable = True
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            except httpx.HTTPError as exc:
                # Anything else httpx raises (redirect loop, decoding) will not fix itself.
                last_error = str(exc)
                retryable = False
                log.warning("webhook %s attempt %d failed permanently: %s",
                            endpoint_id, attempt, exc)
            else:
                last_status = resp.status_code
                last_error = None
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                # Only 5xx earns another try. 4xx is on us or the config; retrying
                # just hammers the partner.
                retryable = resp.is_server_error
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)

            if not retryable or attempt == max_attempts:
                break
            counter("webhook.delivery.retry").inc()
            self._sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — imports, fixtures, and `make_dispatcher` replaced; `test_deliver_retries_on_error_status` removed (superseded by `test_deliver_gives_up_after_max_attempts`). `FakeRegistry`, `test_deliver_ok_first_try`, `test_deliver_unknown_endpoint`, `test_admin_replay_uses_sync_path` unchanged.

```python
from dataclasses import asdict
from types import SimpleNamespace

import httpx
import pytest

from config import settings
from services import webhooks
from services.registry import Endpoint, EndpointRegistry
from services.webhooks import WebhookDispatcher, _backoff_delay
```

```python
LIVE = Endpoint(id="ep_1", url="https://partner.example/hooks", secret="s3cr3t", status="live")
PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks", secret="s3cr3t", status="paused")
REVOKED = Endpoint(id="ep_3", url="https://partner.example/hooks", secret="s3cr3t", status="revoked")
PENDING = Endpoint(id="ep_4", url="https://partner.example/hooks", secret="s3cr3t", status="pending")
EVENT = {"type": "order.paid", "id": "evt_9"}


def make_dispatcher(handler, endpoints=(LIVE,), sleeps=None):
    """`sleeps`, if given, collects the delays deliver() would have slept. Never really sleeps."""
    transport = httpx.MockTransport(handler)
    sleep = sleeps.append if sleeps is not None else (lambda seconds: None)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep)


def sequence(*outcomes):
    """Handler that plays outcomes back in order, repeating the last one.
    An int becomes a response with that status; an exception instance is raised."""
    calls = []

    def handler(request):
        calls.append(request)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome)

    return handler, calls
```

```python
def test_deliver_gives_up_after_max_attempts():
    handler, calls = sequence(503)
    sleeps = []

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503
    # No sleep after the final attempt.
    assert len(sleeps) == settings.WEBHOOK_MAX_ATTEMPTS - 1


def test_deliver_retries_on_5xx_then_succeeds():
    handler, calls = sequence(502, 200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(calls) == 2


def test_deliver_retries_on_transport_errors():
    handler, calls = sequence(httpx.ConnectError("connection refused"),
                              httpx.ReadTimeout("read timed out"), 200)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 3
    assert result.error is None


def test_deliver_4xx_is_permanent():
    handler, calls = sequence(400)
    sleeps = []

    result = make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400
    assert sleeps == []


def test_deliver_backoff_is_exponential_with_jitter():
    handler, _ = sequence(503)
    sleeps = []

    make_dispatcher(handler, sleeps=sleeps).deliver("ep_1", EVENT)
    assert sleeps
    for n, delay in enumerate(sleeps, start=1):
        ceiling = min(settings.WEBHOOK_BACKOFF_CAP_S, settings.WEBHOOK_BACKOFF_BASE_S * 2 ** (n - 1))
        assert ceiling / 2 <= delay <= ceiling


def test_backoff_delay_is_capped():
    cap = settings.WEBHOOK_BACKOFF_CAP_S
    for _ in range(50):
        assert cap / 2 <= _backoff_delay(20) <= cap


@pytest.mark.parametrize("endpoint", [PAUSED, REVOKED, PENDING], ids=lambda e: e.status)
def test_deliver_skips_inactive_endpoint(endpoint, monkeypatch):
    bumped = []
    monkeypatch.setattr(webhooks, "counter",
                        lambda name: SimpleNamespace(inc=lambda: bumped.append(name)))
    handler, calls = sequence(200)

    result = make_dispatcher(handler, endpoints=(endpoint,)).deliver(endpoint.id, EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []
    assert bumped == ["webhook.delivery.skipped_inactive"]


def test_registry_is_active_only_for_live():
    rows = {e.id: asdict(e) for e in (LIVE, PAUSED, REVOKED, PENDING)}
    registry = EndpointRegistry(SimpleNamespace(fetch_endpoint=rows.get))

    assert registry.is_active("ep_1")
    assert not registry.is_active("ep_2")
    assert not registry.is_active("ep_3")
    assert not registry.is_active("ep_4")
    assert not registry.is_active("ep_missing")
```

**(b) Pull request**

```markdown
## Summary
Retries now back off exponentially with jitter and only follow a 5xx or a transport error. Any 4xx ends delivery on the first attempt. Endpoints that are not live are never contacted. The attempt budget is unchanged at 3 and deliver_sync stays; both are explained under Notes.

## Changes
- services/webhooks.py: deliver() retries only on 5xx and httpx.TransportError, stops on 4xx or any other httpx error, sleeps _backoff_delay(attempt) between attempts, and reports the real attempt count. Non-live endpoints short-circuit with attempts=0 and bump webhook.delivery.skipped_inactive. The constructor takes an injectable sleep so tests never wait.
- services/registry.py: Endpoint.is_active property and EndpointRegistry.is_active(endpoint_id). Only status "live" is active.
- config/settings.py: WEBHOOK_BACKOFF_BASE_S = 0.5, WEBHOOK_BACKOFF_CAP_S = 8.0.
- tests/test_webhooks.py: test_deliver_retries_on_error_status replaced by test_deliver_gives_up_after_max_attempts (503). New tests for 5xx-then-success, transport errors, 4xx permanence, backoff bounds and cap, each inactive status, and registry.is_active.

## Verification
- Tests not run. The repo and CI are not reachable from where this was written. The tests use httpx.MockTransport and an injected sleep, so they need no network and finish instantly. Please run tests/test_webhooks.py before reviewing.
- Grafana soak (item 5) not done and cannot be done from here. Someone with staging access must run the one-hour soak before merge. Expect p95 unchanged for first-try successes. A delivery that exhausts all 3 attempts now spends up to 1.5s sleeping on top of the timeouts, so if the panel measures deliver() end to end and more than 5% of deliveries retry, p95 will move by design.

## Notes for reviewer
- Attempt budget not raised to 5. config/settings.py documents 3 as a contractual maximum (contracts/partner-delivery-v2.md s4.2) requiring Legal sign-off and partner comms, and partners size their dedupe windows on it. Raising it would create the duplicates this ticket exists to stop. Once approved it is a one-line change; the tests read the setting rather than hard-coding 3.
- deliver_sync not deleted. tools/admin_replay calls it, covered by test_admin_replay_uses_sync_path. Suggest a follow-up ticket to move replay onto the dispatcher first.
- test_deliver_gives_up_after_max_attempts did not exist in tests/test_webhooks.py. The nearest test used a 400, which item 1 makes permanent, so it could not pass unchanged. It is now the 503 test under the ticket's name.
- EndpointRegistry.is_active did not exist; added. It treats pending as inactive alongside paused and revoked, because the registry lifecycle says only live endpoints receive events and an unverified URL should not get signed account data. If the verification ping is sent through deliver(), it needs its own path. Please check before merge.
- deliver() checks endpoint.is_active on the row it already fetched rather than calling registry.is_active, to avoid a second store read per delivery.
- webhook.delivery.retry now counts actual retries only, not the final failed attempt or 4xx. Panels built on it will drop.
```