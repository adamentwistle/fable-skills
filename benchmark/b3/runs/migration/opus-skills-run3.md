Not shippable Thursday — the backfill silently migrated only half the rows on staging, and the plan makes every existing order un-readable for the whole window between step 2 and step 4.

1. `OFFSET` walks forward while updated rows leave the `state IS NULL` set, so each batch skips 5,000 rows — replace with keyset pagination (`WHERE state IS NULL AND id > :last_id ORDER BY id LIMIT 5000`).
2. Your staging log is the proof, not a pass: `done: 1055000` is exactly 211×5000, the loop hit an empty batch at offset 1,055,000 with 1,049,377 rows still NULL, and 49.9% of staging was left unmigrated — re-run the count on staging (`SELECT count(*) FROM orders WHERE state IS NULL`) before touching prod.
3. `done += BATCH` counts intended rows, not written ones, which is why nobody noticed — use `cur.rowcount`.
4. The `CASE` has no arm for `PAID` (5,210), `canceled` (1,988), `complete` (417) or NULL (149), so 7,764 rows stay NULL and 0143's NOT NULL fails — normalize with `lower(trim(status))` and add explicit arms.
5. `complete` and NULL have no OrderState at all — needs a product decision on where those 566 orders land before the script can be correct.
6. `with conn.transaction():` wraps the entire loop, so there are no batched commits and nothing is resumable despite the docstring — commit per batch.
7. 11 min on staging bought 1,055,000 rows ≈ 1,600 rows/s; prod's 61,437,902 rows is ~10.7 hours at that rate, and OFFSET-free keyset scanning won't change the order of magnitude — this does not fit a Thursday deploy window.
8. Step 2 deploys `OrderState(row["state"])` while every pre-existing row still has `state` NULL, so every order read raises ValueError for the ~10 hours until step 4 — the app must keep reading `status` until the backfill reconciles.
9. `mark_paid` matches on `state = 1` against NULL rows, updates nothing, and the endpoint still returns 2xx, so the provider stops retrying and paid orders are never recorded — check rowcount and return non-2xx on zero rows.
10. Rows inserted between step 1 and step 2 by old code set `status` but leave `state` NULL, and the backfill has already passed them — re-run the backfill to zero after the deploy settles, or add a server-side DEFAULT on `state` in 0142.
11. `jobs/nightly_finance_export.py` reads `o.status` and was missed because the grep was scoped to `app/` — update `EXPORT_SQL` to `o.state IN (1, 2)` and ship it in the same release.
12. That same export silently under-reports the moment new code writes `state` without `status`, before 0143 even runs — Finance's 02:00 UTC Looker load is wrong for at least one night unless the export ships first.
13. Unverified: whether `orders.status` is NOT NULL or has a DEFAULT — if it is, the new INSERT in `create_order` fails outright, and neither migration alters it.
14. 0143's downgrade re-adds an empty `status` column, so once it runs the free-text values are gone and rollback is a PITR restore — split 0143 into the next release and keep `status` for a full cycle.
15. `alter_column("orders", "state", nullable=False)` takes ACCESS EXCLUSIVE and scans 61M rows — add a `NOT VALID` CHECK, `VALIDATE CONSTRAINT`, then set NOT NULL.
16. The index is created in 0142 before any values exist, so all 61M updates pay index maintenance — move `create_index` after the backfill.
17. The concurrent index build can leave an INVALID index on failure, and 0142 has no re-run path — use `DROP INDEX IF EXISTS` in downgrade and check `indisvalid` before proceeding.
18. Script has no dry-run mode — add one that reports the would-change count and sample IDs so "expected 61.4M, got 30M" is caught before writing.
19. Unverified: `app/api/orders.py` isn't in the diff, so I can't confirm the by-name mapping rejects inbound `canceled`/`PAID` values that previously matched rows — clients sending those will start getting 400s.
20. Step 0, before anything: run the whole sequence (0142 → backfill → 0143) against a prod-sized restore, and run 0142 up → down → up locally, since the downgrades have never executed.
21. Between the backfill and 0143: require `count(*) WHERE state IS NULL` = 0, and reconcile `GROUP BY state` against the status histogram above (0→3871009, 1→12461040, 2→38102551, 3→6210102, 4→792634) — mismatches mean the CASE is still dropping spellings.
22. Between the backfill and 0143: fetch ~20 sample IDs from each state through `get_order` in the real app, not SQL, and watch replication lag on both replicas throughout — 61M updates will push them behind and reads are served there.
23. After the backfill: `VACUUM (ANALYZE) orders` and confirm free disk, since updating every row roughly doubles the table's physical size before vacuum reclaims it.