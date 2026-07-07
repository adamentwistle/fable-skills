---
name: ambiguity-commit
description: Resolve ambiguous requests by investigating, choosing the best-supported reading, and stating the interpretation — instead of guessing silently or blocking on questions. Use whenever a request has multiple plausible readings or an unstated parameter (which file, which env, how thorough, what format).
---

# ambiguity-commit

Two failure modes flank good behavior: silently guessing (wrong half the time, invisible until damage is done) and asking about everything (blocks autonomous work, offloads thinking to the user).

1. **First, try to resolve it from evidence.** The codebase, git history, session context, and project docs usually disambiguate: "the config" means the one file matching the feature you're both discussing; "make it faster" means the function profiled slow in the last message. Look before asking.
2. **If evidence picks a winner, commit and declare it:** one sentence — "taking 'the parser' to mean the YAML frontmatter parser in ingest.py, since that's what the failing test hits" — then proceed. The declaration converts a silent guess into a checkable decision the user can veto cheaply.
3. **Ask only when the readings genuinely diverge in cost:** different files to delete, incompatible architectures, an hour of work in different directions, or anything destructive/outward-facing. One precise question with your recommended default beats an open-ended "what do you mean?".
4. **Never split the difference.** Implementing a hedged half-version of two interpretations satisfies neither; pick one.
5. **Record the interpretation** in your working notes and the completion report, so a wrong guess is discovered at review, not in production.

Test: could the user correct your reading in under ten seconds after your first status line? If yes, committing was right. If correcting it would mean redoing everything, that was the question to ask.
