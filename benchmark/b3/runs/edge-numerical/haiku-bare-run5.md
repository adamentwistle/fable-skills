1. Missing 'price' or 'qty' keys raise KeyError — use .get() with defaults or validate all keys present.
2. Non-numeric strings like "abc" raise ValueError on float/int — wrap in try/except or pre-validate.
3. None values raise TypeError on float/int — skip rows or validate non-None explicitly.
4. Decimal quantity like "5.5" fails int() — use int(float(r['qty'])) if fractional qty is possible.
5. Float arithmetic imprecision on money (0.1+0.2≠0.3) — switch to Decimal for currency.
6. Negative prices or quantities silently pass — add validation that both ≥ 0.
7. Whitespace in numbers like " 10.5 " prevents parsing — strip() values before conversion.
8. NaN or Infinity strings parse successfully but break arithmetic — validate math.isfinite() after parse.
9. Row not a dict (None, string, list) crashes unpacking — validate isinstance(r, dict).
10. Empty rows list is ambiguous (zero revenue vs. missing data) — handle explicitly or log.