1. Missing 'price'/'qty' keys → KeyError—validate keys or use r.get().
2. None values in dicts → TypeError—check explicitly before type conversion.
3. Empty strings "" → ValueError—reject or skip rows.
4. Non-numeric strings ("abc") → ValueError—validate or wrap in try-except.
5. Whitespace in strings ("  5.99") → parsed incorrectly—.strip() before parsing.
6. Currency symbols ("$5.99"), commas ("1,000.50") → ValueError—clean or validate format.
7. Fractional qty strings ("2.5") → int() fails—decide if qty must be integer; validate.
8. Scientific notation ("1e5") → int() fails—clarify expected formats; validate.
9. Negative prices or quantities → silently accepted—validate both are ≥0.
10. Float type for money → precision loss, == unreliable—use Decimal or integer cents.
11. Accumulating float products → rounding errors compound—use Decimal throughout.
12. No rounding policy → result has arbitrary precision—specify ROUND_HALF_UP, apply once at end.
13. Large values >10^15 → float precision loss—use Decimal.
14. Result is float → unsuitable for storage/comparison—convert to Decimal or integer cents.