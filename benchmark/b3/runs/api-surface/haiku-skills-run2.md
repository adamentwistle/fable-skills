1. **InvoiceState enum reordering corrupts persisted data** — Disputed inserted at index 2 shifts Paid from 2→3 and Void from 3→4; database records with state=2 (Paid) will deserialize as Disputed=2, state=3 (Void) as Paid=3. Move Disputed to the end or add a data migration that updates all persisted values.

2. **computeLateFee call site not updated: services/notifier/src/reminders.ts:57** — Still calls with old positional signature `computeLateFee(inv, cfg.INVOICE_GRACE_DAYS)`; will crash. Update to `computeLateFee(inv, { graceDays: cfg.BILLING_GRACE_PERIOD_DAYS, ... })`.

3. **computeLateFee call site not updated: scripts/backfill-late-fees.js:22** — Old signature and old env var `INVOICE_GRACE_DAYS`; will crash. Update signature and env var name.

4. **Config variable not renamed in services/notifier/src/reminders.ts:57** — Reads `cfg.INVOICE_GRACE_DAYS` which no longer exists; will be undefined. Update to `BILLING_GRACE_PERIOD_DAYS`.

5. **Config variable not renamed in scripts/backfill-late-fees.js:22** — Reads `process.env.INVOICE_GRACE_DAYS`; won't be set. Update env var name.

6. **Helm configs reference old env var** — infra/helm/billing/values.prod.yaml and values.staging.yaml still set `INVOICE_GRACE_DAYS`; will be ignored. Rename to `BILLING_GRACE_PERIOD_DAYS`.

7. **Runbook documentation out of sync** — docs/runbooks/dunning.md:18 documents `INVOICE_GRACE_DAYS`. Update to `BILLING_GRACE_PERIOD_DAYS`.

8. **Response schema change: downstream consumers not updated** — apps/portal/src/client/hooks/useInvoice.ts:23 reads `total_cents` (now gone); services/reconciler/reconcile.py:64 reads old status 'paid' (now 'settled') and `total_cents`. Despite PR claim they handle both shapes, code shows they don't. Update or confirm external vs. in-repo status.

9. **Response serializer test verification weakened** — Test checks `status.toBeTruthy()` and `total.toBeDefined()` instead of verifying the actual shape (status==='settled', amount/currency structure). Restore specific assertions.

10. **Skipped test confirms enum change breaks persistence** — Test "round-trips state values" is skipped due to fixture DB state misalignment caused by enum reordering; rebuild fixtures or fix enum order first.