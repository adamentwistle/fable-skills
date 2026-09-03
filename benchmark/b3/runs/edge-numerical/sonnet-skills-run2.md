1. Missing key `'price'`/`'qty'` → KeyError: use `.get()` with validation or catch and skip/report row.
2. Missing/None value in a present key → same KeyError/TypeError path: validate before cast.
3. Empty string `''` for price/qty → `float('')`/`int('')` raises ValueError: catch and treat as invalid row.
4. Non-numeric text (`"N/A"`, `"$5"`, `"5,000"`) → ValueError on cast: strip currency symbols/commas or reject with row context.
5. Whitespace-padded values (`" 5 "`) → usually fine for `float`/`int`, but confirm and `.strip()` defensively.
6. Negative price or qty (refunds vs bad data) → silently allowed and summed: decide whether negatives are valid and assert/flag accordingly.
7. Non-integer qty string (`"2.5"`) → `int()` raises ValueError even though it's a valid quantity: use `float` or `Decimal` for qty, or explicitly reject fractional units.
8. Float `price` uses binary float arithmetic → rounding drift (`0.1+0.2` style errors) accumulating over many rows: use `Decimal(str(price))` for money, not `float`.
9. Very large qty/price (overflow-adjacent, or just huge order) → float loses precision beyond 2^53: use `Decimal`/`int` instead of `float`.
10. `float('inf')`/`float('nan')` as literal CSV text → silently poisons the total (`nan` propagates, `inf` swamps it): reject non-finite values explicitly.
11. Scientific notation (`"1e10"`) parses fine as float but is probably bad input for a price: validate format if unexpected.
12. Empty `rows` list → returns `0` correctly, but confirm `0` (int) vs `Decimal('0.00')` type consistency with the rest of the pipeline.
13. Duplicate rows (same order counted twice) → silently double-counted: dedupe upstream or document that caller is responsible.
14. One bad row aborts the entire aggregation (no partial result, no indication which row) → wrap per-row in try/except, collect errors, report which row/field failed instead of a bare traceback.
15. Currency/unit mismatch across rows (some rows in cents, some in dollars, or mixed currencies) → summed as if uniform: validate/normalize units before summing if the CSV can mix them.
16. No rounding policy for the final total → downstream display may re-round inconsistently: round once at the boundary (e.g., `quantize` to 2 decimal places) and state the policy (e.g., ROUND_HALF_UP).