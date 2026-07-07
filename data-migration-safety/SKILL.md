---
name: data-migration-safety
description: Schema/data/wire-format changes — old data lives forever, expand→migrate→contract, idempotent dry-run batched bounded backfills, count reconciliation, rollback plan first. Use for schema changes, stored-JSON shape changes, backfills, or renaming/removing persisted or API fields.
---

# Data Migration Safety

Code you can roll back; data you often can't. Any change touching persisted or wire formats gets treated as irreversible-by-default and sequenced so no moment exists where running code can't handle the data it meets.

## The prime rule: old data lives forever

Every row/document/event written under the old shape still exists after your deploy. Reads must tolerate: missing new fields (default them), present old fields (ignore or map them), and malformed historical values (degrade gracefully, never crash or wipe — a parse failure on one bad record must not take down the collection). New required fields are only "required" for new writes.

## Expand → migrate → contract (never in one step)

1. **Expand**: add the new column/field/shape alongside the old. Code writes both (or writes new, reads either). Deploy. Nothing depends on the new shape yet.
2. **Migrate**: backfill old records to the new shape. Verify counts.
3. **Contract**: only after all readers use the new shape and backfill is verified — remove the old field/writes. This step is a separate deploy, days later, not minutes.

Collapsing these into one deploy creates the window where old code meets new schema (or new code meets old data) and errors page you at 2am. The same sequencing applies to API/event contracts: additive first, consumers migrate, then remove — coordinate with every consumer you can enumerate, and assume one you can't.

## Backfill / data-fix scripts

- **Idempotent**: running it twice must be safe (filter to unmigrated rows; upsert, don't blind-insert). Scripts die mid-run; re-runnability is the recovery plan.
- **Dry run first**: a mode that reports what WOULD change (counts + samples) without writing. Review those counts against expectation — "expected ~2k rows, script says 1.4M" is the disaster caught early.
- **Batched with progress**: chunked commits, logged progress, resumable. One giant transaction locks the table and loses everything on failure.
- **Bounded**: an explicit WHERE clause scoping exactly the intended records. Fix scripts without a scope predicate eventually eat a table.
- Capture a before-image of affected rows (backup table, export) when the change is destructive — that's the rollback.

## Verification gates

Before: count the affected set; back it up if destructive. After: recount (migrated + remaining + errored must reconcile to the before-count), spot-check samples end-to-end through the real read path (app code, not just SQL), and watch error rates after deploy. A migration is done when the numbers reconcile — not when the script exits 0.

## Rollback thinking

Write down, before running: "if this is wrong, how do I get back?" Acceptable answers: restore from the before-image; the old field still exists (expand/contract); the script's inverse is trivial and tested. If the honest answer is "we can't" — that's a flag to surface for explicit sign-off, not a detail to skip past.

## Repo-reality check

Migrations live wherever THIS project keeps them (some repos gitignore the migrations dir — then the commit message/docs must carry the SQL). Match the project's migration tooling and naming; never apply ad-hoc schema changes that bypass the project's migration history.
