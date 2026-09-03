1. Missing 'price'/'qty' keys → validate schema upfront or use .get() with defaults
2. Non-numeric strings (letters, symbols, $) → catch ValueError or regex-validate before conversion
3. NaN/Infinity from float() → check math.isfinite() after float() call
4. Negative price or qty (data corruption or returns) → validate both ≥ 0
5. Currency formatting ($5.50, 1,000) → strip symbols and commas before conversion
6. Fractional qty strings ("2.5") → int() fails; decide if qty must be whole or accept float
7. Floating-point accumulation loses precision → use Decimal instead of float for money
8. Empty strings → ValueError in float/int; validate length and content before conversion
9. Type not string (int/float passed directly) → check isinstance(val, str) before converting
10. Scientific notation ("1e10") → float() accepts it; reject if not expected CSV format
11. Non-dict rows → TypeError accessing keys; validate row type before key access
12. No upper-bound validation → accumulation can grow unbounded; add magnitude check if needed