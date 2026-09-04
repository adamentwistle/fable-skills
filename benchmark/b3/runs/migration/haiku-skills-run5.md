1. **Unmapped status values (7,764 rows) will block 0143 migration**: The CASE statement omits uppercase PAID, misspelled canceled, complete, and existing NULLs. Backfill leaves these as NULL, then 0143's NOT NULL constraint fails. Expand the MAPPING to handle all observed values or add a fallback (e.g., `ELSE 0` for PENDING).

2. **OrderState(NULL) crashes models.py during backfill window**: Between deploy (step 2) and backfill completion (~10+ hours per prod timing), reading old unmapped rows fails at `OrderState(row["state"])`. Must handle NULL gracefully: either filter it out, default to PENDING, or catch the ValueError. Staging test's "1055000 updated" vs. "2104377 to backfill" (50% completion) suggests this was hit there.

3. **Unchanged reader blocks 0143: nightly_finance_export.py still SELECTs o.status** — this job will fail after status is dropped. Must be updated to use state and map back to string for Finance's Looker model or removed from the PR scope and updated separately before 0143 deploys.

4. **Dry-run count doesn't reconcile**: Before 61,437,902 rows; after, 61,430,138 backfilled + 7,764 unmapped = 61,437,902 only if unmapped are explicitly handled. Run a dry-run with `WHERE state IS NULL` and show expected unmapped count before proceeding.

5. **Backfill performance exceeds deploy window**: Staging took 11 min for 2.1M rows (~1,600 rows/sec). Prod 61M rows would take ~10+ hours, far longer than the 6-min rolling deploy. Backfill runs in step 3 while app is live, so the long window is acceptable, but confirms NULL-state handling is mandatory during it.

6. **Add verification step before 0143**: After backfill completes, query `SELECT COUNT(*) FROM orders WHERE state IS NULL` and confirm zero (or only the rows that are truly unmappable by business rule). If non-zero, backfill failed or missed unmapped values.

7. **Staging test incomplete or misleading**: Output shows "done: 1055000 rows updated" for "2104377 rows to backfill" (~50%). Either the output was truncated or the test hit the unmapped-value problem and stopped; confirm staging backfill succeeded fully.

**Cannot ship Thursday.** The unmapped values (7,764 rows) will fail 0143's NOT NULL constraint, the app will crash reading NULL states during backfill, and nightly_finance_export.py is a dangling reader. All three must be resolved.