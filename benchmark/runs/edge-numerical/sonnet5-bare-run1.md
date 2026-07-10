<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-bare-1. Content below the line is the agent's final output, unmodified. -->

---

1. Missing 'price'/'qty' keys → KeyError; use `r.get(...)` with validation or explicit required-field check.
2. Empty string price/qty (`''`) → `float('')`/`int('')` raises ValueError; check for blank before parsing.
3. Non-numeric garbage (letters, symbols) → ValueError; wrap parse in try/except and skip/report bad row.
4. `None` values (blank CSV cell parsed as None) → TypeError on `float(None)`; guard for None explicitly.
5. Currency-formatted price (`"$12.99"`, `"1,234.56"`) → float() fails; strip symbols/thousands separators before parsing.
6. Locale decimal comma (`"12,99"`) → misparsed or fails; normalize decimal separator per expected locale.
7. Non-integer qty string (`"3.5"`) → `int()` raises ValueError; decide whether to allow fractional qty (use float/Decimal) or reject.
8. `"nan"`/`"inf"`/`"-inf"` accepted silently by `float()` → poisons the running total with NaN/inf; explicitly reject non-finite values.
9. Scientific notation or leading `+` (`"1e5"`) parsed silently → validate strict numeric format if unexpected values must be rejected.
10. Negative price or qty → silently produces negative revenue; validate sign or explicitly allow (refunds) with a documented rule.
11. Extreme magnitude values → float overflow to `inf`; enforce sane bounds or switch to `Decimal`.
12. Binary floating-point rounding drift across many rows → money totals drift; use `Decimal` (or integer cents) instead of `float`.
13. One bad row raises and kills the whole aggregation with no context → catch per-row, log row index/content, continue or collect errors.
14. Non-dict/malformed row (e.g., short row from ragged CSV) → TypeError on subscript; type/shape-check each row.
15. Unicode/full-width digit strings (`"１２.５"`) → `float()` raises; normalize unicode before parsing if source data isn't guaranteed ASCII.
16. Whitespace-only or hidden non-breaking spaces in fields → parse failure; `.strip()` (and normalize NBSP) before conversion.
17. Very large row count with per-row overhead → no batching/streaming; consider generator-based summation for large files.
18. No return-type/precision contract documented → callers may assume float precision is exact for currency; document/enforce Decimal-based return.

---
Model/settings check: Sonnet 5, standard thinking — appropriate for this task; no change suggested.
