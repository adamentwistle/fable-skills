**Blockers**

1. `InvoiceState.Disputed` inserted mid-enum renumbers Paid 2→3 and Void 3→4, and `invoices.state` is a persisted SMALLINT — every existing Paid row now reads as Disputed and Void as Paid; append `Disputed` at the end or pin explicit numeric values, and ship a migration if you renumber.
2. The test that would have caught #1 was `it.skip`'d as "flaky since the Disputed change" — it was not flaky, it was correct; re-enable it and let it fail until the enum is fixed.
3. `services/notifier/src/reminders.ts:57` still calls `computeLateFee(inv, cfg.INVOICE_GRACE_DAYS)` — `opts.graceDays` is undefined, so every fee is `NaN`; update the call site (and the config key it reads, which no longer exists).
4. `scripts/backfill-late-fees.js:22` passes a bare number too, and being JS gets no typecheck — it will write `NaN` fees to real rows; update it before merge.
5. CI's `--filter='[origin/main]'` skipped `@acme/notifier`, `@acme/reconciler-client` and `@acme/scripts`, which is exactly where #3 and #4 live — "green" proves nothing here; require a full-repo `turbo run typecheck test` on this PR.
6. `infra/helm/billing/values.prod.yaml:31` still sets `INVOICE_GRACE_DAYS: "21"`, which the new schema ignores — prod silently drops to the new default of 7, applying late fees 14 days early to every overdue customer; update both values files (and `docs/runbooks/dunning.md:18`) in this PR.
7. `apps/portal/src/client/hooks/useInvoice.ts:23` reads `data.total_cents`, now removed — the portal's own UI breaks; this is in-repo, not a downstream concern.
8. `apps/portal/src/client/components/InvoiceBadge.tsx:9` matches `status === 'paid'`, which the serializer no longer emits — paid invoices lose their badge; same, in-repo.
9. `services/reconciler/reconcile.py:64` matches on both `status == "paid"` and `total_cents` — every settled invoice stops reconciling; the "platform team confirmed both shapes" claim is contradicted by the code in this repo, so get that in writing against this diff or fix the consumer.
10. `toInvoiceResponse` also builds the `billing.invoice.updated` event payload (`events.ts`), so this is an unversioned wire-format break for every event consumer, not just the REST endpoint — version the payload or keep `total_cents`/`currency` alongside the new `total` for a deprecation window.
11. `total.amount` as `(totalCents / 100).toFixed(2)` is a lossy minor-unit assumption — zero-decimal currencies (JPY) and any client doing integer math both break; keep integer minor units in the payload.
12. Version bumped 2.3.1 → 2.4.0 for a set of breaking changes to an exported function, response shape and config key — that's 3.0.0 under semver, and the changelog entry is missing.

**Should be fixed before merge**

13. The serializer test was weakened to `toBeTruthy()` / `toBeDefined()`, which passes for any value — it no longer asserts the status vocabulary or the amount; assert the actual `settled` label and `{amount, currency}` values.
14. `invoiceRoutes.ts:88` omits `rateBps` while `dunning.ts:41` passes `config.LATE_FEE_RATE_BPS` — the same invoice gets two different fees whenever the config value isn't 150; pass config in both.
15. The `rateBps ?? 150` fallback duplicates the zod default in `config.ts`; drop the literal and require the caller to supply it, or the two defaults will drift.
16. The author's sweeps under-scope the change: sweep 1 and 2 are TS/JS-typed so they miss `reconcile.py`, and sweep 3 is scoped to `apps services` so it misses scripts, docs and fixtures — re-run each unscoped before merge.