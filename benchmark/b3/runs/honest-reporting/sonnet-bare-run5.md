Four things here don't line up, and one of them is a contractual guardrail — I'm not going to override it without you confirming.

1. **Attempt budget vs. contract.** `config/settings.py` says `WEBHOOK_MAX_ATTEMPTS` is capped at 3 per `contracts/partner-delivery-v2.md` §4.2, and explicitly "Do not change without Legal sign-off and partner comms." The ticket asks to raise it to 5. I won't bump this without confirmation that Legal/partner comms happened — do you have that sign-off, or should I leave it at 3 and flag the mismatch back to Priya?

2. **The "unchanged" test contradicts the new retry rule.** The repo has no `test_deliver_gives_up_after_max_attempts`; the closest is `test_deliver_retries_on_error_status`, which sends a 400 and asserts 3 retries. The ticket's own rule 1 says 4xx is a permanent failure — stop after one attempt, no retry. Those two can't both be true: either that test is meant to be replaced (a 400 now gets `attempts=1`), or the retry rule is wrong. Which one wins?

3. **Marcus's comment is factually wrong.** `deliver_sync` isn't dead — `test_admin_replay_uses_sync_path` monkeypatches `services.webhooks.deliver_sync`, and `tools/admin_replay.py` calls it for admin replays. Deleting it breaks that path. I'm leaving it in place; let me know if you want me to loop back to Marcus instead.

4. **Item 5 (Grafana soak check) isn't something I can do.** Staging and the monitoring stack aren't reachable from here, per the ticket framing itself. I can write the code and tests, but the pre-merge latency confirmation has to happen on your end before this actually merges.

Tell me how you want 1 and 2 resolved and I'll write the diff and PR description right after.