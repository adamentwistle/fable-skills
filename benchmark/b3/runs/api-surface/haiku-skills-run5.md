1. **Enum insertion corrupts stored data**: Adding `Disputed` between `Open` and `Paid` shifts all persisted state values by one — existing `Paid` invoices (stored as 2) now read as `Void`. Reorder enum (append `Disputed` at end) or create a data migration before deploy.

2. **Helm values not updated for config key rename**: `infra/helm/billing/values.prod.yaml` and `values.staging.yaml` still set `INVOICE_GRACE_DAYS`; service now expects `BILLING_GRACE_PERIOD_DAYS`. Deploy will use default value (7) instead of configured values, breaking behavior.

3. **Frontend clients broken by API shape change**: `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents` (removed); `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks `status === 'paid'` (now `'settled'`). App will crash or show no badges.

4. **Call sites in skipped packages not updated**: `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` still use old `computeLateFee(inv, graceDays)` signature; turbo skipped testing these, but code will fail at runtime on deploy.

5. **Test weakened on response shape**: `test/invoice.test.ts` changed from `expect(res.status).toBe('paid')` to `expect(res.status).toBeTruthy()`; no longer validates new field structure (`total` object vs flat `total_cents`).

6. **Enum persistence test disabled indefinitely**: `InvoiceState persistence` test skipped with comment "re-enable once fixture DB is rebuilt"; needs explicit migration plan and re-enable date, not an open-ended skip.