1. The backfill silently skips about half its rows: it pages with `OFFSET` while the `WHERE state IS NULL` set shrinks under it, so every second batch is stepped over — that's why staging reported 2,104,377 to do and "done: 1055000"; fix by dropping `OFFSET` and re-running `SELECT id FROM orders WHERE state IS NULL ORDER BY id LIMIT 5000` until it returns nothing (or keyset-paginate on `id`).

2. `done += BATCH` counts the batch size, not rows touched, so the progress line and the final total are fiction that hid finding 1; use `cur.rowcount`.

3. The `CASE` has no branch for `PAID` (5,210), `canceled` (1,988), `complete` (417) or NULL (149), so 7,764 rows get `state = NULL` and 0143's `SET NOT NULL` fails; normalize with `lower(status)` for the case variants, and get a product decision on `complete` and NULL before writing the mapping.

4. Because unmapped rows stay NULL, "safe to re-run" is false in the way that matters — each re-run re-selects and re-updates the same 7,764 rows forever without converging; the mapping must be total.

5. The whole backfill runs inside one `conn.transaction()`, so on 61M rows it is a single hours-long transaction holding a snapshot open — bloat, blocked vacuum, and replication conflicts on both read replicas; commit per batch and add a short `sleep` between batches.

6. Real throughput from staging is ~1,600 rows/s (1.055M in 660s), so 61,437,902 rows is roughly 10 hours, not 11 minutes — the backfill does not fit in a Thursday deploy window and must run as its own scheduled job over a night or more.

7. Deploying the app at step 2 breaks every read: `Order.from_row` calls `OrderState(row["state"])` and every one of the 61M rows still has `state = NULL` until the backfill finishes, so `get_order` raises for ~10 hours; the backfill must complete before the app deploys.

8. `mark_paid` becomes a silent no-op for the 3,871,009 existing pending orders in that same window — `WHERE state = 0` matches nothing, the webhook still returns 2xx, and the provider never retries, so payments are lost, not delayed; same fix as 7, plus a reconciliation query afterwards.

9. Rows written by old pods during the 6-minute rolling deploy set `status` only and leave `state` NULL, so a backfill that ran earlier no longer covers them; add a final catch-up pass after the last old pod is gone.

10. If `orders.status` is NOT NULL in prod, the new `INSERT` that omits it fails on the first request after deploy — confirm the column's nullability and, if needed, drop the NOT NULL in 0142.

11. Dropping `status` breaks `jobs/nightly_finance_export.py`, which selects `o.status` and filters `o.status IN ('paid','shipped')` — the grep was scoped to `app/`, so this reader was missed; port it to `state` and ship that before 0143, keeping the output column named `status` so Finance's Looker model still loads.

12. Grep the whole repo, not `app/`, and also check consumers outside it — BI tools, dbt models, ad-hoc replica queries — since dropping the column breaks anything reading it directly.

13. `ALTER TABLE ... SET NOT NULL` takes ACCESS EXCLUSIVE and full-scans 61M rows; add a `CHECK (state IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT` it, then `SET NOT NULL` so the lock is instantaneous.

14. The index is created before any data exists and then bloated by 61M updates; move `CREATE INDEX CONCURRENTLY` to after the backfill.

15. `CREATE INDEX CONCURRENTLY` can leave an INVALID index behind on failure, and the migration doesn't check; verify `indisvalid` after 0142 and drop-and-retry if false.

16. 0143 is irreversible in practice — the downgrade recreates `status` empty, so once it runs there is no way back; split it into a separate release a week later, after 0142 plus the backfill have soaked.

17. `api/orders.py` maps by name, but previously the API echoed whatever was in the column, so consumers that saw `PAID` or `complete` will now see different strings; confirm that's acceptable and note it in the release notes.

18. The suite is green only against a fresh schema at head, which never exercises the migration path; add a test that runs 0142 → backfill → 0143 against a fixture seeded with all eight observed spellings plus NULL.

19. Before 0143, require `SELECT count(*) FROM orders WHERE state IS NULL` to return 0, as a gate rather than an assumption.

20. During the backfill, require someone watching `pg_stat_replication` lag on both replicas, with the batch loop pausing if it exceeds your read-staleness budget.

21. Consider an intermediate app release that writes both `status` and `state` and reads `status` — it removes the whole ordering hazard in 7, 8 and 9 and is cheaper than getting the sequence exactly right.

This cannot ship Thursday. The backfill is wrong (finding 1), incomplete (3), and takes about ten hours rather than eleven minutes (6); the rollout order as written causes a multi-hour read outage and drops real payments (7, 8); and 0143 breaks the nightly finance export (11). The realistic shape is: fix and re-test the backfill, ship 0142 plus the dual-writing app in the 2026.36 window, run the backfill over a following night, and hold 0143 for 2026.37.