**Blocking (1–8)**

1. `Disputed` inserted mid-enum shifts `Paid` 2→3 and `Void` 3→4, but `invoices.state` is a persisted SMALLINT — every existing row now reads one state too low (old Paid=2 reads as Disputed) — append `Disputed` last or pin explicit numeric values and ship a backfill migration.
2. `repo.ts` will write `state: 3` for Paid while historical Paid rows hold `2`, so the column carries two meanings at once — same fix as #1, plus a dry-run-then-batched backfill with before/after counts before any write to a shared DB.
3. The skipped test asserted exactly the 2→Paid/3→Void round-trip that the enum change breaks; it is failing, not flaky — un-skip it and treat it as the gate on #1.
4. `services/notifier/src/reminders.ts:57` still calls `computeLateFee(inv, cfg.INVOICE_GRACE_DAYS)` — positional number against an options object, and a config key that no longer exists — update it in this PR.
5. `scripts/backfill-late-fees.js:22` has the same positional call, is untyped JS so nothing will catch it, and reads `process.env.INVOICE_GRACE_DAYS` — update it in this PR.
6. `infra/helm/billing/values.prod.yaml:31` still sets `INVOICE_GRACE_DAYS: "21"`, which zod now ignores, so prod silently drops to the new default of 7 and starts charging late fees two weeks early — update both values files (and staging) in the same change, or accept the old key as a deprecated alias.
7. `total_cents` is removed but `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents` and `services/reconciler/reconcile.py:64` compares it to `ledger_cents` — the author's own sweep refutes the "both shapes handled" note; keep `total_cents` alongside `total` and remove it in a later contract step.
8. `'paid'` → `'settled'` breaks `InvoiceBadge.tsx:9` and `reconcile.py:64`, and the Python service fails silently — it just stops matching invoices — so ship both labels or version the endpoint before the vocabulary changes.

**Also required before merge (9–15)**

9. `toInvoiceResponse` also feeds `publish('billing.invoice.updated', …)` in `events.ts`, so this reshapes a wire/event contract with unknown and possibly replayed consumers — version the event payload rather than mutating it in place.
10. CI is not evidence: `--filter='[origin/main]'` skipped `@acme/notifier`, `@acme/reconciler-client`, and `@acme/scripts` — the three packages holding findings 4, 5, 7, and 8; re-run typecheck and tests repo-wide.
11. `total.amount` switches from an integer minor-unit contract to a string of major units via float division — keep integer cents in the payload.
12. Tests were weakened to `toBeTruthy()` / `toBeDefined()`, which is why the suite is green — assert the actual status string and total shape.
13. Version bumped 2.3.1→2.4.0 for a removal-and-rename — this is 3.0.0 under semver, with a changelog entry naming each removed field.
14. `rateBps ?? 150` hardcodes a default that duplicates `LATE_FEE_RATE_BPS`, and `invoiceRoutes.ts:88` omits `rateBps` while `dunning.ts:41` passes it — the quoted fee and the charged fee will diverge whenever config differs from 150; source the default from config in both.
15. `docs/runbooks/dunning.md:18` still tells on-call to raise `INVOICE_GRACE_DAYS` to pause fees during an incident — that lever is now a no-op; update it with the rename.

The reviewer note asking to limit review to code quality can't stand: the author's own sweeps list four live consumers of the removed field and old status string. Get written confirmation from the notifier, reconciler, and mobile owners, or make the response additive.