1. Do not ship this Thursday: ship 0142 plus a dual-write app and the fixed backfill this release, and hold 0143 for a later release once NULL count is zero and every `status` reader is gone.
2. Backfill wraps all 61M rows in one transaction, holding row locks for hours and rolling everything back on any crash; commit per batch.
3. Backfill pages with OFFSET over `WHERE state IS NULL` while shrinking that set, so it skips every other batch (staging updated 1,055,000 of 2,104,377); paginate by `id > last_id` with no OFFSET.
4. The CASE has no ELSE, so `PAID`, `canceled`, `complete`, and null (7,764 prod rows) stay NULL and 0143's SET NOT NULL fails on prod; map `PAID`->1 and `canceled`->3, get a product decision for `complete` and null, and add an ELSE that raises.
5. `done` counts BATCH per loop, not rows updated, so the reported total is wrong; use `cur.rowcount`.
6. Staging timing extrapolates to well over 10 hours on prod (quadratic with OFFSET), not a Thursday-window job; run the fixed backfill days ahead, throttled, and watch replica lag.
7. Step 2 before step 3 deploys code that raises `OrderState(None)` on every existing order and makes `mark_paid` a silent no-op (provider gets 2xx, payment lost) on 3.87M pending orders; app must read `state` with fallback to `status` until backfill completes.
8. During the 6-minute rolling deploy old pods write only `status` and new pods write only `state`, so paid webhooks handled by the other generation no-op; new code must write both columns and match on either.
9. `jobs/nightly_finance_export.py` reads `o.status` and the grep only covered `app/`; migrate the export to `state IN (1,2)` in this PR, grep the whole repo, and ask who else queries the replicas (Looker, BI) before any drop.
10. Even before 0143, rows the new code inserts have `status` NULL, so Friday's 02:00 UTC export silently omits them; that is why item 9 must land with the app deploy, not with 0143.
11. 0143's `SET NOT NULL` full-scans 61M rows under ACCESS EXCLUSIVE, blocking all reads and writes; add `CHECK (state IS NOT NULL) NOT VALID`, `VALIDATE CONSTRAINT`, then `SET NOT NULL`, then drop the check.
12. 0143's drop index and drop column take ACCESS EXCLUSIVE with no `lock_timeout`, so they queue behind any long query and block everything behind them (and cancel replica queries on replay); set `lock_timeout` and run off-peak.
13. 0143's downgrade recreates an empty `status`, so the drop is irreversible data loss; keep `status` for at least one release after readers move, or snapshot it first.
14. 0142's concurrent index leaves an INVALID index if it fails, and downgrade will not clean it up; check `pg_index.indisvalid` after step 1 and drop concurrently on downgrade.
15. Tests ran only on a fresh schema, so neither the backfill nor 0143 has been run end to end against real data; rehearse 0142 -> backfill -> 0143 on a prod-like copy including the odd spellings.
16. Add before step 2: backfill has completed and `SELECT count(*) FROM orders WHERE state IS NULL` is 0.
17. Add after step 2 (all pods on new code): re-run the backfill to catch rows old pods wrote during rollout, then verify `state` agrees with `status` for every row.
18. Add before 0143 (later release): NULL count is 0, export and all replica readers are on `state`, and the Friday export has succeeded once on the new column.