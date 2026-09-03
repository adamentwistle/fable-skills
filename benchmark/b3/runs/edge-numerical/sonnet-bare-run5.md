1. Missing/empty key or field — `KeyError` on malformed row → validate row has 'price'/'qty' before use.
2. Non-numeric string ("abc", "") — `ValueError` on float()/int() → wrap in try/except and skip or log bad row.
3. `int(r['qty'])` fails on decimal-looking strings like "1.0" or "3.5" → parse qty as float or Decimal, or explicitly reject fractional quantities.
4. Negative price or qty — silently allowed, corrupts total → validate non-negative (or flag refunds explicitly if intended).
5. NaN/Infinity strings ("nan", "inf") accepted by float() — poisons the sum → reject non-finite values explicitly.
6. Float accumulation of money causes rounding drift → use Decimal (or integer cents) instead of float.
7. Thousands separators / currency symbols ("$1,000") break float() → strip/normalize or reject before parsing.
8. Leading/trailing whitespace in fields — usually fine but locale variants (comma decimal) aren't → normalize/validate format explicitly.
9. Extremely large qty or price — no overflow in Python floats but can produce nonsensical totals silently → sanity-cap or flag outliers.
10. `rows` itself None or not iterable → guard with explicit type check.
11. One bad row aborts the entire aggregation with no partial result or diagnostics → decide on skip-and-log vs fail-fast policy explicitly, and report which rows failed.