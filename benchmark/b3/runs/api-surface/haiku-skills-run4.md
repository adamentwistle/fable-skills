**BLOCKING: Do not merge.** The PR has multiple unfinished migrations and a critical data corruption issue.

1. **Enum reordering corrupts persisted state**: Adding `Disputed` at index 2 shifts `Paid` from 2→3 and `Void` from 3→4; all existing "Paid" invoices with state=2 in the database will be loaded as "Disputed" post-merge. Reorder enum to append `Disputed` at the end, or run a data migration first.

2. **Function signature breaking change unfinished**: `computeLateFee(invoice, graceDays)` → `computeLateFee(invoice, opts)` breaks untouched callers in `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` (skipped in CI). Update those callsites or keep an old overload for backwards compatibility.

3. **Config name change incomplete**: `INVOICE_GRACE_DAYS` → `BILLING_GRACE_PERIOD_DAYS` is used in `infra/helm/billing/values.{prod,staging}.yaml` and `docs/runbooks/dunning.md`; Helm will fail to load this config post-merge. Update Helm values and runbook.

4. **API response shape change not fully consumed**: Downstream code in `apps/portal/src/client/hooks/useInvoice.ts:23` still reads `data.total_cents` (now undefined), `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks `status === 'paid'` (now "settled"), and `services/reconciler/reconcile.py:64` reads both old fields. Update these callers.

5. **Status "paid" → "settled" not migrated**: InvoiceBadge will break checking for the old status value. Update the condition or add a deprecation path.

6. **Test assertions degraded**: `toInvoiceResponse` test weakened from `expect(res.status).toBe('paid')` to `expect(res.status).toBeTruthy()`; restore to verify the actual expected value is 'settled'.

The author's note claiming downstream consumers are "already updated" contradicts the sweep evidence—multiple unpatched callsites will fail on merge.