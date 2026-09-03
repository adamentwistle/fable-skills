1. `jobs/nightly_finance_export.py` queries `o.status` which migration 0143 drops — update the EXPORT_SQL query to select `o.state` and convert the integer back to the original string representation.

2. Backfill MAPPING omits 'PAID' (5210 rows), 'canceled' (1988), 'complete' (417), and NULL (149) — extend MAPPING to handle all cases, including case-insensitive normalization ('PAID' → 1, 'canceled' → 3, 'complete' to an appropriate state, NULL to a default or explicit error).

3. Backfill script loop lacks protection against incomplete updates — if the MAPPING misses any status value, rows remain state IS NULL and the loop will waste cycles re-selecting and re-updating them.

4. Add verification step after backfill, before migration 0143: run `SELECT count(*) FROM orders WHERE state IS NULL` and confirm it returns 0.

5. **Cannot ship Thursday.** Migration 0143's NOT NULL constraint will fail when the incomplete backfill leaves NULL values in state; this blocks the entire rollout.