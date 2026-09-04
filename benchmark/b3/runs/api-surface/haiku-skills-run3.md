1. **Incomplete signature migration**: `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` still call `computeLateFee()` with old positional signature; must pass options object.

2. **Config key rename incomplete**: `INVOICE_GRACE_DAYS` still exists in `services/notifier/src/reminders.ts`, `scripts/backfill-late-fees.js`, `infra/helm/billing/values.prod.yaml`, `infra/helm/billing/values.staging.yaml`, and `docs/runbooks/dunning.md`; rename all to `BILLING_GRACE_PERIOD_DAYS`.

3. **Response format changes not consumed in monorepo**: `apps/portal/src/client/hooks/useInvoice.ts:23` still accesses `data.total_cents`, `apps/portal/src/client/components/InvoiceBadge.tsx:9` still checks `status === 'paid'`, and `services/reconciler/reconcile.py:64` still expects old format; update consumers before deploying API change.

4. **InvoiceState enum insertion breaks stored data**: Adding `Disputed` as state value 2 shifts `Paid` from 2→3, corrupting all existing paid invoices to appear as disputed without a data migration; add a schema migration to renumber stored state values before merging.

5. **Test degraded, not updated**: `toInvoiceResponse` test now only checks `toBeTruthy()` and `toBeDefined()` instead of verifying the new response shape (`status: 'settled'`, `total.amount`); restore actual value assertions.