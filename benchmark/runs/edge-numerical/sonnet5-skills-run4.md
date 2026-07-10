<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-skills-4. Content below the line is the agent's final output, unmodified. -->

---

**Model-suitability check:** Sonnet 5, standard effort, is appropriate for this enumeration/hardening task — no extended thinking needed. No change suggested.

1. Missing `'price'` key raises `KeyError` — use `.get()`/explicit check and raise a named error identifying the row index and missing field.
2. Missing `'qty'` key raises `KeyError` — same fix, name row + field in the error.
3. `None` value for price (`float(None)`) raises `TypeError`, not `ValueError` — validate type before cast and normalize error type.
4. `None` value for qty (`int(None)`) raises `TypeError` — same, validate before cast.
5. Empty string price (`float('')`) raises `ValueError` — pre-check for blank/whitespace-only strings, raise descriptive error with row+value.
6. Empty string qty (`int('')`) raises `ValueError` — same pre-check.
7. Non-numeric price (e.g. `"abc"`) raises bare `ValueError` with no row context — wrap in try/except and re-raise with row index, field name, and offending value.
8. Non-numeric qty raises bare `ValueError` — same wrapping.
9. Decimal-looking qty (`int('3.0')`) raises `ValueError` — decide policy (reject or `int(float(qty))`) and document it.
10. Whitespace-only strings (`"   "`) pass `.strip()` checks but still raise `ValueError` on cast — treat as blank/invalid explicitly.
11. Thousands separators or currency symbols (`"$1,200.50"`) raise `ValueError` — strip/reject with a clear "unsupported format" message rather than crashing generically.
12. `"nan"`/`"inf"`/`"-inf"` strings are silently accepted by `float()`, corrupting the total without error — explicitly reject non-finite values.
13. Scientific notation (`"1e400"`) silently overflows to `inf` — validate magnitude bounds instead of trusting the float parse.
14. Negative price or qty is accepted silently (refunds vs. bad data ambiguous) — add explicit sign policy/validation.
15. Huge price/qty values accumulate float rounding error across many rows — use `Decimal` or integer cents instead of `float`.
16. Float multiplication (`price * qty`) drifts from exact currency math — switch to `Decimal(str(price))` or cents-as-int.
17. No rounding policy on final total — results like `12.000000000000002`; define and apply an explicit rounding/quantize step.
18. Duplicate rows are silently double-counted with no dedup/flagging — add optional duplicate detection or document that dedup is caller's responsibility.
19. Unicode/locale-formatted numerics (full-width digits, non-`.` decimal separators) fail cast silently as `ValueError` with no locale context — normalize/validate encoding before parsing, name the row.
20. Non-dict row entries (e.g. `None`, list) raise `TypeError` on `r['price']` — validate row shape before access.
21. Empty `rows` list returns `0` silently with no distinction from "all rows failed" — consider returning a result object with count-processed vs. count-total.
22. All failure paths raise bare stdlib exceptions with no row index/field/value — wrap every parse in try/except and raise a custom exception carrying row index, field name, and raw value.
