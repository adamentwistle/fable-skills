1. **jobs/nightly_finance_export.py will crash**: The export SQL still selects `o.status` (line 5), which doesn't exist after migration 0143 drops it. Update EXPORT_SQL to select `o.state` and map to string for Looker.

2. **Backfill doesn't handle non-standard status values; migration 0143 will fail**: Production data contains 7,764 rows with status values not in the MAPPING: 5,210 'PAID' (uppercase), 1,988 'canceled' (variant), 417 'complete' (unknown), 149 NULL. These will remain state=NULL after the backfill. Migration 0143's `ALTER COLUMN state NOT NULL` will fail. Add an ELSE clause to the MAPPING CASE statement (or preprocess these rows) before running backfill.

3. **Add verification step before migration 0143**: After backfill, require `SELECT count(*) FROM orders WHERE state IS NULL` to return 0. This gate is missing from the rollout plan.

4. **Staging test incomplete; needs explanation**: Output shows "done: 1055000 rows updated" from 2,104,377 rows (~50%). Why was only half the table backfilled? Re-run or document whether this is partial output.

5. **Backfill script lacks dry-run mode**: Run with `--dry-run` first to report counts without writing; data-migration-safety requires this.

**Cannot ship Thursday.** Blocker #2 fails the migration; blocker #1 breaks the nightly export job post-deploy.