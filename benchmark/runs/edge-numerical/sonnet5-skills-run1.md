<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-skills-1. Content below the line is the agent's final output, unmodified. -->

---

1. Missing `'price'`/`'qty'` key → raises `KeyError`; fix: validate/access via `.get()` with explicit missing-field error.
2. `None` value for price/qty (null CSV cell) → `TypeError` on `float(None)`/`int(None)`; fix: check for `None` before casting.
3. Empty string `""` for price/qty → `float('')`/`int('')` raise bare `ValueError`; fix: catch and raise with row context.
4. Non-numeric string (e.g. `"abc"`) → bare `ValueError`; fix: wrap cast in try/except naming row index, field, and offending value.
5. `qty` as `"3.0"` → `int('3.0')` raises `ValueError` (int() rejects decimal-looking strings); fix: parse qty via `int(float(qty))` or `Decimal` with integer validation, not raw `int()`.
6. Leading/trailing whitespace (`" 12 "`) → works today but whitespace-only (`"  "`) still raises; fix: `.strip()` explicitly and treat empty-after-strip as invalid.
7. Thousands separators / locale formatting (`"1,000.50"`) → `ValueError`; fix: strip/reject separators explicitly rather than silently failing deep in float().
8. Unicode digits or currency symbols (`"$5"`, full-width digits) → `ValueError` or wrong parse; fix: sanitize/validate charset before cast.
9. `float('nan')` / `float('inf')` parse successfully → poisons total silently (NaN propagates, inf dominates); fix: explicitly reject non-finite values.
10. Negative price or qty → accepted silently, no distinction between legitimate refund and bad data; fix: add explicit sign policy/validation.
11. Extremely large values → float loses precision at large magnitudes (money should never use float); fix: use `Decimal` or integer cents throughout.
12. Float summation drift across many rows → cumulative rounding error in `total`; fix: accumulate in `Decimal`/integer cents, not `float`.
13. No rounding/quantization policy on final total → returns arbitrary float precision (e.g. `19.999999999999996`); fix: quantize to 2 decimal places with defined rounding mode (e.g. `ROUND_HALF_UP`).
14. Duplicate rows → summed twice with no dedup check, easy to miss data-pipeline bug; fix: add optional duplicate detection/counting.
15. `rows` itself `None` or non-iterable → `TypeError` at `for r in rows`; fix: validate input type up front with a clear message.
16. `r` not a dict (malformed row) → `TypeError`; fix: validate row shape before field access.
17. Empty `rows` list → silently returns `0` (int) while normal case should likely return `Decimal('0.00')`; fix: ensure consistent return type regardless of path.
18. All current failures raise bare `ValueError`/`KeyError`/`TypeError` with no row/field/value context → hard to debug bad CSV rows; fix: wrap per-row parsing in try/except that re-raises a descriptive error including row index, field name, and raw value.

---

Model/thinking suitability note (per org policy): this was a well-scoped, single-file code-hardening/enumeration task with no ambiguity or multi-step exploration — Sonnet without extended thinking is appropriate here; no upgrade to Opus or extended thinking was needed.
