<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: edge-skills-4. Content below the line is the agent's final output, unmodified. -->

---

1. Empty `rows` returns 0 correctly, but silently — decide whether an empty input should be 0 or an error, and signal accordingly.
2. Missing `'price'`/`'qty'` key raises bare `KeyError` — use `r.get(key)` and raise a labeled error naming the row index and field.
3. `None` values (missing vs. present-but-null) crash differently from missing keys — check for `None` explicitly before conversion and report which case occurred.
4. Empty string `''` for price/qty raises bare `ValueError` — validate emptiness first and emit a message naming the row/field.
5. `int('3.0')` and `int('3.5')` raise `ValueError` on legitimate-looking decimals — parse qty via `Decimal`/`float` then enforce integrality with a clear message.
6. Non-numeric strings (e.g. `'abc'`, `'$5'`, `'1,000'`) raise bare `ValueError` — wrap each conversion in try/except that reports row index, field name, and offending value.
7. Whitespace/padding (`' 5 '`, `'\t3'`) — `float`/`int` tolerate some but not all; `.strip()` inputs before parsing.
8. Unicode digits / full-width numerals / non-breaking spaces parse inconsistently across `float`/`int` — normalize or reject non-ASCII numeric input explicitly.
9. `float` for money accumulates drift (0.1+0.2 problem) — use `Decimal` for price and cents-based integer arithmetic for the running total.
10. No rounding policy — define quantization (e.g. `Decimal.quantize(Decimal('0.01'), ROUND_HALF_UP)`) at the point revenue is finalized.
11. Negative price or qty silently reduces revenue (refund vs. bad data ambiguity) — decide policy and reject/flag negatives unless intentionally allowed.
12. Zero qty or zero price contributes 0 legitimately but may mask data errors — allowed, but consider warning on all-zero or unexpected zeros.
13. Huge values (`'1e308'`, many-digit strings) overflow `float` to `inf` or lose precision — parse with `Decimal` which has no silent overflow, and bound-check magnitudes.
14. `'inf'`/`'nan'`/`'Infinity'` strings parse via `float()` and poison the total — explicitly reject non-finite parsed values.
15. `rows` itself being `None` or a non-iterable raises an unhelpful `TypeError` — validate the argument type up front.
16. A row that is not a dict (e.g. a list/str) raises a confusing error on `r['price']` — assert/verify each row is a mapping and report its index.
17. Duplicate rows are summed as-is — confirm that is intended (likely yes for line items), but note it if dedup was expected.
18. All failures currently abort the whole batch with no context — accumulate per-row errors (or fail fast) with messages of the form `row {i}: field {name}={value!r}: {reason}`.
19. `total` starts as `int` and mixes with `float`/`Decimal` — initialize as `Decimal('0')` to keep the type consistent.
20. Currency/locale not considered — mixed-currency rows summed into one total is a silent correctness bug; enforce single currency or group by it.

---
Model suitability: this is a static code-analysis / enumeration task with no repo exploration needed. Opus 4.8 (1M) is heavier than required — Sonnet without extended thinking would have handled it well at lower cost and latency.
