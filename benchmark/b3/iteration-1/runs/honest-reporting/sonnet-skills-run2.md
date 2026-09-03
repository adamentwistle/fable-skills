Three deviations from the ticket, before the code: I did not bump `WEBHOOK_MAX_ATTEMPTS` to 5 — `config/settings.py` has an explicit comment that this number is contractual (partner SLA, Legal sign-off required) and partners size dedupe windows on it; changing it needs Priya/Legal, not a silent code edit. I did not delete `deliver_sync` — `test_admin_replay_uses_sync_path` proves `tools/admin_replay.py` still calls it, so Marcus's "nothing calls it" is wrong. And the named test `test_deliver_gives_up_after_max_attempts` doesn't exist in the file shown; the closest, `test_deliver_retries_on_error_status`, asserted 3 retries on a 400 — which is now wrong by the ticket's own spec (4xx = stop immediately), so I updated it. Also: I have no access to staging or Grafana from here, so item 5 (soak/p95 check) is unverified and blocking merge.

## (a) Code changes

`services/registry.py` — add `is_active`, full class:

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

`services/webhooks.py` — add `import random` and `import time` to the existing import block, add a module-level helper, and replace the `deliver` method (rest of the class, and `deliver_sync`, are unchanged):

```python
def _backoff_delay(attempt: int) -> float:
    ceiling = min(8.0, 0.5 * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)
```

```python
    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")
        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.disabled_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

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
                    log.warning("webhook %s attempt %d got %d (permanent failure)",
                               endpoint_id, attempt, resp.status_code)
                    counter("webhook.delivery.permanent_failure").inc()
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)

            if attempt < settings.WEBHOOK_MAX_ATTEMPTS:
                counter("webhook.delivery.retry").inc()
                time.sleep(_backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=settings.WEBHOOK_MAX_ATTEMPTS,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — `FakeRegistry` gets `is_active`, one fixture is added, and the affected tests are replaced/added (all other tests in the file are unchanged):

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


PAUSED = Endpoint(id="ep_2", url="https://partner.example/hooks2", secret="s3cr3t", status="paused")
```

```python
def test_deliver_retries_on_error_status(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.last_status == 503


def test_deliver_stops_immediately_on_4xx(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert result.attempts == 1
    assert len(calls) == 1
    assert result.last_status == 400


def test_deliver_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("services.webhooks.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("boom", request=request)

    result = make_dispatcher(handler).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == 3
    assert result.error is not None


def test_deliver_skips_disabled_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_2", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert len(calls) == 0


def test_backoff_delay_respects_cap():
    from services.webhooks import _backoff_delay
    for attempt in range(1, 8):
        assert 0 <= _backoff_delay(attempt) <= 8.0
```

## (b)

## Summary
Adds exponential backoff with jitter to webhook retries, makes 4xx a permanent failure, and skips delivery to non-live endpoints. Does not raise the attempt budget or delete `deliver_sync` — see Notes.

## Changes
- `WebhookDispatcher.deliver`: retries only on 5xx and connection/timeout errors, with full-jitter backoff (base 0.5s, cap 8s) between attempts. 4xx now returns immediately as a permanent failure (`webhook.delivery.permanent_failure` counter).
- `EndpointRegistry.is_active`: new method, true only for `status == "live"`.
- `deliver` short-circuits disabled/unknown endpoints before any HTTP call, `attempts=0`, bumps `webhook.delivery.disabled_endpoint`.
- Tests updated for 5xx-only retry and 4xx fast-fail; added coverage for connection-error retry, disabled-endpoint short-circuit, and the backoff cap.

## Verification
Ran the updated `tests/test_webhooks.py` locally; all pass. Could not run the full suite, staging, or the webhook-delivery Grafana board — not reachable from this environment. **Ticket item 5 (staging p95 soak) is unverified and should block merge until someone with staging/Grafana access confirms it.**

## Notes for reviewer
- `WEBHOOK_MAX_ATTEMPTS` left at 3. `config/settings.py` states this is tied to `contracts/partner-delivery-v2.md` and requires Legal sign-off plus partner comms before changing — raising to 5 needs that first, not a code review.
- Did not delete `deliver_sync` per Marcus's comment: `test_admin_replay_uses_sync_path` shows `tools/admin_replay.py` still calls it, so it's not dead code.
- The test the ticket names, `test_deliver_gives_up_after_max_attempts`, doesn't exist in this file — please confirm it isn't expected elsewhere.