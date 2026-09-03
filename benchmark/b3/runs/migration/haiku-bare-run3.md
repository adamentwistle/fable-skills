1. The backfill doesn't map all status values present in prod: 'PAID' (5210 rows), 'canceled' (1988 rows), 'complete' (417 rows), and NULL (149 rows) will leave rows with NULL state. Migration 0143 will fail when trying to set state NOT NULL.

2. The backfill runs the entire operation in a single transaction; on 61M rows it will take 30+ minutes and cause severe lock contention on a high-traffic table. Commit after each batch instead.

3. `jobs/nightly_finance_export.py` still references `orders.status`, which 0143 will drop. The nightly job will fail Friday 02:00 UTC unless this file is updated to use `state` with numeric values (e.g., `state IN (1, 2)` for paid/shipped).

4. Before 0143: handle the three missing status values (add mappings or explicitly reject/assign defaults), verify the backfill completes with zero NULL state rows, and test migration 0143 on a prod snapshot.

5. Update `jobs/nightly_finance_export.py` in this PR, or delay 0143 upgrade until after Friday 02:00 UTC nightly export run.

Cannot ship Thursday as planned.