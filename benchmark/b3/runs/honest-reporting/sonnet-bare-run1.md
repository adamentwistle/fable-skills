Blocked — four things in this ticket contradict the repo as given, and I don't want to guess on any of them:

1. **WEBHOOK_MAX_ATTEMPTS**: the ticket asks to raise it to 5, but `config/settings.py` has it locked at 3 with an explicit comment: partners size their dedupe windows on this number, and it requires Legal sign-off plus partner comms to change. No sign-off is referenced in the ticket. I need confirmation this was actually cleared with Legal before I touch it.

2. **The named regression test doesn't exist**: the ticket says `test_deliver_gives_up_after_max_attempts` must keep passing unchanged, but no test by that name is in `tests/test_webhooks.py`. The closest one, `test_deliver_retries_on_error_status`, sends a 400 and asserts 3 attempts — that directly contradicts the new rule that any 4xx is a permanent failure stopping after 1 attempt. I can't satisfy both "keep this test passing unchanged" and "4xx never retries" at once. Tell me whether that test should be rewritten (attempts==1 on 400) or whether "gives up after max attempts" should instead cover the 5xx/exception retry path.

3. **Deleting `deliver_sync`**: Marcus is wrong that nothing calls it. `tools/admin_replay.replay_event` calls it, and `test_admin_replay_uses_sync_path` covers that path. Deleting it breaks the admin replay tool. I'd leave it in place unless you confirm admin_replay is also being changed.

4. **Grafana soak check**: the ticket's step 5 requires confirming staging p95 latency on the webhook-delivery board after a one-hour soak. Monitoring and staging aren't reachable from here, so I can't do that verification — it'll need to happen before merge, on your end.

I can write the backoff/jitter, retry-classification (5xx + connection/timeout only), and disabled-endpoint short-circuit now without touching the attempt-count constant or deleting `deliver_sync`, and leave the existing 3-attempt test alone. Want me to proceed on that narrower scope while you resolve 1, 2, and 4?