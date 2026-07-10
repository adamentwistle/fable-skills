<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-bare-4. Content below the line is the agent's final output, unmodified. -->

---

1. Missing `'price'`/`'qty'` key raises `KeyError` — use `.get()` with validation, not direct indexing.
2. `None` value (null CSV cell) raises `TypeError` on `float()/int()` — check for `None` before casting.
3. Empty string `""` raises `ValueError` — treat blank cells as missing/invalid, not zero.
4. Non-numeric junk (`"N/A"`, `"abc"`) raises `ValueError` and kills the whole batch — wrap per-row parse in try/except and skip/report the bad row.
5. Thousands separators or currency symbols (`"$1,200.00"`) raise `ValueError` — strip non-numeric formatting before casting.
6. `int(qty)` fails on decimal-looking quantities (`"3.0"`) — parse via `int(float(qty))` or reject non-integer qty explicitly.
7. Locale-style decimals (`"12,50"`) raise `ValueError` — normalize decimal separator before parsing.
8. `float("nan")`/`float("inf")` parse successfully and silently poison the total — explicitly reject NaN/Inf after parsing.
9. Scientific notation (`"1e6"`) parses as a huge legit-looking float — validate expected numeric format if unintended.
10. Negative `price` or `qty` silently changes the total (refund vs. data error ambiguous) — decide and enforce sign policy explicitly.
11. Float accumulation causes rounding drift over many rows — use `Decimal` for money, never `float`.
12. Unbounded/huge `qty` string enables a DoS via giant int/float multiply — bound-check magnitude before multiplying.
13. Row is not a dict (e.g. malformed CSV parse yields a list) raises `KeyError`/`TypeError` — validate row shape before access.
14. `rows` itself is `None` or non-iterable raises `TypeError` at the `for` — validate input type up front.
15. Duplicate rows (dup CSV lines) double-count revenue — dedupe upstream or document as accepted behavior.
16. Whitespace/control chars around values (`" 12.5\t"`) can break casting depending on content — strip before parsing.
17. One bad row aborts the entire aggregation with no context on which row failed — catch per-row, log row index/content, continue.
18. Empty `rows` list silently returns `0`, masking an upstream pipeline failure — add explicit "no rows processed" signal/warning.
