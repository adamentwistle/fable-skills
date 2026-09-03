1. Backfill script is incomplete — doesn't handle 'PAID' (uppercase, 5210 rows), 'canceled' (American spelling, 1988 rows), 'complete' (417 rows), or NULL (149 rows); migration 0143 will fail when it makes state NOT NULL.

2. OrderState enum missing COMPLETE state — 417 production orders have status='complete', which maps to nothing; need to either add COMPLETE to the enum or clarify what those orders should be.

3. jobs/nightly_finance_export.py still selects o.status (which will be deleted in 0143) — query will fail when that file next runs.

4. Backfill script is case-sensitive — the CASE statement won't match 'PAID' or 'canceled' due to SQL case sensitivity; use LOWER(status) in the mapping.

5. Before rollout: investigate the 149 NULL status rows and the 417 'complete' rows to understand what states they should map to, and add COMPLETE to the enum or handle as a separate case.

**Cannot ship Thursday.** The backfill will leave ~7,500+ unmapped rows, blocking migration 0143 from completing, and the finance export will crash.