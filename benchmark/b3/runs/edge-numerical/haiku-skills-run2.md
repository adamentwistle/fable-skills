1. Missing 'price'/'qty' keys cause KeyError: validate keys exist before accessing.
2. None values cause TypeError: check `is not None` before float()/int().
3. Non-numeric strings raise ValueError unhandled: wrap parse in try-except ValueError.
4. Whitespace in strings fails int('  5  '): call .strip() before parsing.
5. Negative prices/quantities silently pass: validate ≥ 0 after parsing, raise if violated.
6. Float cannot exactly represent money (0.1 + 0.2 ≠ 0.3, precision loss): use Decimal for all calculations.
7. No rounding policy, result has arbitrary decimals: specify rounding mode (half-up) and round to cents.
8. Currency units ambiguous (dollars vs cents, inconsistent): document or validate expected units.
9. One bad row crashes entire calculation: add try-except per row to log/skip bad data.
10. Empty rows returns 0 silently: document if intentional or add explicit check to surface no-data case.