<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-bare-3. Content below the line is the agent's final output, unmodified. -->

---

1. Missing `'price'`/`'qty'` key → `KeyError`; fix with `r.get(key)` and validate presence first.
2. `None` value in either field → `TypeError` on cast; fix by checking for `None` before conversion.
3. Empty string `''` for price/qty → `ValueError`; fix by validating non-empty before parsing.
4. `qty` like `"3.0"` or `"3,5"` → `int()` raises `ValueError`; fix by parsing via `Decimal`/`float` and validating integrality, or using regex-validated int parse.
5. `price`/`qty` with currency symbols, commas, or units (`"$12.50"`, `"1,200"`) → `ValueError`; fix by stripping/normalizing or rejecting malformed formats explicitly.
6. `float("nan")` / `float("inf")` accepted silently → poisons the running total; fix by rejecting non-finite values with `math.isfinite`.
7. Scientific notation (`"1e3"`) silently parsed as valid → may not be intended input; fix with strict numeric-format validation (e.g. regex) instead of bare `float()`.
8. Locale decimal separators (`"12,50"`) → misparsed or `ValueError`; fix by normalizing locale format before casting.
9. Negative price or qty (refund vs. corrupt data) → silently subtracts from total; fix by defining and enforcing a sign policy.
10. Binary float summation of currency → cumulative rounding error; fix by using `Decimal` (or integer cents) instead of `float`.
11. Extremely large price/qty values → float overflow/precision loss; fix by bounding inputs or using `Decimal`.
12. One bad row raises and aborts the whole aggregation with no context; fix by catching per-row errors, logging the offending row, and continuing/collecting failures.
13. Non-dict row (e.g. `None`, malformed CSV line) → `TypeError` on `r['price']`; fix by validating row type/shape before indexing.
14. Duplicate rows (re-ingested CSV lines) double-count revenue; fix by deduping on a unique row/order key if applicable.
15. Leading/trailing or unicode whitespace / non-breaking spaces in cells → inconsistent parse failures; fix by normalizing/stripping whitespace before casting.
16. No final rounding → returns values like `19.999999999999996`; fix by rounding/quantizing to 2 decimals at the end.
17. `rows` as a one-shot iterator/generator → silent empty result if already consumed elsewhere; fix by materializing to a list or documenting single-use.
18. No overall input validation/logging → silent bad data skews revenue with no audit trail; fix by returning both total and a list of skipped/invalid rows.
