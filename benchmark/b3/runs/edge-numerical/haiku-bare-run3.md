1. Missing 'price' or 'qty' keys raise KeyError: validate presence or use .get() with defaults.
2. Empty strings raise ValueError on conversion: validate non-empty before parsing.
3. Non-numeric strings raise ValueError: validate numeric format.
4. Negative prices/quantities allowed (business logic error): validate >= 0.
5. Float precision loss in currency math: use Decimal type.
6. None values raise TypeError: validate not None.
7. Scientific notation silently parsed (1e5): validate or document expected format.
8. Rounding errors accumulate from repeated float ops: sum products first or use Decimal.
9. Embedded whitespace breaks parsing (e.g., "1 .5"): strip before conversion.
10. Non-dict rows cause KeyError: validate each row is a dictionary.