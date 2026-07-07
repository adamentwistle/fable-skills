---
name: leave-no-mess
description: Clean up your session's side effects — background processes, temp files, debug scaffolding, test data, stashed state — before reporting done. Use at the end of any task that spawned servers, wrote scratch files, added debug output, or altered state beyond the intended diff.
---

# leave-no-mess

The task isn't the diff alone; it's the diff plus a workspace in the state you found it (minus the intended change).

1. **Kill what you started:** dev servers, watchers, background jobs, containers, port-holders. A zombie process from your session is the "port already in use" mystery in the user's next one. Check running background tasks before your final report.
2. **Sweep your scaffolding out of the diff:** debug prints, verbose-logging flags you flipped, hardcoded test values, commented-out experiments, `TODO(remove)` markers. `git diff` read hunk-by-hunk is the checklist (see self-review-diff) — everything there should be the change, not the process of finding it.
3. **Scratch files go in the scratchpad, and die with the task.** Throwaway repro scripts, downloaded samples, generated fixtures — if they were written into the repo, remove them or they'll show up in someone's `git status` as archaeology (see git-hygiene step 2).
4. **Undo state changes made for testing:** seeded rows in a shared database, modified local configs, environment variables exported for one run, git stashes you created, test users/webhooks registered against real services. External test artifacts (a queue, a webhook, a sandbox record) especially — nobody else knows they exist.
5. **What you can't or shouldn't clean, report:** a cache that will rebuild, a migration already applied, a process intentionally left serving. "Left running: dev server on :3000 for your review" converts a mess into a handoff (see honest-report).
6. **Deliberate artifacts are not mess** — the new test fixture, the added script, the updated lockfile stay. The test is intent: did the task need this to exist afterward, or did *you* need it to exist during?

Exit check: `git status` shows only intended changes; no process you spawned is still running unannounced; the next session (theirs or yours) starts clean.
