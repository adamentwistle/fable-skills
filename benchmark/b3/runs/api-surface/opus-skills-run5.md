1. **BLOCKER — enum renumbering corrupts persisted state.** Inserting `Disputed` before `Paid` shifts `Paid` 2→3 and `Void` 3→4, and `invoices.state` is a SMALLINT holding those numbers; every existing paid row will read back as `Disputed` and every void row as `Paid`. Append `Disputed` last (or pin explicit values `Draft=0…Void=3, Disputed=4`) — otherwise this needs a backfill migration plus expand/migrate/contract sequencing, not a one-line enum edit.

2. **BLOCKER — the skipped test is the one that catches finding 1.** `it.skip('round-trips state values through the invoices table')` seeds `state: 2`/`state: 3` and asserts `[Paid, Void]`; it started failing *because* the change is wrong, not because the fixture DB is stale. Un-skip it and let it fail before merging.

3. **BLOCKER — `computeLateFee` still called positionally in two places.** `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` pass a bare number; `opts.graceDays` is `undefined`, `overdue` is `NaN`, `NaN <= 0` is false, so both emit `NaN` late fees rather than throwing. Migrate both call sites in this PR (5 hits total: 1 definition, 2 migrated, 2 not).

4. **BLOCKER — CI green is not evidence.** `turbo run typecheck test --filter='[origin/main]'` skipped `@acme/notifier`, `@acme/reconciler-client` and `@acme/scripts` — exactly the packages holding the broken call sites. Re-run typecheck and test across the whole workspace before this is mergeable.

5. **BLOCKER — config rename silently drops the production grace period.** `infra/helm/billing/values.prod.yaml:31` sets `INVOICE_GRACE_DAYS: "21"` and staging sets `14`; `z.object` strips unknown keys instead of erroring, so both environments fall to the new default of 7 and start charging late fees up to 14 days earlier than today. Either accept both keys with a deprecation warning, or update both values files in this same change.

6. **BLOCKER — response shape break has unmigrated in-repo consumers.** `total_cents` and `currency` are removed; `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents` (now `undefined` — typecheck passed only because the payload is untyped) and `services/reconciler/reconcile.py:64` compares `inv["total_cents"]`. Keep `total_cents` and `currency` alongside `total` for one release, or migrate both consumers here.

7. **BLOCKER — `'paid'` → `'settled'` breaks two live status checks.** `apps/portal/src/client/components/InvoiceBadge.tsx:9` will stop rendering the Paid badge, and `reconcile.py:64` will match zero settled invoices, silently reporting everything as unreconciled. Same treatment as finding 6.

8. **The "platform team confirmed both shapes" note is contradicted by the author's own sweep** — `reconcile.py:64` keys on both `"paid"` and `"total_cents"`. Get that claim in writing against the actual reconciler code, or drop it; downstream breakage is in scope for a wire-format change regardless of the reviewer note.

9. **`billing.invoice.updated` event payload changes with no version or notice.** `events.ts` publishes `toInvoiceResponse(inv)` directly, so findings 6 and 7 hit every out-of-repo event consumer too, and the PR description doesn't mention it. Version the event or dual-emit.

10. **Version bump is wrong.** `2.3.1 → 2.4.0` for a published package that removes response fields, changes an exported function signature and renumbers an exported enum — this is `3.0.0`, with a changelog entry naming the migration.

11. **`rateBps` disagrees between the two live call sites.** Dunning passes `config.LATE_FEE_RATE_BPS`, the `GET /v1/invoices/:id` route doesn't, so the fee shown to the customer falls back to the hardcoded `150` while the fee actually applied uses the configured rate. Pass config in both, and source the default from `LATE_FEE_RATE_BPS` rather than duplicating `150` in `lateFee.ts`.

12. **The serializer test was weakened to a tautology.** `expect(res.status).toBeTruthy()` and `expect(res.total).toBeDefined()` pass for `'draft'` and `{}`; restore exact assertions on `'settled'`, the amount and `'GBP'`.

13. **Money formatted via float division.** `(inv.totalCents / 100).toFixed(2)` also silently mis-renders zero-decimal currencies (JPY), and changes the amount's type from integer to decimal string — call that out in the migration note for consumers.

14. **`docs/runbooks/dunning.md:18` becomes wrong.** The documented incident lever ("set `INVOICE_GRACE_DAYS` high to pause late fees") turns into a no-op; update it in this PR.

15. **Two changes are bundled that should be separable** — the grace-period *rename* and the default *lowering* 14→7. Land the rename compatibly first; the default change is a finance-visible behavior change that deserves its own approval.

16. **Unverifiable from the material given, state these as open before merge:** whether a migration directory exists for finding 1, whether any out-of-repo consumer reads `total_cents`/`'paid'`, and whether the mobile app was actually tested against the new shape. The one check to run first: apply the branch to a copy of the invoices table and read back a known paid row.