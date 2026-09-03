**Blockers**

1. Enum reorder corrupts stored data — inserting `Disputed` before `Paid` shifts Paid 2→3 and Void 3→4, but `invoices.state` is a persisted SMALLINT; every existing paid row now reads as Disputed and every void row as Paid. Append `Disputed` last or assign explicit values, and ship a migration if any renumbering stands.
2. The one test that would have caught #1 was skipped, not fixed — `it.skip('round-trips state values')` asserts exactly `state: 2 → Paid, 3 → Void`. It isn't flaky; it's failing correctly. Un-skip and make it pass.
3. `services/notifier/src/reminders.ts:57` still passes a number to `computeLateFee` — `opts.graceDays` is `undefined`, so every fee computes as `NaN` and `NaN > 0` is false, silently zeroing late fees on reminders. Update the call site.
4. `scripts/backfill-late-fees.js:22` has the same broken positional call and reads the deleted `INVOICE_GRACE_DAYS` env var; it's plain JS so nothing typechecks it. Update it.
5. CI green proves nothing here — `--filter='[origin/main]'` skipped `@acme/notifier`, `@acme/reconciler-client`, and `@acme/scripts`, which are precisely the packages holding the broken call sites. Require a full-repo `turbo run typecheck test` before merge.
6. Prod grace period silently drops 21 → 7 days on deploy — Zod ignores unknown keys, so `INVOICE_GRACE_DAYS: "21"` in `values.prod.yaml` (and `"14"` in staging) is discarded and the new 7-day default applies, charging late fees two weeks early. Accept both keys with a deprecation warning, and update both values files in this PR.
7. `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents`, which no longer exists — in-repo consumer, outside the author's mobile/reconciler assurance. Fix in this PR.
8. `apps/portal/src/client/components/InvoiceBadge.tsx:9` matches `status === 'paid'`, now `'settled'`, so paid invoices lose their badge. Fix in this PR.
9. `services/reconciler/reconcile.py:64` matches both `status == "paid"` and `inv["total_cents"]` — it won't crash, it will just stop matching and silently under-reconcile. Confirm the deployed reconciler, not just the claim.
10. The serializer also feeds the `billing.invoice.updated` event via `events.ts`, so this is a wire-schema break for external subscribers no grep can enumerate — the PR description covers only the HTTP route. Version the event or keep the old fields.
11. Response change is breaking, not additive — keep `total_cents`/`currency` alongside `total` for a deprecation window, or cut a `/v2` route; the platform-team assurance covers two consumers, not the contract.

**Should fix before merge**

12. `total.amount` becomes a decimal *string* via `toFixed(2)` — a type change on top of the field move, and wrong for zero-decimal currencies like JPY. Keep integer minor units.
13. `version: 2.4.0` is a minor bump for a breaking export signature and a breaking response schema — needs a major bump and a changelog entry.
14. The route and the dunning job now compute different fees — `invoiceRoutes.ts:88` omits `rateBps` and falls to the hardcoded `150`, while `dunning.ts:41` passes `config.LATE_FEE_RATE_BPS`. Pass config in both, and drop the literal `150` that duplicates the schema default.
15. The serializer test was weakened to `toBeTruthy()`/`toBeDefined()`, which would pass against any object — assert the actual new shape and status string.
16. `docs/runbooks/dunning.md:18` still tells on-call to set `INVOICE_GRACE_DAYS` to pause late fees during an incident; that knob is now inert. Update it with the config rename.