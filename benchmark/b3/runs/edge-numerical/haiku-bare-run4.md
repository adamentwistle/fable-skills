1. Missing 'price' or 'qty' keys raise KeyError → use dict.get() or validate keys present.
2. Non-numeric price string raises ValueError → validate format or wrap float() in try-except.
3. Non-numeric qty string raises ValueError → validate format or wrap int() in try-except.
4. Empty or None values raise ValueError → skip rows or validate non-empty before conversion.
5. Negative price/qty produces wrong totals → assert both price > 0 and qty > 0.
6. Float precision degrades with currency math → use Decimal instead of float.
7. float("nan") and float("inf") accepted as valid → validate result with math.isfinite().
8. Qty must be integer (decimals rejected) → clarify if quantities are always whole units.
9. No exception handling → function crashes on bad rows, wrap in try-except.