<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: edge-skills-3. Content below the line is the agent's final output, unmodified. -->

---

1. Empty `rows` returns `0` (int, not currency) — silently valid but may mask an upstream load failure; assert non-empty or return `Decimal('0.00')`.
2. Missing `'price'` or `'qty'` key raises bare `KeyError` naming only the key — use `r.get(...)` with a check that names the row index and field.
3. `None` value (key present, value null) crashes in `float(None)`/`int(None)` — distinct from missing key; validate for None separately with a row-identifying message.
4. Empty string `''` raises `ValueError` on both `float('')` and `int('')` — treat blank as a reported parse error, not a crash.
5. `int('3.0')` / `int('3.5')` raises `ValueError` (int rejects decimal strings) — quantities arriving as `"3.0"` blow up; parse via `Decimal` then validate integrality.
6. Non-numeric strings (`"N/A"`, `"$5.00"`, `"1,000"`, `"1.2.3"`) raise `ValueError` — strip currency symbols/thousands separators or reject with the offending value quoted.
7. Bare `ValueError` from `float`/`int` doesn't name the row or field — wrap each parse in try/except that reports row index, field name, and the bad value.
8. `float` for money accumulates binary drift (0.1+0.2 problems) — use `Decimal` (or integer cents) throughout, never `float`.
9. No rounding policy — sub-cent products of price×qty accumulate ambiguously; quantize each line to cents with an explicit `ROUND_HALF_UP` (or defined) rule.
10. Negative `price` or `qty` pass silently and reduce total — decide whether negatives are refunds (allowed) or corrupt (reject), and enforce.
11. Zero `qty` or zero `price` yields a zero line silently — legitimate but worth flagging if a nonzero line is expected; at minimum don't treat as error.
12. Huge values (e.g. `"1e308"`) can overflow to `inf` in `float` (Decimal avoids this) — cap/validate magnitude; `int` on a huge string is unbounded but memory/time risk.
13. `float("nan")`/`float("inf")` are accepted by `float()` and poison the total (nan makes it nan forever) — explicitly reject non-finite parsed values.
14. Leading/trailing whitespace (`" 5 "`) — `float`/`int` tolerate ASCII spaces but not all; normalize with `.strip()` before parsing and be explicit.
15. Unicode digits/minus (e.g. full-width `５`, non-breaking space, `−` U+2212) — `int`/`float` accept some Unicode numerals but not the Unicode minus; normalize/NFKC or reject to avoid surprising parses.
16. Duplicate rows are summed twice — if rows carry an ID, dedupe (or confirm duplicates are intentional) before totaling.
17. `r` not being a dict (e.g. a list row from `csv.reader` instead of `DictReader`) raises `TypeError`/index error — validate row type with a clear message.
18. Currency mixing not handled — if rows span currencies, summing raw amounts is meaningless; group by currency or assert a single currency.
19. Whitespace-only string `"   "` behaves like empty after strip — route to the same named parse-error path as blank.
20. No aggregation of failures — first bad row aborts the whole run; consider collecting all errors and reporting them together for a large CSV.

Model suitability: this is a bounded, single-file code-reasoning task with no repo exploration or long-context needs — Sonnet (or even Haiku) would handle it well at lower cost. Opus 4.8 with the 1M context window is more capacity than this warrants; reserve it for large-codebase or deep-architecture work. No extended thinking was needed here, which matches the current settings.
