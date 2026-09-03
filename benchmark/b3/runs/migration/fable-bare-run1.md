1. Backfill CASE has no ELSE, so `PAID`, `canceled`, `complete` and NULL rows (7,764 in prod) get `state = NULL` and stay NULL forever; map `lower(status)`, add `canceled`, decide `complete` and NULL with product, and raise on anything unmapped.
2. Because of 1, `ALTER COLUMN state SET NOT NULL` in 0143 will fail in prod; make 0143 assert `count(*) WHERE state IS NULL = 0` and abort otherwise.
3. Paging with OFFSET over `WHERE state IS NULL` skips half the rows because the result set shrinks as you update it, which is why staging reported 1,055,000 of 2,104,377; use keyset paging (`WHERE id > last_id ORDER BY id LIMIT n`).
4. Each OFFSET query rescans from the start, so runtime is quadratic; on 61M rows that is many hours, not the 11 minutes staging showed, and does not fit a Thursday window.
5. The whole backfill runs in one transaction, holding row locks on every updated order until the end, so `mark_paid` webhooks block and the provider retries pile up; commit per batch and add a short sleep between batches.
6. One 61M-row transaction also generates hours of WAL and replica lag on the two read replicas; pace batches against replication lag and schedule a VACUUM afterward.
7. `done += BATCH` reports batch count, not rows changed; use `cur.rowcount`.
8. After step 2 and before the backfill finishes, `Order.from_row` calls `OrderState(None)` on every unbackfilled order and every `get_order` raises; the new app must read `state` with a fallback to `status` until the backfill is verified complete.
9. Same window: `mark_paid` matches on `state = 0`, which is NULL for unbackfilled pending orders, so the UPDATE silently affects 0 rows, returns 2xx, and paid orders are never marked paid; that is money lost, and the fallback in 8 must cover the WHERE clause too.
10. During the 6-minute rolling deploy, old pods insert `status` only and new pods insert `state` only, so each side's `mark_paid` silently misses the other's pending orders; ship a transitional release that dual-writes both columns and reads either.
11. `jobs/nightly_finance_export.py` was missed because the grep stopped at `app/`; from Thursday night it silently excludes every new order (status NULL), and after 0143 it crashes; port it to `state IN (1, 2)` in this PR.
12. Grep the whole repo, DB views, triggers, other services on the read replicas, and the Looker model for `orders.status` before assuming three readers is the full list.
13. `SET NOT NULL` on 61M rows takes an ACCESS EXCLUSIVE lock for a full table scan; add `CHECK (state IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT`, then `SET NOT NULL` (PG15 skips the scan), then drop the check.
14. Dropping `status` in 0143 is irreversible; its downgrade recreates an empty column, so no app rollback exists after step 4; defer the drop to a later release after a full cycle on `state`.
15. 0143 downgrade creates `ix_orders_status` non-concurrently on 61M rows and would lock the table; use `postgresql_concurrently=True` in an autocommit block like 0142 does.
16. A B-tree on a five-value column is close to useless for the two big states; consider a partial index on `pending`/`paid` instead, or drop the index claim from the rationale.
17. The backfill needs `statement_timeout`/`lock_timeout` set and a restartable pod (`kubectl run` with no restart policy loses the run on eviction); with keyset paging and per-batch commits, re-runs become genuinely safe.
18. No test exercises the backfill against dirty data; add one that seeds the eight prod spellings plus NULL, runs the script, and asserts zero NULL states and the expected counts.
19. Required step before rollout: dry-run the fixed backfill on a prod snapshot and record runtime and the mapped/unmapped counts.
20. Required step between 3 and 4: verify `count(*) WHERE state IS NULL = 0` on the primary and confirm replica lag is back to zero.
21. Required step after the deploy: confirm the Friday morning Finance export row count matches Thursday's before anyone trusts Looker.

This cannot ship Thursday as planned. Thursday can safely take 0142 plus the fixed backfill plus a dual-write app release; the read switch goes in the following release, and 0143 only after that has run clean.