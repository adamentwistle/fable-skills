1. **CRITICAL: Reader not enumerated** — `jobs/nightly_finance_export.py:4` queries `o.status`; grep was scoped to `app/` only and missed it. Must update this query to use `state` or disable the job before running 0143 (it will crash when status column is dropped).

2. **CRITICAL: Backfill MAPPING is incomplete** — Prod data contains `status` values not in the CASE: `PAID` (5210 rows), `canceled` (1988 rows), `complete` (417 rows). These will remain NULL after backfill. Migration 0143 sets `state NOT NULL` and will fail. Must add these to MAPPING or verify they can be discarded.

3. **CRITICAL: Dry-run missing** — Backfill script has no `--dry-run` mode; skill requires reporting expected counts before write. Add a mode to count affected rows and sample them without UPDATE.

4. **CRITICAL: Rollback plan missing** — If 0143 fails (e.g., NOT NULL violation), `status` values are gone and cannot be recovered. Backup the affected rows before running the backfill, or accept that rollback must restore from a database snapshot.

5. **Backfill progress counting is wrong** — `done += BATCH` increments even when final batch has fewer rows; the "done: 1055000 rows updated" from staging does not match the progress printout (stops at 1000000). Actual count should track `len(ids)` per batch or query the final result.

6. **No recount verification** — Before/after counts must reconcile. After backfill completes, query `SELECT count(*) FROM orders WHERE state IS NOT NULL` and `WHERE state IS NULL` to confirm all rows migrated or have known NULL reason (the 149 original NULLs).

7. **New orders inserted during backfill window are untracked** — Between app deploy (step 2) and backfill completion (step 3), new orders get `state` set but `status` NULL. The nightly job querying `status` will see these as missing data. Verify timing or update the job before this window opens.

**Cannot ship Thursday.** Must resolve readers, complete the MAPPING, add dry-run verification, and confirm nightly export or other jobs will not break.