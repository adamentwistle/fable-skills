1. **BLOCKING: Enum value insertion breaks existing data.** Adding `Disputed` between `Open` and `Paid` shifts numeric values of all downstream states (Paid: 2→3, Void: 3→4). Existing invoices with `state=2` (Paid) will be read as Disputed after deploy. Requires database migration to rekey existing rows or update the schema to not rely on positional enum values.

2. **BLOCKING: Config rename incomplete.** `INVOICE_GRACE_DAYS` renamed to `BILLING_GRACE_PERIOD_DAYS` but Helm values files not updated: `infra/helm/billing/values.prod.yaml:31` and `infra/helm/billing/values.staging.yaml:29` still set `INVOICE_GRACE_DAYS`, will cause runtime config lookup failure.

3. **BLOCKING: Function signature change not applied everywhere.** `computeLateFee` changed from `(invoice, graceDays: number)` to `(invoice, opts)` but call sites in `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` not updated (CI skipped these packages; they will fail at runtime).

4. **BLOCKING: Config key rename not applied everywhere.** `INVOICE_GRACE_DAYS` references remain in `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22`; will fail at runtime when those services load config.

5. **BLOCKING: API response consumers in portal not updated.** Response shape changed (removed `total_cents`, renamed `status: 'paid'` to `'settled'`, added nested `total` object), but `apps/portal/src/client/hooks/useInvoice.ts:23` still reads `data.total_cents` and `apps/portal/src/client/components/InvoiceBadge.tsx:9` checks `status === 'paid'`. Not updated in diff; will break in portal.

6. **HIGH: Test coverage weakened.** "serializes a paid invoice" test gutted from checking exact values to just `toBeTruthy()` / `toBeDefined()`, no longer verifies response shape correctness.

7. **HIGH: Skipped test indicates incomplete migration.** State round-trip test disabled with comment "flaky since the Disputed change; re-enable once the fixture DB is rebuilt" — known incomplete work.