<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-skills-5. Content below the line is the agent's final output, unmodified. -->

---

1. Empty `rows` — returns `0` (int) silently; fine, but callers expecting Decimal/float should get a typed zero.
2. Missing `'price'` key — raises bare `KeyError`; catch and raise with row index + missing field name.
3. Missing `'qty'` key — same `KeyError` issue; identify row/field in the error.
4. `None` value for price/qty — raises `TypeError` on `float(None)`/`int(None)`; validate presence before casting.
5. Empty string `''` for price — `float('')` raises `ValueError`; check-and-report before parsing.
6. Empty string `''` for qty — `int('')` raises `ValueError`; same explicit check.
7. Fractional qty string like `'3.0'` — `int('3.0')` raises `ValueError`; parse via float then validate integrality, or define policy.
8. Non-numeric garbage (`'abc'`, `'N/A'`, `'-'`) — raises unhelpful `ValueError`; wrap in try/except naming row/field/value.
9. Whitespace-padded values (`' 3.00 '`) — works today but relies on implicit `strip()`; make explicit so future format tweaks don't break it.
10. Currency symbols/thousands separators (`'$1,200.50'`) — raises `ValueError`; sanitize or reject with a clear message rather than crashing opaquely.
11. Locale decimal commas (`'1.234,56'`) — misparses or raises `ValueError`; needs explicit locale handling or rejection.
12. Unicode/full-width digits (`'３.５'`) — raises `ValueError` in `float()`; normalize (NFKC) or reject with context.
13. `'nan'`/`'inf'`/`'-inf'` strings — `float()` accepts these silently, poisoning the total with NaN/Infinity; explicitly reject non-finite values.
14. Negative price or qty — silently included (refunds? bad data?); decide business rule and validate/flag.
15. Huge magnitude values — float precision loss on large numbers; use `Decimal` for money instead of `float`.
16. Float summation drift — repeated float addition accumulates rounding error (e.g. `0.1+0.2`); use `Decimal` or integer cents throughout.
17. No rounding policy on final total — result can be like `19.999999999999996`; define explicit rounding (e.g. `quantize` to cents).
18. Duplicate rows — summed without detection; add a duplicate/row-hash check if double-counting is a real risk.
19. Row not a dict (malformed record) — `r['price']` raises `TypeError`; validate row shape before indexing.
20. No error context anywhere — every failure surfaces as a bare `ValueError`/`KeyError`/`TypeError` with no row index or offending value; wrap the per-row parse in try/except and re-raise a descriptive exception naming row index, field, and raw value.

**Model suitability note:** This request (a bounded, well-scoped code-hardening checklist) is well matched to Sonnet without extended thinking — no suggested change.
