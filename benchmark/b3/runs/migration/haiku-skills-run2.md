1. jobs/nightly_finance_export.py references `o.status` which migration 0143 drops — update to use `o.state`.
2. Backfill script uses OFFSET-based pagination; staging shows ~50% completion, indicating rows are skipped when UPDATE sets them to NULL — rewrite with id-based pagination (`WHERE id > last_id`).
3. Prod data has unmapped statuses (PAID uppercase, canceled American spelling, complete, null totaling 7,764 rows) not covered by the CASE mapping — expand the mapping to handle all observed values.
4. Before running migration 0143, verify: `SELECT status, COUNT(*) FROM orders WHERE state IS NULL GROUP BY status;` must return empty.
5. Cannot ship Thursday as planned without fixing findings 1–3.