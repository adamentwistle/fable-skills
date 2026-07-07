---
name: context-checkpoint
description: Externalize working state to files so long tasks survive context compaction and interruption. Use at the start of any task likely to exceed ~30 minutes or span many files, and again whenever a major phase completes or the plan changes.
---

# context-checkpoint

Context windows compact; whatever lives only in conversation history can silently vanish. Durable state lives in files.

1. **At task start, write a scratch plan file** (in the session scratchpad or a `.claude/`-ignored path): the goal in one line, acceptance criteria, ordered steps, and decisions made. This is the file future-you re-reads after compaction instead of re-deriving everything.
2. **Update it at phase boundaries, not continuously:** tick completed steps, record decisions with their why ("chose X over Y because Z" — the why is what evaporates first), note dead ends so they aren't retried.
3. **Record exact state for resumption:** the failing command and its current output, the file:line you were editing, the next concrete action. "Continue the migration" is useless after compaction; "run `pytest tests/test_ingest.py -k utf8`, still failing on line 214 null check" resumes in seconds.
4. **After compaction or a fresh session, trust the file over the summary.** Re-read the checkpoint and the current `git diff` before acting — the compacted summary is lossy; the file and the diff are ground truth.
5. **Commit at safe points** when the work is committable — a described commit is the strongest checkpoint there is. Don't let 400 lines of uncommitted work ride on one fragile context.

Failure mode this prevents: the post-compaction session confidently redoing step 2 while overwriting completed step 4.
