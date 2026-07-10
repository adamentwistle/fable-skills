<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-bare-2. Content below the line is the agent's final output, unmodified. -->

---

1. Missing keys ('price'/'qty' absent) → KeyError; use `r.get(...)` with explicit validation/error.
2. Empty string values ('') → ValueError on float/int; reject or default with logged skip.
3. None values (null CSV cells) → TypeError; treat as missing/invalid.
4. Non-numeric garbage ("N/A", "abc") → ValueError; wrap in try/except and isolate per-row failures instead of aborting the whole batch.
5. "nan"/"NaN" strings parse silently via float() → total becomes NaN and poisons all downstream sums; explicitly reject non-finite values.
6. "inf"/"-inf" strings parse silently → total overflows to infinity; reject non-finite values.
7. Currency symbols/thousands separators ("$1,200.00") → ValueError; strip/sanitize before parsing.
8. Locale-formatted numbers ("12,50" as decimal comma) → misparsed or ValueError; normalize locale first.
9. qty given as decimal string ("3.0", "2.5") → int() raises ValueError; decide and enforce int-vs-Decimal quantity semantics.
10. int() accepts underscores ("1_000") as valid Python numeric syntax → unexpected leniency on untrusted input; pre-validate with a strict numeric regex.
11. Negative price or qty → silently produces negative/absurd revenue; validate sign unless refunds are explicitly allowed.
12. Float binary rounding (0.1+0.2-style drift) accumulating across many rows → use Decimal (or integer cents) for money math.
13. Very large price/qty values → precision loss or overflow to inf; bound-check magnitudes.
14. rows is None or not iterable → TypeError on the for-loop; validate input type up front.
15. Individual row r is not a dict (e.g., a list/None from a malformed CSV line) → TypeError; validate row shape before indexing.
16. Whitespace/unicode/non-breaking-space padding in numeric strings → ValueError or silent misparse; strip and normalize whitespace before conversion.
17. Empty rows list returns 0 with no distinction from "aggregation failed" → return/raise a distinguishable sentinel or count of processed rows.
18. Mixed currencies across rows summed as if uniform → silent semantic error; check/require a single currency (or convert) before summing.
19. Duplicate rows (e.g., re-ingested CSV lines) double-counted → dedupe or key on a row identifier before summing.
20. No audit trail on skipped/failed rows → log or return rejected-row indices alongside the total for reconciliation.
