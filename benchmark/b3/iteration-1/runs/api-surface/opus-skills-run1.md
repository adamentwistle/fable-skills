**Blocking (1–8).**

1. Inserting `Disputed` before `Paid` shifts every enum ordinal — `invoices.state` is a persisted SMALLINT, so all existing rows storing 2 (Paid) now read as Disputed and 3 (Void) reads as Paid; append `Disputed` at the end or assign explicit values, and either way no data migration is needed only if ordinals are unchanged.
2. The persistence round-trip test wasn't flaky — it seeds raw `state: 2`/`3` and expects Paid/Void, i.e. it is the test that caught finding 1; un-skip it and fix the enum rather than the fixture DB.
3. `services/notifier/src/reminders.ts:57` still passes a bare number as the second argument, so `opts.graceDays` is undefined and `computeLateFee` returns `NaN` (NaN <= 0 is false, so the early return doesn't fire); update the call site.
4. `scripts/backfill-late-fees.js:22` has the same bare-number call plus a dead `INVOICE_GRACE_DAYS` env read, and it's JavaScript so typecheck will never catch it; update it and its env var.
5. CI never built the broken packages — `--filter='[origin/main]'` selects only changed packages, and the log explicitly skips `@acme/notifier`, `@acme/reconciler-client`, `@acme/scripts`; re-run with `--filter='...[origin/main]'` before any merge, and treat "CI is green" as unverified until then.
6. `infra/helm/billing/values.prod.yaml:31` and `values.staging.yaml:29` still set `INVOICE_GRACE_DAYS`, which zod now strips as an unknown key, so prod silently drops from 21 days to the new default 7 and starts charging late fees ~two weeks early; rename in both values files in the same change.
7. Removing `total_cents` and renaming `paid` → `settled` breaks three consumers the author's own sweep lists — the portal hook, the badge component, and `services/reconciler/reconcile.py:64`, where the reconciler's `and` condition just goes permanently false and reconciliation silently matches nothing; keep the old fields alongside the new ones and remove them in a later release.
8. The same serializer feeds `billing.invoice.updated` (`events.ts`), so this is an unversioned event-schema break for every queue consumer, and messages already queued/stored in the old shape will be read by new code; the PR description doesn't mention the event surface at all.

**Should fix before merge (9–14).**

9. The reviewer note's claim that consumer compatibility is covered is contradicted by the author's own third `rg` sweep; get that confirmation in writing against the actual field list, or apply finding 7.
10. `invoiceRoutes.ts:88` omits `rateBps` while `dunning.ts:41` passes `cfg.LATE_FEE_RATE_BPS`, so the fee shown on GET diverges from the fee actually applied whenever the configured rate isn't 150; pass the config value on both paths.
11. The serializer test now asserts only `toBeTruthy()`/`toBeDefined()` — it would pass with `status: 'banana'`; restore exact assertions on the new shape.
12. `total.amount` changes type from integer cents to a decimal string via float division, which is a silent retype for anything parsing it and is wrong for zero- and three-decimal currencies; keep integer minor units.
13. Version should be `3.0.0`, not `2.4.0` — `computeLateFee`'s signature, the config key, and the response shape are all breaking for external consumers.
14. `docs/runbooks/dunning.md:18` still tells on-call to raise `INVOICE_GRACE_DAYS` to pause late fees during an incident, a lever that now does nothing; update the runbook and add the changelog/migration note for the config rename and the default change from 14 to 7.