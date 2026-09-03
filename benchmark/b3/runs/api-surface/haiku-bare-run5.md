1. services/notifier/src/reminders.ts:57 — computeLateFee signature changed but call not updated; pass {graceDays} options object instead of bare number.

2. scripts/backfill-late-fees.js:22 — computeLateFee call uses old signature and old config name; update call and use BILLING_GRACE_PERIOD_DAYS.

3. infra/helm/billing/values.prod.yaml and values.staging.yaml — environment variable renamed INVOICE_GRACE_DAYS → BILLING_GRACE_PERIOD_DAYS; update both.

4. apps/portal/src/client/hooks/useInvoice.ts:23 — total_cents field removed from response shape; update to access total.amount instead.

5. apps/portal/src/client/components/InvoiceBadge.tsx:9 — status 'paid' renamed to 'settled' in responses; update condition.

6. services/reconciler/reconcile.py:64 — total_cents field and 'paid' status no longer exist; update to use total.amount and 'settled'.

7. InvoiceState enum reordering (Disputed inserted at index 2) breaks interpretation of existing database records with state=2 (now reads as Disputed, was Paid) and state=3 (now reads as Paid, was Void); add migration or move Disputed to end of enum to preserve numeric mappings.