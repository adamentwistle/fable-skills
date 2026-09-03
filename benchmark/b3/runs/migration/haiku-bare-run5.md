1. Backfill script MAPPING doesn't handle 'PAID' (5,210 prod rows), 'canceled' (1,988 rows), 'complete' (417 rows), or NULL (149 rows); these will remain state=NULL and cause migration 0143's ALTER NOT NULL to fail. Add all observed values to MAPPING with their intended state, or document why they're excluded and how they should be handled.

2. jobs/nightly_finance_export.py still queries `o.status` (unchanged file, line 5). After 0143 drops the column, this nightly job will crash. Update the query to use `o.state` and map values back to strings if the export format requires text.

3. Before running 0143 in prod, add a verification step: `SELECT COUNT(*) FROM orders WHERE state IS NULL` must return 0. If nonzero, backfill failed to convert all rows.

4. The grep for status was scoped to app/ only. Check for references to orders.status in jobs/, reports/, admin/, and other modules outside app/ that the PR description doesn't mention.

5. OrderState enum defines only 5 values (0–4), but prod has 'complete' in 8 years of data. Clarify: is 'complete' a valid state that should be added to the enum, or a data error that should be rejected?

6. Before step 2 (code deploy), verify that old code won't insert orders during the rolling deployment window. If it does and doesn't set state, those rows will have state=NULL and need backfill to cover them (contingent on fixing issue 1).

**Cannot ship Thursday** without fixing issues 1 and 2 (blocker: backfill will fail, nightly export will crash).