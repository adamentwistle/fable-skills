1. Missing key ('price' or 'qty' absent) → KeyError: use r.get(...) and reject/report row.
2. Empty string value ('' for price/qty) → ValueError on cast: validate non-empty before cast.
3. Non-numeric junk ('abc', 'N/A') → ValueError: catch cast errors, skip/log offending row with its value.
4. Whitespace/formatting (' 12.50 ', '$12.50', '1,200') → ValueError or wrong parse: strip and strip currency/thousands separators before cast, or reject.
5. Negative price or qty (refunds vs bad data) → silently accepted: decide policy (allow negative for refunds, else reject) explicitly.
6. Non-integer qty ('2.5') → ValueError on int(): decide whether fractional qty is valid, use float/Decimal or reject.
7. int('2.0') fails despite being "numeric" → ValueError: normalize via float-then-check-integer or Decimal.
8. NaN/Infinity strings ('nan', 'inf') → float() accepts them silently, poisoning total: explicitly reject non-finite values (math.isfinite).
9. Float binary imprecision accumulating over many rows → wrong total to the cent: use Decimal (or integer minor units) for price/total, not float.
10. Extremely large qty (overflow-scale, e.g. 10**18) → unrealistic total dominates sum: cap/validate qty against a sane max.
11. Very large row count (millions) → memory/perf if rows isn't already a generator: ensure streaming iteration, not list-building elsewhere.
12. Duplicate rows (same order counted twice) → silently double-counts: dedupe by row/order ID if the source can duplicate.
13. None values (CSV null vs empty parsed as None upstream) → TypeError on float(None): guard for None explicitly.
14. Empty rows list → returns 0, which is correct but silent: fine as-is, just document zero-row behavior.
15. Locale-formatted numbers ('1.234,56' European decimal) → misparsed as 1234.56 vs 1.23456: normalize decimal format explicitly or reject ambiguous formats.
16. Mixed currencies with no currency column → total conflates units: require a currency column or explicit single-currency assumption documented.
17. Single bad row currently aborts the entire aggregation (no partial result, no indication which row) → poor error message: catch per-row, report row index/value in the exception, continue or fail loudly with context.
18. Rounding policy for total undefined → downstream display mismatches: round once at the end using a named policy (e.g., ROUND_HALF_UP to cents).