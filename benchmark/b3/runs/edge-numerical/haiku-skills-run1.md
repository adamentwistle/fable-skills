1. Missing 'price'/'qty' keys crash with KeyError — use dict.get() with defaults or validate upfront.
2. None values crash with TypeError — add None checks before float()/int().
3. Non-numeric strings crash with ValueError — validate format or wrap in try/except.
4. Rows parameter not validated for iterability — TypeError if not a sequence; add type check.
5. Using float for revenue is fundamentally wrong — use Decimal or track as integer cents.
6. No rounding policy defined — accumulation drifts; round each item to cents before summing.
7. Commas and currency symbols in strings cause ValueError — preprocess/strip before conversion.
8. Qty as decimal string "3.5" fails int() — decide if decimals allowed, convert to float first if so.
9. Accumulating many floats loses precision — use Decimal or math.fsum for large datasets.
10. Negative price or qty silently accepted — add range checks (>= 0) if discounts/returns not intended.