<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-bare-5. Content below the line is the agent's final output, unmodified. -->

---

1. Missing `price`/`qty` key on a row → `KeyError`; use `.get()` with validation instead of `r[...]`.
2. Non-numeric/malformed string ("abc", "", None) → `ValueError`/`TypeError`; validate and skip/log or raise a domain error.
3. `int(qty)` rejects decimal quantities ("2.5") → `ValueError`; decide policy (reject vs. treat as float).
4. `float()` silently accepts "nan"/"inf"/"-inf" → poisons total with NaN/∞; explicitly reject non-finite values.
5. `float()` accepts scientific notation ("1e3") and locale junk like "$1,200.50" fails → inconsistent parsing; normalize/strip currency symbols and separators, or reject.
6. Negative price or qty accepted silently → could zero out or invert revenue (fraud/bad data); enforce non-negative (or explicit allowlist for refund rows).
7. Floating-point accumulation of money → rounding drift over many rows; use `Decimal` (or integer cents) instead of `float`.
8. Extremely large numeric strings → `float` overflow to `inf` or huge distortion; cap/validate magnitude.
9. One bad row aborts the entire aggregation (no isolation) → wrap per-row parsing in try/except, collect errors, continue.
10. `rows` itself `None` or not iterable → `TypeError` on `for r in rows`; guard/validate input type upfront.
11. Row is not a dict (e.g., malformed CSV → list/None) → `TypeError`/`KeyError`; validate row shape before indexing.
12. Whitespace-only or unicode digit strings parse inconsistently across locales → normalize/strip before parsing.
13. No overflow/precision guard on the running `total` (starts as `int` 0, becomes `float`) → type drift masks precision loss; initialize as `Decimal('0')`.
14. Silent empty-list case returns `0` — confirm that's the intended "no data" signal vs. raising/flagging.
15. No logging/telemetry on skipped or rejected rows → data-quality issues go unnoticed; emit metrics/log per rejected row.
16. `qty` truncation via `int()` on non-integer-looking strings depends on Python's strict parsing (no silent truncation, good) — but confirm downstream doesn't `int(float(qty))` elsewhere, which *would* silently truncate.

---
**Model/settings suitability check:** This request (enumerate edge cases in a small function) is a bounded, well-scoped review task — Sonnet 5 at moderate reasoning effort is appropriate; no change needed.
