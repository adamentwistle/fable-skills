Not shippable Thursday — the backfill silently skipped half the table on staging, and two steps in this plan lose money and break Finance.

1. The backfill's `OFFSET` advances while the `state IS NULL` result set shrinks, so it skips every other block and exits when `offset >= remaining`; that is exactly your staging result (breaks at 1,055,000 ≈ 2,104,377/2, leaving ~1.05M rows NULL and printing "done"). Fix: keyset-paginate on `id > last_id`, never `OFFSET`.
2. `done += BATCH` counts batches, not rows, so the final line can't detect the above. Fix: accumulate `cur.rowcount`.
3. The `CASE` has no arm for `PAID` (5,210), `canceled` (1,988), `complete` (417) or NULL (149), so it writes NULL for 7,764 rows and 0143's `SET NOT NULL` fails. Fix: add case-folded arms for `PAID`/`canceled`, and get a product decision on `complete` and NULL before writing the mapping.
4. `OrderState` has no member for `complete`; decide whether it maps to SHIPPED or needs a new value — don't silently fold it.
5. The whole backfill runs inside one `conn.transaction()`, so 61M row updates commit as a single transaction: unbounded WAL, table bloat, vacuum blocked, and replication lag on both read replicas. Fix: commit per batch.
6. No throttle and no replica-lag check while rewriting 61M rows against two replicas serving production reads. Fix: sleep between batches and pause when `pg_stat_replication` write lag exceeds a threshold.
7. Runtime is extrapolated from a run that did half the work: ~11 min for ~1M rows scales to roughly 11 hours for 61M, plus index maintenance. This does not fit a Thursday deploy window; plan the backfill as a multi-hour or overnight job, not a rollout step.
8. `mark_paid` matches `state = PENDING`, but every order created before the backfill has `state IS NULL` — the update affects 0 rows, the webhook still returns 2xx, and the provider stops retrying. That is silently unpaid orders across 3.87M pending rows for the entire deploy-to-backfill window. Fix: dual-write and match on `(state = 0 OR (state IS NULL AND status = 'pending'))` until the backfill is verified complete.
9. `Order.from_row` calls `OrderState(row["state"])`, which raises on NULL, so every read of a not-yet-backfilled order 500s the moment the first new pod is live. Fix: fall back to mapping `row["status"]` when `state` is NULL.
10. `create_order` inserts without `status`; if `orders.status` is NOT NULL or has no default, order creation fails outright on the first new pod. Fix: confirm the column's constraint and dual-write `status` during the transition.
11. `jobs/nightly_finance_export.py` selects and filters on `o.status`; dropping the column breaks the 02:00 UTC export and Finance's Looker load the next morning. The grep covered only `app/`. Fix: update the job to `state IN (1, 2)`, keep emitting a `status` text label so the Looker model's schema is unchanged, and ship it before any drop.
12. Re-run the grep across the whole repo, not `app/` — plus check DB views, materialized views, and anything querying the replicas directly (analytics, dashboards, other services).
13. 0143's downgrade recreates `status` as an empty nullable column, so it is not a rollback — the data is gone. Fix: split the drop into its own PR a full release after 0143, once nothing reads `status`.
14. `SET NOT NULL` takes ACCESS EXCLUSIVE and full-scans 61M rows, blocking all `orders` traffic for minutes. Fix: add `CHECK (state IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT` (no exclusive lock), then `SET NOT NULL`, which is then cheap.
15. Neither migration sets `lock_timeout`, so `add_column` queuing behind a long query blocks every reader on `orders`. Fix: `SET lock_timeout = '3s'` and retry.
16. The index is built on 61M NULLs and then churned by every backfill update. Fix: create `ix_orders_state` after the backfill, not before.
17. `CREATE INDEX CONCURRENTLY` can fail and leave an INVALID index that the migration will not notice. Fix: drop-if-exists-and-invalid before creating.
18. The API maps by name, but `OrderState` names are uppercase and the wire values are lowercase; confirm inbound `canceled` and `PAID` still resolve as they do today, or existing clients break.
19. Tests ran only against a fresh schema at head, so the mixed state (`status` present, `state` NULL) is untested. Fix: add a migration test seeded with pre-0142 rows, including the odd spellings and the NULLs.
20. Before step 1: capture `SELECT status, count(*) ... GROUP BY 1` again and fail the backfill on any spelling not in the mapping, rather than writing NULL.
21. Between steps 2 and 3: verify all 12 pods are on the new build and dual-writing before starting the backfill.
22. Between steps 3 and 4: require `SELECT count(*) FROM orders WHERE state IS NULL` to return 0 immediately before 0143, and hold the window open only if it does.
23. After step 4: watch replica lag and the payment-webhook success rate for a full cycle, and confirm the nightly finance export ran clean before removing the dual-write.

Ship 0142 plus the dual-writing app on Thursday. Run the backfill separately once it is fixed, and move 0143 — and the `status` drop as its own later change — to a subsequent release.