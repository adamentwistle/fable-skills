---
name: codebase-orientation
description: Fast recon before changing unfamiliar code — instructions → manifest → tree → trace one flow end-to-end → git archaeology → imitate the newest precedent. Use when starting in a repo or module you haven't touched this session, or before designing against an existing architecture.
---

# Codebase Orientation

The expensive failure is building something that fights the codebase's own architecture because you never learned it. Orientation is 5–10 minutes of reads that pay for themselves immediately.

## The recon sequence

1. **Instructions first.** CLAUDE.md / AGENTS.md / CONTRIBUTING / README — in that order. These override your defaults and often name the exact gotchas you'd otherwise rediscover the hard way. If project instructions exist, they win over your habits.

2. **The manifest.** `package.json` scripts (or Makefile/justfile/pyproject) tells you: how to build, test, lint, run — and the dependency list tells you the intended stack. Use the project's declared commands, never your generic equivalents.

3. **Shape of the tree.** One `ls`-level pass over the source root. Learn the layering (where do types live? where does business logic vs UI vs IO live?) before deciding where new code goes. New code goes where the existing analog lives.

4. **The relevant flow, end to end.** For the specific task, trace one representative request/action from entry point to effect (route → handler → service → store, or CLI arg → command → output). Read the actual files on that path — this is the single highest-value read. Note the idioms: error handling style, naming, how modules import each other.

5. **Recent history.** `git log --oneline -20` and, for files you'll edit, `git log --oneline -5 -- <file>`. Recent commits reveal active conventions, in-flight migrations (don't build on the OLD pattern mid-migration), and who/what last touched your area. A recent commit titled "migrate X to Y" means new code uses Y.

6. **Find the precedent.** For "add a Z" tasks, find the most recently added Z (tool, route, component, migration) and read its full diff if possible (`git log --diff-filter=A`, or just read all its wiring). Imitate the precedent exactly; deviate only deliberately.

## Judging which pattern to copy

When the codebase contains two competing patterns for the same thing, prefer: (1) the one in newer code, (2) the one the instructions endorse, (3) the one nearest your change. If genuinely ambiguous and load-bearing, ask — citing both patterns you found.

## Cheap map, not deep study

Orientation is breadth-first and time-boxed. Read signatures and shapes, not every body. Depth comes later, on the specific path you're changing. If the repo is huge, delegate the broad sweep (search agents) and keep only the conclusions.

## Signs you skipped this step (go back)

- You're about to add a dependency the repo already has an equivalent for.
- Your new file's imports look different from every neighbor's.
- You invented a directory.
- You wrote a helper that grep would have found already exists.
