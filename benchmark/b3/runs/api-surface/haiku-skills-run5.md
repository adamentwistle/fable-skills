1. **`services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` call `computeLateFee` with old signature** — still passing second positional arg instead of options object; both packages were skipped by CI so errors won't be caught until deployment; must update calls to `{ graceDays: ... }` form and test.

2. **`InvoiceState` enum insert at position 2 corrupts existing data** — adding `Disputed` between `Open` and `Paid` shifts indices: state value 2 (currently Paid in DB) reads as Disputed, value 3 (currently Void) reads as Paid; the skipped persistence test confirms breakage; must append `Disputed` at end of enum or run a data migration before this ships.

3. **Client-side response consumers not updated** — `apps/portal/src/client/hooks/useInvoice.ts:23` reads removed `total_cents` field and `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks for removed `status === 'paid'` value; code will crash at runtime when fields are missing; must update or conditionally handle both old and new shapes.

4. **Helm and runbook docs still reference `INVOICE_GRACE_DAYS`** — `infra/helm/billing/values.prod.yaml`, `values.staging.yaml`, and `docs/runbooks/dunning.md` use old key; services will fail to load config; must update all three to `BILLING_GRACE_PERIOD_DAYS`.

5. **Test assertions weakened** — changed from specific field value checks (`expect(res.status).toBe('paid')`) to existence checks (`expect(res.status).toBeTruthy()`); no longer verify response correctness; must restore or add value assertions to catch format errors.

6. **Packages with errors skipped by CI** — `@acme/notifier` and `@acme/scripts` have breaking changes in diff but were not run through test suite; these must either be tested on merge or their changes must be fixed now.