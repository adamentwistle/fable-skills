1. **Critical data corruption risk:** Adding `Disputed` between `Open` and `Paid` in the enum shifts subsequent state values (Paid: 2→3, Void: 3→4); existing DB records with state 2 and 3 will read as wrong states on deploy. Reorder enum to put `Disputed` at the end, or add database migration to update existing records.

2. `services/notifier/src/reminders.ts:57` calls `computeLateFee(inv, cfg.INVOICE_GRACE_DAYS)` with old signature and config name; update to match options object format and `BILLING_GRACE_PERIOD_DAYS`.

3. `scripts/backfill-late-fees.js:22` calls `computeLateFee` with old signature and `INVOICE_GRACE_DAYS`; update both.

4. `infra/helm/billing/values.prod.yaml` and `values.staging.yaml` still define `INVOICE_GRACE_DAYS`, not renamed `BILLING_GRACE_PERIOD_DAYS`; update both files.

5. `apps/portal/src/client/hooks/useInvoice.ts:23` accesses removed `data.total_cents`; update to `data.total.amount`.

6. `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks status `'paid'` but response now returns `'settled'`; update condition.

7. `services/reconciler/reconcile.py:64` checks for removed `status == "paid"` and `total_cents`; verify claim that reconciler handles both old and new shapes, or update.

8. Skipped test + weakened assertions leave enum/state persistence untested; re-enable after enum fix and DB rebuild.