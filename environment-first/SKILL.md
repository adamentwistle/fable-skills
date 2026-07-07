---
name: environment-first
description: When something that should work doesn't, suspect the environment before rewriting the code — wrong directory, stale build, missing env var, version mismatch, dirty state. Use when a command fails unexpectedly, tests fail that "can't" fail, or behavior contradicts the code you're reading.
---

# environment-first

Weaker debugging assumes the code is wrong and starts editing. Often the code is fine and the world is misconfigured — and code edits made while the environment lies will be wrong edits.

1. **When behavior contradicts the source you're reading, you're probably not running that source:** stale build artifact, cached bytecode, an installed copy shadowing the checkout, the wrong virtualenv/node_modules, a running server that predates the change. Rebuild/restart before concluding the code is haunted.
2. **Check the boring five first** (under a minute, in order): `pwd` — right directory/repo/branch? `git status` — unexpected local modifications? runtime version (`node -v`, `python --version`) vs what the project expects? env vars/config the code reads — set, and set to what you think? is the dependency install current (lockfile newer than last install)?
3. **"Works on the other machine / in CI" is an environment diff by definition.** Diff the versions, env vars, and OS assumptions before diffing the code.
4. **Flaky ≠ mysterious:** a test failing intermittently usually means shared state, port collisions, timing, or leftover files from a previous run. Clean state and rerun before blaming the test's logic.
5. **Fix the environment properly, then re-run the original failure** — and if the "bug" vanishes, say so honestly: nothing was wrong with the code, and no code change should ship (see honest-report).
6. **If the setup itself was broken, note the fix** where the project keeps such things — the next session shouldn't rediscover it.

Heuristic: if the failure message doesn't mention your code's names at all (import errors, command-not-found, connection refused), it's environment until proven otherwise.
