Not shippable Thursday. The backfill silently migrates about half the rows, and the staging log the PR quotes as a success is the proof.

1. The backfill's `LIMIT/OFFSET` paging combines with `WHERE state IS NULL`: each updated batch leaves the result set, so the next `OFFSET` skips that many still-unmigrated rows — fix by keyset paging on `id > last_id` and dropping `OFFSET` entirely.
2. Staging already failed this way and was read as green: `done: 1055000` is exactly 211 batches of 5000, which is where the drift math stops (`5000k > total − 5000k` at k=211) — 1,049,377 staging rows still have `state IS NULL` today; go confirm that count before anything else.
3. `MAPPING` covers only the five lowercase spellings, so `PAID` (5210), `canceled` (1988), `complete` (417) and NULL (149) fall through to NULL — add the legacy spellings to the `CASE`.
4. `complete` and the 149 NULLs have no `OrderState` member at all — that is a product decision for the orders owner, not a mapping the reviewer or author can pick.
5. Those two bugs together guarantee `0143`'s `SET NOT NULL` aborts mid-window on prod — no rollback plan is written for a failed step 4.
6. `with conn.transaction():` wraps the whole loop, so this is one transaction over 61M rows, not a batched backfill — commit per batch so it is resumable and does not hold a snapshot for hours.
7. Runtime does not fit the window: staging went 31s for the first 100k but 627s by 1M (linear would be ~310s), so per-batch cost grows with offset; prod's 61.4M rows are 29.2× staging, giving 5.4 hours at the linear floor and ~150 hours at the observed quadratic rate.
8. `jobs/nightly_finance_export.py` selects and filters on `o.status` and was missed because the grep was scoped to `app/` — migrate it to `state` in the same release.
9. That export breaks before any drop: from the moment step 2 deploys, new orders are written with `status` NULL, so `status IN ('paid','shipped')` silently omits them from the Finance Looker load — dual-write both columns instead.
10. Step 2 deploys the new reader before the backfill, and `OrderState(row["state"])` raises `ValueError` on NULL, so every pre-existing order 500s for the hours between step 2 and step 4 — backfill first, and make `from_row` tolerate NULL for one release.
11. During the ~6 min rolling deploy old pods write `status` only, so rows created then keep `state` NULL even after the backfill passes them — dual-write, or a sync trigger, closes that hole.
12. `mark_paid` matches on `state = PENDING`, so for any not-yet-backfilled pending order it updates zero rows and still returns 2xx to the payment webhook — a silently lost payment; assert `rowcount` and match on either column during the transition.
13. `op.alter_column(..., nullable=False)` takes ACCESS EXCLUSIVE and full-scans 61M rows — add a `NOT VALID` check, `VALIDATE CONSTRAINT`, then `SET NOT NULL` so PG15 skips the scan.
14. `0143`'s downgrade recreates `status` empty, so it restores the schema and not the data — rename to `status_deprecated` and drop it a release later instead.
15. The script has no dry-run mode — add one that reports counts and sample IDs without writing, so "expected 61.4M, script says 30.7M" is caught before the real run.
16. Nothing reconciles counts: `done` is incremented by `BATCH` rather than `cur.rowcount`, and the script never re-queries `count(*) WHERE state IS NULL` at the end — that omission is exactly why finding 2 shipped.
17. Expand, migrate and contract are collapsed into one Thursday window; `0143` belongs in a separate release days after the backfill reconciles.
18. `SELECT *` with asyncpg means dropping `status` invalidates cached statement plans on live connections — expect `InvalidCachedStatementError` until pods recycle.
19. A multi-hour single transaction against a primary with two streaming read replicas will lag them and stall vacuum — batch, throttle, and watch replica lag during the run.
20. If `CREATE INDEX CONCURRENTLY` in `0142` fails it leaves an INVALID index that blocks a re-run — document dropping it before retrying.
21. Tests only run against a fresh schema at head, so nothing covers a row with `state` NULL or the mixed-write window — add a test that reads old-shape data.
22. Before step 1: grep the whole repo and any other service for `orders.status`, not just `app/`; the one reader shown here was already missed.
23. Before step 1: run `alembic upgrade 0142`, `downgrade`, `upgrade` locally — the down paths have not been exercised.
24. Before step 1: confirm PITR or a `status` before-image covers the drop, and get Finance's sign-off on the export change.
25. New step, ahead of the current step 2: ship a dual-write release that writes both columns and reads either, and let it soak.
26. Between the fixed backfill and `0143`: `SELECT count(*) FROM orders WHERE state IS NULL` must return 0, and spot-check ~20 IDs through the API read path, not just SQL.
27. After the backfill: leave `0143` for a later release once error rates are clean and every reader is confirmed on `state`.
28. I could not verify `app/api/orders.py` or the tests, since neither is shown, and I could not grep the repo — the reader list here is only what the PR text contains, so finding 8 may not be the only miss.