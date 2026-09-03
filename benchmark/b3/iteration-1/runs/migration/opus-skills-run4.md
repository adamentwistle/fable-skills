Cannot ship Thursday. The backfill silently skips half the table (proven by the author's own staging log), the mapping drops 7,764 rows on the floor, `0143` will fail on those, and the nightly finance export still reads `orders.status`.

1. The backfill skips every other batch: `OFFSET` walks forward while the `state IS NULL` result set shrinks underneath it — drop `OFFSET` and repeatedly take the first `BATCH` ids (or keyset-paginate on `id > last_seen`).
2. Staging did not succeed, it stopped halfway and printed "done": 5000 × 211 = 1,055,000 of 2,104,377, exactly where `OFFSET` overtakes the remaining unmigrated set — treat that run as a failure, not a baseline.
3. `done += BATCH` counts attempts, not rows written, so the log overstates and hides the skip — accumulate `cur.rowcount`.
4. The `CASE` has no `ELSE`, so `PAID` (5,210), `canceled` (1,988), `complete` (417) and the 149 NULLs get `state = NULL` and are re-selected on every re-run forever — add explicit mappings plus an `ELSE` that fails loudly on anything unrecognized.
5. `complete` and the 149 NULL statuses have no obvious target state — get a written decision from the orders owner before the mapping is final.
6. `alter_column("orders", "state", nullable=False)` in 0143 will simply error out on those leftover NULLs, aborting mid-migration — gate 0143 behind a reconciliation query, not behind the script's exit code.
7. Even when it succeeds, that `SET NOT NULL` takes ACCESS EXCLUSIVE and full-scans 61.4M rows, blocking all order traffic — add a `NOT VALID` CHECK, `VALIDATE CONSTRAINT`, then set NOT NULL so PG 15 skips the scan.
8. The whole loop runs inside one `conn.transaction()`, so nothing commits until the end: a 61M-row transaction, no resumability, table bloat, and replica conflicts — commit per batch.
9. Timing does not fit the window: staging managed ~1,600 rows/sec, so 61.4M rows is roughly 10 hours even before `OFFSET`'s quadratic degradation (100k in 31s vs 1M in 627s shows it already) — plan the backfill as a multi-hour background job, not a rollout step.
10. `jobs/nightly_finance_export.py` selects `o.status` and filters on it; 0143 breaks Finance's Looker load at 02:00 UTC the same night — port the export to `state` and ship it before 0143.
11. The grep was scoped to `app/` only, which is why `jobs/` was missed — re-grep the entire repo plus any other service or ETL touching this database, and post the reader/writer list on the PR.
12. Steps 1–3 collapse expand and contract: during the ~6-minute rolling deploy old pods write `status` only and new pods write `state` only, so rows created in that window are unreadable by one side or the other — dual-write both columns and read either for one full release.
13. `OrderState(row["state"])` raises on `None`, so any unbackfilled row or old-pod insert crashes the read path rather than degrading — tolerate NULL and unknown values per record.
14. 0143's `downgrade` recreates an empty `status` column, which is not a rollback — snapshot `id, status` into a backup table before 0143 and keep it until the release after.
15. Dropping `status` in the same window as adding `state` leaves no recovery period — move 0143 to release 2026.37 at the earliest.
16. The script has no dry-run — add one reporting the would-change count and sample ids, and compare it to the 61,437,902 total before writing anything.
17. Nothing states where the backfill runs or who approves it — name the target host/database and get explicit go-ahead before it touches prod.
18. Required before rollout: run 0142 and 0143 up → down → up on a prod-shaped copy loaded with the real spellings, including `PAID`, `canceled`, `complete` and NULL.
19. Required after the backfill, before 0143: `count(*) WHERE state IS NULL` must be 0 and each `state` value's count must match its `status` count from the histogram — and spot-check ~10 ids of each odd spelling through `get_order`, not just SQL.
20. Required after 0142: confirm `ix_orders_state` is `indisvalid` — a failed `CREATE INDEX CONCURRENTLY` leaves an invalid index behind, and the `downgrade` drops it non-concurrently.
21. Two streaming replicas serve reads, so a multi-hour backfill's WAL will lag them and can cancel read queries — throttle between batches and watch replication lag.
22. Not verifiable from this PR: `app/api/orders.py` and the tests weren't included, so I could not check whether clients that currently send `PAID`, `canceled`, or `complete` to the `status` query parameter now get rejected — that mapping needs review before merge.