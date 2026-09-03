1. Enum value `Disputed` inserted at position 2 shifts numeric state values in the database — existing records with `state=2` (Paid) become `Disputed`, `state=3` (Void) become `Paid`. Requires data migration before deploy.

2. `apps/portal/src/client/hooks/useInvoice.ts:23` accesses removed field `data.total_cents` but response now uses `data.total.amount` — will crash at runtime.

3. `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks `status === 'paid'` but response now sends `'settled'` — broken logic.

4. `services/notifier/src/reminders.ts:57` calls `computeLateFee()` with old signature and old env var `INVOICE_GRACE_DAYS` — will fail at runtime (not tested by CI).

5. `scripts/backfill-late-fees.js:22` calls `computeLateFee()` with old signature and old env var — will fail at runtime (not tested by CI).

6. `infra/helm/billing/values.prod.yaml:31` and `values.staging.yaml:29` use old env var `INVOICE_GRACE_DAYS` instead of `BILLING_GRACE_PERIOD_DAYS` — will fail to load new config key, defaulting instead of using configured values.

7. Test at `packages/billing-core/test/invoice.test.ts` lines 21–25 weakened to check only existence (`toBeTruthy()`, `toBeDefined()`) instead of actual values — no longer validates response schema.

8. Documentation `docs/runbooks/dunning.md:18` references old env var `INVOICE_GRACE_DAYS`.