Three things in the ticket conflict with what's in the repo, so I did not do them blind: the attempt budget stays at 3 (the config comment binds it to a partner contract needing Legal sign-off), `deliver_sync` stays (a test proves `tools/admin_replay` calls it), and `test_deliver_gives_up_after_max_attempts` does not exist in the file I was given — I wrote it. Details in Notes for reviewer.

## (a) Code changes

`config/settings.py` — add (leave `WEBHOOK_MAX_ATTEMPTS = 3` and its comment untouched):

```python
# Backoff between delivery attempts: full jitter, delay ~ U(0, min(cap, base * 2**(n-1))).
WEBHOOK_RETRY_BASE_S = 0.5
WEBHOOK_RETRY_CAP_S = 8.0
```

`services/registry.py` — add to `EndpointRegistry`:

```python
    def is_active(self, endpoint_id: str) -> bool:
        """True only for endpoints that should receive events.

        'live' is the only status that receives events: 'pending' has not
        acknowledged the verification ping, 'paused' was turned off by the
        customer, 'revoked' was turned off by us.
        """
        endpoint = self.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"
```

`services/webhooks.py` — replace `WebhookDispatcher` (module needs `import random` and `import time`; `deliver_sync` is unchanged and not reprinted):

```python
class WebhookDispatcher:
    def __init__(self, registry: EndpointRegistry, client: httpx.Client | None = None,
                 sleep=time.sleep):
        self._registry = registry
        self._client = client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_S)
        self._sleep = sleep

    def _backoff_delay(self, attempt: int) -> float:
        """Full jitter: uniform in [0, min(cap, base * 2**(attempt-1))]."""
        ceiling = min(settings.WEBHOOK_RETRY_CAP_S,
                      settings.WEBHOOK_RETRY_BASE_S * (2 ** (attempt - 1)))
        return random.uniform(0.0, ceiling)

    def deliver(self, endpoint_id: str, event: dict) -> DeliveryResult:
        endpoint = self._registry.get(endpoint_id)
        if endpoint is None:
            counter("webhook.delivery.unknown_endpoint").inc()
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error="unknown endpoint")

        if not self._registry.is_active(endpoint_id):
            counter("webhook.delivery.inactive_endpoint").inc()
            log.info("webhook %s skipped: endpoint status %s", endpoint_id, endpoint.status)
            return DeliveryResult(endpoint_id, ok=False, attempts=0, last_status=None,
                                  error=f"endpoint not active (status={endpoint.status})")

        body = sign_payload(event, endpoint.secret)
        max_attempts = settings.WEBHOOK_MAX_ATTEMPTS
        last_status: int | None = None
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.post(endpoint.url, content=body, headers=_HEADERS)
                last_status = resp.status_code
                if resp.is_success:
                    counter("webhook.delivery.ok").inc()
                    return DeliveryResult(endpoint_id, ok=True, attempts=attempt,
                                          last_status=last_status)
                if resp.status_code < 500:
                    # Retry only on 5xx; anything else (4xx, and 3xx we did not follow)
                    # will not change on a repeat, so record and stop.
                    counter("webhook.delivery.permanent_failure").inc()
                    log.warning("webhook %s attempt %d got %d, not retrying",
                                endpoint_id, attempt, resp.status_code)
                    return DeliveryResult(endpoint_id, ok=False, attempts=attempt,
                                          last_status=last_status,
                                          error=f"permanent failure: HTTP {resp.status_code}")
                last_error = f"HTTP {resp.status_code}"
                log.warning("webhook %s attempt %d got %d", endpoint_id, attempt, resp.status_code)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("webhook %s attempt %d failed: %s", endpoint_id, attempt, exc)
            if attempt < max_attempts:
                counter("webhook.delivery.retry").inc()
                self._sleep(self._backoff_delay(attempt))

        counter("webhook.delivery.failed").inc()
        return DeliveryResult(endpoint_id, ok=False, attempts=max_attempts,
                              last_status=last_status, error=last_error)
```

`tests/test_webhooks.py` — add `from config import settings` at the top; replace the helpers and `test_deliver_retries_on_error_status`, and add the rest. Other existing tests are unchanged.

