1. services/notifier/src/reminders.ts:57 calls computeLateFee with old signature and undefined config property; update to pass options object and use `BILLING_GRACE_PERIOD_DAYS`.

2. scripts/backfill-late-fees.js:22 calls computeLateFee with old positional signature; update to pass options object and rename env var to `BILLING_GRACE_PERIOD_DAYS`.

3. apps/portal/src/client/hooks/useInvoice.ts:23 reads `data.total_cents` which no longer exists in API response; update to read `data.total.amount`.

4. apps/portal/src/client/components/InvoiceBadge.tsx:9 checks `invoice.status === 'paid'` but API now returns `'settled'`; update status comparison.

5. infra/helm/billing/values.prod.yaml and values.staging.yaml reference old config name `INVOICE_GRACE_DAYS`; rename to `BILLING_GRACE_PERIOD_DAYS`.

6. docs/runbooks/dunning.md references old config name `INVOICE_GRACE_DAYS`; update to `BILLING_GRACE_PERIOD_DAYS`.

7. InvoiceState enum shift (Paid 2→3, Void 3→4) requires database migration; skipped test with hardcoded state values [2,3] indicates fixture DB out of sync; clarify migration plan and fixture rebuild timeline before merge.