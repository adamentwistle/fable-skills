1. Backfill incomplete: prod has 7,764 rows with unmapped status values (PAID uppercase: 5,210; canceled single-L: 1,988; complete: 417; null: 149); CASE statement only handles 5 values; step 4 will fail when trying to alter state NOT NULL; add CASE clauses for all observed values or decide if they map to existing states.

2. Reader missed: jobs/nightly_finance_export.py directly queries `orders.status` but is not listed as updated; job will fail after step 4 drops the column; add to reader audit and update query to use state instead.

3. Grep scope incomplete: only searched `app/` directory; prod failure risk if there are other readers in `jobs/`, scripts, or elsewhere; re-grep entire codebase for `orders.status` references before final rollout.

4. Staging test inconclusive: only 1,055,000 of 2,104,377 rows updated; unclear if unmapped values exist in staging data or script hit an error; retest backfill against prod replica to confirm coverage.

5. Pre-step-4 verification missing: before attempting "alembic upgrade 0143", run `SELECT count(*) FROM orders WHERE state IS NULL`; if > 0, the alter will fail.

6. **Cannot ship Thursday.** Backfill must handle all 61.4M prod rows and jobs/nightly_finance_export.py must be updated (second reader discovered after the grep). Fix the CASE statement, complete the reader audit, re-test, and add the verification query.