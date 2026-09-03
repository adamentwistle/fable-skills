1. Missing key ('price'/'qty' absent) raises KeyError uncaught → wrap in try/except and skip or collect bad rows.
2. Non-numeric price/qty ("N/A", "") raises ValueError → validate/catch and reject the row explicitly.
3. None values (null CSV cell parsed as None) raise TypeError → treat as missing, same as #1.
4. Negative price or qty silently subtracts from total → decide policy (reject or allow refunds) and assert non-negative if disallowed.
5. Whitespace/currency symbols in price ("$12.50", " 12.50 ") raise ValueError → strip and sanitize before float().
6. Thousands separators ("1,200.50") raise ValueError → strip commas or use locale-aware parser.
7. qty as float string ("2.0") raises ValueError on int() → parse via float then validate integral, or use Decimal.
8. Empty rows list returns 0 silently, indistinguishable from "all rows failed" → return count of skipped rows alongside total.
9. float() accepts "inf"/"nan" → total becomes inf/nan silently → explicitly reject non-finite values.
10. Binary float arithmetic drifts (0.1+0.2 rounding) over many rows → use Decimal for money, not float.
11. No rounding policy → total has floating garbage digits ($12.999999999998) → quantize to cents with a named rounding mode at the end.
12. Very large qty (e.g. 10**18) can overflow float precision silently → cap/validate qty against a sane max.
13. Unit mismatch: price assumed dollars but CSV could have cents or mixed currencies → validate/document the expected unit.
14. Duplicate rows (same order twice) inflate total with no dedup check → decide if dedup is needed and note it as a deliberate non-goal if not.
15. `rows` itself None or not iterable → raises TypeError with no context → validate input type up front with a clear error.