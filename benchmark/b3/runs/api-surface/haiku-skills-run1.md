1. services/notifier/src/reminders.ts:57 — computeLateFee call uses old positional signature; pass { graceDays: cfg.BILLING_GRACE_PERIOD_DAYS }

2. scripts/backfill-late-fees.js:22 — computeLateFee call uses old positional signature; pass { graceDays: Number(process.env.BILLING_GRACE_PERIOD_DAYS ?? 7) }

3. services/notifier/src/reminders.ts:57 — cfg.INVOICE_GRACE_DAYS removed from config schema; use cfg.BILLING_GRACE_PERIOD_DAYS

4. scripts/backfill-late-fees.js:22 — env var INVOICE_GRACE_DAYS will not be provided; update to BILLING_GRACE_PERIOD_DAYS

5. infra/helm/billing/values.prod.yaml:31 — rename INVOICE_GRACE_DAYS to BILLING_GRACE_PERIOD_DAYS and preserve value 21 (not default 7)

6. infra/helm/billing/values.staging.yaml:29 — rename INVOICE_GRACE_DAYS to BILLING_GRACE_PERIOD_DAYS and preserve value 14

7. docs/runbooks/dunning.md:18 — update INVOICE_GRACE_DAYS reference to BILLING_GRACE_PERIOD_DAYS

8. InvoiceState enum — inserting Disputed at position 2 shifts existing values; all DB rows with state=2 (old Paid) will be read as Disputed after deploy; requires DB migration to rewrite state values before code deploys

9. apps/portal/src/client/hooks/useInvoice.ts:23 — expects data.total_cents which is now nested as data.total.amount; update to read from correct path

10. apps/portal/src/client/components/InvoiceBadge.tsx:9 — checks status === 'paid' but API now returns 'settled'; update condition to 'settled'

11. packages/billing-core/test/invoice.test.ts — toInvoiceResponse test assertions weakened to truthiness checks; restore specific assertions on status, amount, and currency values to catch serialization bugs