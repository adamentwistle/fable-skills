1. Price is binary float — use Decimal(r['price']) * int(r['qty']) for accurate money arithmetic.
2. No validation for negative price or qty — add checks: if float(r['price']) <= 0 or int(r['qty']) < 0, reject or log.
3. Whitespace in CSV fields causes parsing failure — call r['price'].strip() and r['qty'].strip() before conversion.
4. Qty as float string like "3.5" raises ValueError on int() — use int(float(r['qty'])) or validate format first.
5. Currency symbols like "$100" won't parse — preprocess to remove $ and commas, or validate numeric-only.
6. Missing 'price' or 'qty' key raises KeyError silently — use r.get('price') with defaults or check key existence first.
7. Non-numeric strings raise ValueError with no row context — wrap in try-except and re-raise with row identifier.
8. float("inf") and float("nan") are accepted and corrupt total — validate each price/qty with math.isfinite() after parsing.
9. No rounding policy specified — round(total, 2) or use Decimal with ROUND_HALF_UP for cents.
10. Accumulating floats drifts on large datasets — use Decimal for total, not float, to avoid precision loss.