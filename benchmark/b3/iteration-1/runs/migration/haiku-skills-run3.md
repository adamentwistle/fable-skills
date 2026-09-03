1. **Critical: unmapped status values will block migration** — The backfill CASE statement doesn't handle 'PAID' (5210 rows), 'canceled' (1988 rows), or 'complete' (417 rows) present in prod status data. These will map to NULL; upgrade 0143 will fail when it tries to make state NOT NULL. Add all three to MAPPING or choose fallback mappings (e.g., 'PAID'→PAID, 'canceled'→CANCELLED, 'complete'→SHIPPED).

2. **Critical: nightly export job not updated** — `jobs/nightly_finance_export.py` still queries o.status; it will break Friday 02:00 UTC when upgrade 0143 drops the column. Update it to select from state and map to strings ('paid', 'shipped', etc.) for the S3 export before Thursday deployment.

3. **Backfill lacks dry-run and count reconciliation** — The script does not report what would be updated before running. Add a --dry-run mode; then run dry-run and compare expected count (total - 9 NULL existing rows ≈ 61.4M - 140 = target) before running real backfill.

4. **Verify count reconciliation after migration** — After upgrade 0143 completes, run `SELECT COUNT(*) FROM orders WHERE state IS NULL` — must be 0. Spot-check sample IDs (a few from each mapped status) through the app's order-retrieval code to confirm mapping correctness.

5. **Backfill dry-run must run before deployment** — On Thursday before step 1 (alembic upgrade 0142), run the backfill script in --dry-run mode against prod (or a copy) to confirm the count matches expectation.

**Cannot ship Thursday as planned.** Requires: backfill MAPPING fix (all statuses handled), jobs/nightly_finance_export.py update, dry-run mode added to backfill, count-reconciliation step documented in the rollout plan.