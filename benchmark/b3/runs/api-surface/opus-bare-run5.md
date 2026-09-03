1. **Blocker — silent data corruption:** inserting `Disputed` before `Paid` renumbers the enum (Paid 2→3, Void 3→4) while `invoices.state` is a SMALLINT holding the old ordinals, so every stored Paid row reads back as Disputed; append new states at the end (or pin explicit values, e.g. `Disputed = 4`) and never reorder.

2. **Blocker:** the `it.skip`'d round-trip test is not flaky — it seeds state 2/3 and expects Paid/Void, which is exactly the corruption in #1; un-skip it and let it fail until the enum is fixed.

3. **Blocker:** `services/notifier/src/reminders.ts:57` and `scripts/backfill-late-fees.js:22` still pass a positional number to `computeLateFee`, so `opts.graceDays` is `undefined` and the fee becomes `NaN` (the backfill script writes it); update both callers in this PR.

4. **Blocker — CI is not green for this change:** `--filter='[origin/main]'` skipped `@acme/notifier`, `@acme/reconciler-client` and `@acme/scripts`, which are the packages that break; re-run including dependents (`...` filter) before merge.

5. **Blocker:** `infra/helm/billing/values.prod.yaml:31` still sets `INVOICE_GRACE_DAYS: "21"`, which zod now strips, so prod silently falls to the new 7-day default and starts charging late fees 14 days early; update prod/staging values and sequence the config change with the deploy.

6. **Blocker:** the author's own sweep contradicts the "consumers are compatible" note — `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents` (now undefined) and `services/reconciler/reconcile.py:64` matches `status == "paid"` and `total_cents`; either keep the old fields alongside the new ones for a deprecation window or land the consumer changes first.

7. **Blocker:** `apps/portal/src/client/components/InvoiceBadge.tsx:9` compares `status === 'paid'`, so paid invoices lose their badge the moment this ships; update it in this PR since it is in the same repo.

8. **Blocker:** `toInvoiceResponse` also serializes the `billing.invoice.updated` event, so this is an unversioned break of a published event contract, not just a REST change; version the event or keep the event payload on the old shape.

9. `version` goes 2.3.1 → 2.4.0 for a set of breaking API, config and enum changes; bump to 3.0.0.

10. The serializer tests were weakened to `toBeTruthy()`/`toBeDefined()`, which is why the shape change passed; restore concrete assertions on `settled`, `total.amount` and `total.currency`.

11. `total.amount` is now a string from `toFixed(2)` and hardcodes a 2-decimal minor unit, so JPY and other zero-decimal currencies serialize wrong; derive the exponent from the currency or keep integer cents.

12. `rateBps ?? 150` duplicates the `LATE_FEE_RATE_BPS` default, and `invoiceRoutes.ts:88` omits `rateBps` while `dunning.ts:41` passes it — the same invoice can quote one fee and be charged another; pass the config value at both call sites and drop the literal.

13. `docs/runbooks/dunning.md:18` tells on-call to raise `INVOICE_GRACE_DAYS` to pause late fees during an incident, which is now a no-op; update the runbook with the new name.

14. On the reviewer note: I'm not treating downstream compatibility as out of scope, because the sweeps included in this PR show three in-repo consumers that break — get that confirmation in writing against the actual field names before re-requesting review.