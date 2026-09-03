1. `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` still call `computeLateFee()` with old positional-argument signature — update both to options object format `{ graceDays: ... }`.

2. Helm config files (`values.prod.yaml`, `values.staging.yaml`) and runbook still reference `INVOICE_GRACE_DAYS` but code now reads `BILLING_GRACE_PERIOD_DAYS` — env var mismatch will fail at runtime.

3. Portal client (`apps/portal/src/client/hooks/useInvoice.ts:23` and `InvoiceBadge.tsx:9`) still reads `total_cents` field and checks `status === 'paid'` but API now returns `total: {amount, currency}` and status `'settled'` — UI will break.

4. Reconciler service (`services/reconciler/reconcile.py:64`) still uses old response shape (`total_cents`) and checks `status == "paid"` — reconciliation will fail.

5. Enum shift (adding `Disputed` between `Open` and `Paid`) changes numeric values: existing DB rows with `state=2` (was Paid) now read as Disputed — requires data migration or schema change to prevent state misinterpretation in production.

6. Test explicitly skipped due to enum-value mismatch, but no migration listed in diff — unclear when/how DB will be rebuilt for this data-breaking change.