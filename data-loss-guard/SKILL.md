---
name: data-loss-guard
description: Stop-and-check protocol before any destructive or hard-to-reverse operation — rm, overwrite, force-push, reset --hard, DROP, bulk delete, killing processes. Use the moment a planned action would destroy state that cannot be trivially recreated.
---

# data-loss-guard

Almost every catastrophic agent failure is a destructive command run on a wrong assumption. Before any destructive action:

1. **Look at the target first.** `ls` the directory before `rm -rf`; `git status`/`git stash list` before `reset --hard` or `checkout .`; `SELECT` before `DELETE`/`UPDATE` (same WHERE clause, check the row count). If what you find contradicts what you expected — files you didn't create, more rows than predicted — stop and surface it instead of proceeding.
2. **Distinguish recoverable from gone.** Committed work is recoverable via reflog; uncommitted work is not. A dropped column is gone. Overwritten files have no undo. Rank the action's blast radius honestly before choosing convenience.
3. **Prefer the reversible variant:** `git stash` over discard; move to a trash/backup path over `rm`; soft-delete or export-then-delete over hard delete; `--dry-run` flags wherever they exist (rsync, terraform, kubectl, many CLIs) on the first pass.
4. **Scope the command tightly.** No wildcards where an explicit list will do; absolute paths so a surprise cwd can't redirect the deletion; never `rm -rf` a variable-built path without checking the variable is non-empty and expected.
5. **Uncommitted user work is sacred.** If the working tree holds changes you didn't make, don't clean, checkout, or stash over them without the user's explicit say-so — that's their morning, not your scratch space.
6. **Force-push and history rewrites on shared branches need explicit user authorization**, every time.

Rule of thumb: cheap check, irreversible mistake — the one-command look-before-delete is always worth it.
