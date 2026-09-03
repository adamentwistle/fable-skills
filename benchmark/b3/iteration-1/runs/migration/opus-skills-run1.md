This cannot ship Thursday. The backfill has a row-skipping bug that its own staging log proves fired, three of the four rollout steps are ordered wrong, and a reader outside `app/` breaks when `status` is dropped.

1. The backfill skips about half the rows: `OFFSET` advances by 5000 while the `state IS NULL` set shrinks by 5000 each batch — switch to keyset paging (`WHERE state IS NULL AND id > :last ORDER BY id LIMIT 5000`, carry `last`).
2. The staging log is that bug, not a success: it stops at 211 batches (`done: 1055000`) because that is where `5000k ≥ 2104377 − 5000k`, leaving ~1,049,377 staging rows NULL and unnoticed — re-run staging after the fix and reconcile counts before prod is discussed again.
3. `done += BATCH` counts intended rows, not updated ones, which is why the log looked plausible — use `len(ids)`.
4. The `CASE` has no `ELSE`, so `PAID` (5210), `canceled` (1988), `complete` (417) and NULL (149) — 7,764 rows, exactly the gap between your mapped 61,430,138 and the table's 61,437,902 — silently map to NULL; normalize with `lower(trim(status))` and get a product decision on `complete` and NULL.
5. Because of 4, step 4's `SET NOT NULL` aborts after the whole window is spent — add a gate between steps 3 and 4: `SELECT count(*) FROM orders WHERE state IS NULL` must return 0.
6. The entire loop is inside one `conn.transaction()` — commit per batch, or nothing is resumable and a multi-hour transaction on the primary blocks vacuum and bloats both replicas.
7. No dry-run mode — add `--dry-run` that prints per-`status` counts and sample IDs and writes nothing, and compare its output to the prod `GROUP BY` above before the real run.
8. Runtime does not fit the window: staging did 1,000,000 rows in 627s ≈ 1,600 rows/s, so 61,437,902 rows is ~10.7 hours at best, and worse with `OFFSET` degradation — run it as a rate-limited background job over days, not inside a Thursday deploy.
9. `jobs/nightly_finance_export.py` selects `o.status` and filters `o.status IN ('paid','shipped')`; step 4 breaks the 02:00 UTC export and Finance's Looker load that morning — migrate it to `state` and ship that first.
10. The grep was scoped to `app/`, which is how 9 was missed — grep the whole repo plus other services, dbt/Looker models and ops runbooks for `status`, and list every reader before any contract step.
11. Step 2 before step 3 breaks all order reads: `from_row` calls `OrderState(row["state"])` and every pre-existing row has `state` NULL — backfill before deploying, or have `from_row` fall back to `status` when `state` is NULL.
12. No expand phase: during the ~6-min rolling deploy old pods write `status` only (state NULL, missed by a completed backfill) and new pods write `state` only (status NULL, so those orders vanish from the finance export) — write both columns for one full release, read either.
13. `mark_paid` silently no-ops while a row has `state` NULL and `status='pending'`: the UPDATE matches 0 rows, the handler still returns 2xx, the provider does not retry, and the order never becomes paid — same money loss for any row the backfill skips.
14. `0143`'s downgrade recreates an empty `status` column, so the free-text values are gone for good — snapshot `id, status` into a backup table as the first statement of 0143 and keep it for a release.
15. `SET NOT NULL` takes ACCESS EXCLUSIVE and full-scans 61M rows — add `CHECK (state IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT`, then `SET NOT NULL`, and set an explicit `lock_timeout` on every DDL statement.
16. `0143` is the contract step and belongs in a later release, not the same window as the expand — ship it days after `state` has run in production and every reader from 10 is confirmed migrated.
17. A failed `CREATE INDEX CONCURRENTLY` leaves an INVALID index that makes 0142 unrerunnable — drop-if-exists first, and drop concurrently in the downgrade too.
18. Run `0142` and `0143` up → down → up against a prod-sized copy before the window; neither downgrade has ever executed.
19. Watch replica lag throughout the backfill and pause between batches if it grows — two streaming replicas are serving reads.
20. The suite being green "on fresh schema at head" tests none of this — add tests for a NULL-`state` row, a legacy-spelling row, and the mixed-pod window.
21. After the backfill: per-`state` counts must equal the pre-run per-`status` counts (38102551 / 12455830 / 6208114 / 3871009 / 792634 plus the 7,764 decision), and spot-check sample IDs through the app's real read path, not just SQL.
22. `PAID`, `canceled` and `complete` were previously valid values in API responses and the `status` filter and now are not — confirm with API consumers before 0143.

I could not see `app/api/orders.py`, the tests, or whether `orders.status` is currently NOT NULL, so the name-mapping in the API and any insert that omits `status` are unverified.