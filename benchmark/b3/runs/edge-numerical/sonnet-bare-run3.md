1. Missing key (`r['price']` or `r['qty']` absent) → raises KeyError; use `.get()` with default or validate schema upfront.
2. Non-numeric price/qty (e.g. "N/A", "") → raises ValueError; wrap conversion in try/except and skip or log bad rows.
3. Empty string qty/price → ValueError on `int('')`/`float('')`; same try/except, treat as 0 or reject row.
4. Negative price or qty (refunds, data errors) → silently subtracts from total; decide policy explicitly (allow refunds vs. reject negatives).
5. Non-integer qty like "2.5" → `int()` raises ValueError; use `float(qty)` or `Decimal` if fractional quantities are valid.
6. Thousands separators or currency symbols ("$1,200.50") → `float()` raises ValueError; strip/normalize before parsing.
7. Whitespace padding (" 12.50 ") → usually fine for `float`/`int` but fails on symbols/commas; `.strip()` defensively anyway.
8. Locale decimal comma ("12,50") → `float()` misparses or raises; normalize to `.` before conversion or use `locale`-aware parser.
9. Float binary rounding error accumulating over many rows → use `Decimal` instead of `float` for money.
10. `NaN`/`inf` strings ("nan", "inf") parse successfully via `float()` → poisons total silently; validate `math.isfinite()` after parsing.
11. Overflow/absurd values (e.g. qty "99999999999999999999") → inflates total unbounded; add sanity bounds/max checks.
12. `None` values from CSV nulls → `float(None)`/`int(None)` raises TypeError; guard for `None` before conversion.
13. Extremely large row count with float accumulation → precision drift; use `Decimal` or integer cents to avoid.
14. Duplicate rows (dup invoice lines) not deduplicated → double-counts revenue; dedupe by row key if source can contain repeats upstream.
15. Silent partial failure (one bad row aborts entire aggregation) → no visibility into which row failed; catch per-row and report/collect errors rather than crashing whole batch.
16. No currency-unit consistency check (mixed currencies summed as if same) → nonsensical total; validate/segregate by currency column if present.