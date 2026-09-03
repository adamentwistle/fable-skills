1. **Backfill MAPPING incomplete** — script's CASE statement doesn't handle 'PAID' (5.2k rows), 'canceled' (1.9k rows), or 'complete' (417 rows); these will retain state=NULL, causing migration 0143's NOT NULL constraint to fail.

2. **Staging backfill incomplete** — only 1,055,000 of 2,104,377 rows updated (50%); cause unclear and must be understood before prod run.

3. **jobs/nightly_finance_export.py still selects orders.status** — query will fail when migration 0143 drops the column; update the SELECT to use `state` and map back to status string for export, or deploy this change before 0143.

4. **Missing before/after reconciliation** — verify that before-count 2,104,377 = migrated + remaining + errored; the staging test did not show this.

5. **Dry-run not shown for production** — run backfill script once with a dry-run query (UPDATE...WHERE 1=0 or SELECT the would-be updates) on prod to verify data and estimate real duration before executing for real.

6. **Backfill must handle or reject anomalous status values** — either add PAID/canceled/complete to OrderState enum and MAPPING, or decide on a mapping (e.g., 'canceled'→CANCELLED, 'PAID'→PAID, 'complete'→?), or flag those rows and require manual review before proceeding.

7. **Between steps 3 and 4 of rollout** — after backfill completes, run a count query to verify all rows have state IS NOT NULL before running 0143, else 0143 will fail and roll back.

**Cannot ship Thursday as planned.** The backfill is incomplete and the mapping is wrong; the migration will fail on prod. Staging must be re-run to completion and reconciled first; prod data must be audited for the anomalous status values.