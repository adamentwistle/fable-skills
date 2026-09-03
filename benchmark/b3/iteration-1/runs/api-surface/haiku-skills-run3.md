1. **Function signature not updated at all call sites**: services/notifier/src/reminders.ts:57 and scripts/backfill-late-fees.js:22 still call `computeLateFee` with positional `graceDays` parameter; old signature no longer exists.

2. **Config key rename incomplete**: infra/helm/billing/values.prod.yaml and values.staging.yaml still set `INVOICE_GRACE_DAYS`; schema expects `BILLING_GRACE_PERIOD_DAYS` and will reject unknown keys.

3. **Enum value inserted in middle breaks database deserialization**: Disputed added between Open and Paid shifts Paid from 2→3 and Void from 3→4; existing database records with state=2 will deserialize as Disputed instead of Paid, state=3 as Paid instead of Void.

4. **Response schema change breaks portal client**: apps/portal/src/client/hooks/useInvoice.ts:23 reads `data.total_cents` which is no longer in response (replaced with `total.amount`); will be undefined.

5. **Status string change not reflected in portal component**: apps/portal/src/client/components/InvoiceBadge.tsx:9 checks `status === 'paid'` but API now returns 'settled'; badge will never show success state.

6. **Serialization test validation removed**: Test for paid invoice went from checking exact status/field values to only checking truthiness; does not verify the new shape is correct.

7. **CI skipped affected packages**: @acme/notifier and @acme/scripts not tested despite changes breaking their code; run full suite before merge.