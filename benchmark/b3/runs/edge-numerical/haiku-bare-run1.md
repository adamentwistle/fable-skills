1. Missing keys raise `KeyError` — validate keys exist or use `.get()` with defaults
2. Non-numeric strings raise `ValueError` — validate/sanitize input before conversion
3. Empty strings raise `ValueError` — reject or handle explicitly
4. Float accumulation causes precision loss for currency — use `Decimal` instead
5. Negative prices/quantities unchecked — add assertions for non-negative values
6. Special floats (inf, nan) pass silently to result — filter these values
7. Currency symbols like "$" raise `ValueError` — preprocess to remove them
8. Leading/trailing whitespace may cause errors — call `.strip()` before conversion
9. Locale-specific decimal separators (commas) raise `ValueError` — normalize format
10. `int()` rejects fractional quantities like "5.5" — clarify whether fractional qty is allowed
11. Very large numbers may exceed float precision — document or validate limits
12. No validation of output — result could be inf/nan silently passed through