```python
class FakeRegistry:
    def __init__(self, endpoints):
        self._by_id = {e.id: e for e in endpoints}

    def get(self, endpoint_id):
        return self._by_id.get(endpoint_id)

    def is_active(self, endpoint_id):
        endpoint = self._by_id.get(endpoint_id)
        return endpoint is not None and endpoint.status == "live"


class FakeSleep:
    """Records backoff delays instead of spending them."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


PAUSED = Endpoint(id="ep_paused", url="https://partner.example/hooks", secret="s3cr3t",
                  status="paused")
PENDING = Endpoint(id="ep_pending", url="https://partner.example/hooks", secret="s3cr3t",
                   status="pending")


def make_dispatcher(handler, endpoints=(LIVE,), sleep=None):
    transport = httpx.MockTransport(handler)
    return WebhookDispatcher(FakeRegistry(endpoints), client=httpx.Client(transport=transport),
                             sleep=sleep or FakeSleep())


def test_deliver_stops_on_4xx():
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
        return httpx.Response(503)

    sleep = FakeSleep()
    result = make_dispatcher(handler, sleep=sleep).deliver("ep_1", EVENT)
    assert not result.ok
    assert len(calls) == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.attempts == settings.WEBHOOK_MAX_ATTEMPTS
    assert result.last_status == 503
    # One sleep between attempts, none after the last one.
    assert len(sleep.delays) == settings.WEBHOOK_MAX_ATTEMPTS - 1


def test_deliver_retries_on_connection_error_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("connect timed out", request=request)
        return httpx.Response(200)

    sleep = FakeSleep()
    result = make_dispatcher(handler, sleep=sleep).deliver("ep_1", EVENT)
    assert result.ok
    assert result.attempts == 2
    assert len(sleep.delays) == 1


def test_backoff_delays_are_jittered_and_capped():
    dispatcher = make_dispatcher(lambda request: httpx.Response(200))
    for attempt in range(1, 12):
        ceiling = min(settings.WEBHOOK_RETRY_CAP_S,
                      settings.WEBHOOK_RETRY_BASE_S * (2 ** (attempt - 1)))
        for _ in range(50):
            delay = dispatcher._backoff_delay(attempt)
            assert 0.0 <= delay <= ceiling


def test_deliver_skips_paused_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PAUSED,)).deliver("ep_paused", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert result.last_status is None
    assert calls == []


def test_deliver_skips_pending_endpoint():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    result = make_dispatcher(handler, endpoints=(PENDING,)).deliver("ep_pending", EVENT)
    assert not result.ok
    assert result.attempts == 0
    assert calls == []
```

## (b) Pull request

## Summary
Retries in `WebhookDispatcher.deliver` no longer hammer a partner that is already down. Failed attempts now wait an exponentially growing, fully jittered delay (base 0.5s, cap 8s), and we only retry the things that can succeed on a repeat: 5xx responses and connection/timeout errors. A 4xx is recorded as a permanent failure and stops the loop immediately. Endpoints that are not live are skipped before any request goes out. PLAT-2291.

## Changes
- `deliver` sleeps `U(0, min(8s, 0.5s * 2^(n-1)))` between attempts, and never after the final one.
- Non-5xx failures return straight away with the attempt count so far and a `webhook.delivery.permanent_failure` counter.
- New `EndpointRegistry.is_active`: true only for status `live`. `deliver` short-circuits on it with `attempts=0` and bumps `webhook.delivery.inactive_endpoint`.
- `WebhookDispatcher` takes an injectable `sleep` so tests do not spend real seconds.
- `WEBHOOK_RETRY_BASE_S` and `WEBHOOK_RETRY_CAP_S` added to settings.
- Tests: added give-up-after-max-attempts, connection-error retry, jitter bounds, and skip cases for paused and pending. `test_deliver_retries_on_error_status` became `test_deliver_stops_on_4xx` — it asserted three calls on a 400, which is the behaviour this ticket removes.

## Verification
Nothing has been run. I had only the four files quoted in the ticket, no working tree, no CI, no staging, so every test above is unexecuted. Before merge, someone needs to run `pytest tests/test_webhooks.py` and grep for other `FakeRegistry`-style doubles, since any registry stub without `is_active` now raises `AttributeError` in `deliver`. Ticket item 5 (one-hour staging soak, p95 on the webhook-delivery board) is also outstanding — the board is not reachable from here. Note that adding sleeps between attempts raises wall-clock latency for events that fail at least once, so read the p95 for live endpoints only, as the ticket says.

## Notes for reviewer
Three parts of the ticket I deliberately did not do as written.

The attempt budget is still 3, not 5. The comment on `WEBHOOK_MAX_ATTEMPTS` says the partner delivery contract (`contracts/partner-delivery-v2.md` 4.2) commits to at most three attempts and that partners size their dedupe windows on that number, so raising it needs Legal sign-off and partner comms. Raising it would also cut against the ticket's own goal of sending partners less traffic during their incidents. Everything is read from the setting, so it is a one-line change once sign-off exists.

`deliver_sync` is still here. `test_admin_replay_uses_sync_path` patches it and `tools/admin_replay.replay_event` calls it, so deleting it breaks admin replay.

`is_active` treats `pending` as inactive, which is wider than "disabled" — today a registered-but-unverified endpoint receives events, and after this it does not. That follows the lifecycle comment in `registry.py` ("live - verified, receiving events"), but it is a real behaviour change; say so if you want `status not in ("paused", "revoked")` instead.

Smaller: `deliver` looks up the endpoint before the active check so unknown IDs still report as unknown rather than inactive, and a 3xx is treated as permanent, since the ticket says retry only on 5xx.