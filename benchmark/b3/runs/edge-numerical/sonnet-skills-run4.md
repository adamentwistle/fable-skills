1. Missing key `r['price']`/`r['qty']` → KeyError; catch/validate and skip or raise a named row error.
2. Non-numeric `price` (`"abc"`, `""`) → ValueError from `float()`; validate/catch per row.
3. Non-integer `qty` (`"3.5"`) → ValueError from `int()`; parse qty as `int(float(x))` only if fractional qty is meaningless, else reject.
4. `qty` as `"3.0"` string → `int()` throws on decimal strings; use `int(float(r['qty']))` or regex-validate.
5. Negative price or qty (refunds/data errors) → silently flips total; decide policy (allow refunds vs reject negatives) explicitly.
6. `price`/`qty` as `None` (null CSV cell) → TypeError in `float()/int()`; treat None as missing/invalid.
7. Whitespace-padded values (`" 12.50 "`) → may or may not parse; `.strip()` before parsing.
8. Currency symbols/commas in price (`"$1,200.00"`) → ValueError; strip formatting or reject with clear error.
9. Locale decimal comma (`"12,50"`) → silently wrong via `float()` or throws; require explicit locale/format contract.
10. `float` binary rounding error accumulating over many rows → money drifts from true sum; use `Decimal` (from `str`, not `float`) for all money math.
11. Very large qty/price (overflow-adjacent, scientific notation `"1e10"`) → accepted silently by `float()`, producing bogus totals; bound-check parsed values.
12. `qty` as huge value causing unreasonable multiplication → cap or flag outlier rows rather than trust blindly.
13. Empty `rows` list → returns `0` silently; confirm that's the intended "no data" result, not an error.
14. Duplicate rows (same order counted twice) → inflates total; dedupe upstream if CSV can contain repeats, or document as caller's responsibility.
15. `NaN`/`Infinity` strings (`"nan"`, `"inf"`) → `float()` accepts them, poisoning the sum; reject non-finite values explicitly.
16. Mixed units (price in cents vs dollars across rows) → silent misprice; enforce single unit contract at ingestion.
17. Non-dict row (malformed CSV parse gives a list or string) → TypeError on `r['price']`; validate row shape before indexing.
18. Any single bad row aborts the entire aggregation (no partial result, no indication which row) → wrap per-row parsing, collect errors with row index, decide fail-fast vs skip-and-report policy.
19. Return type is `int` when `total` starts at `0` and stays untouched (empty rows) but `float`/`Decimal` otherwise → inconsistent return type; initialize `total = Decimal('0')` for type stability.
20. No currency/precision on output → caller must decide rounding for display; round once at the boundary with a named policy (e.g. `ROUND_HALF_UP` to cents).