<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-edge-skills-3. Content below the line is the agent's final output, unmodified. -->

---

1. Empty `rows` → returns `0` silently; decide if that's valid or should signal "no data."
2. Missing `'price'` key → raises `KeyError`; catch and report the row index/field, don't let it propagate raw.
3. Missing `'qty'` key → same `KeyError` risk, same fix.
4. `price`/`qty` value is `None` → `float(None)`/`int(None)` raise `TypeError`; validate before casting.
5. Empty string `''` for price or qty → `ValueError`; treat as missing data, not a crash.
6. Non-numeric string (e.g. `"abc"`) → `ValueError`; wrap and name the offending row/field/value.
7. `qty` as a decimal string like `"3.0"` → `int("3.0")` raises `ValueError`; parse qty via `float`→check-integral or `Decimal`.
8. Thousands/locale-formatted strings (`"1,234.56"`, `"1.234,56"`) → `float()` mis-parses or raises; needs explicit locale-aware parsing.
9. Whitespace-padded values (`" 12 "`) parse fine but hide upstream CSV corruption; log/strip explicitly rather than relying on implicit behavior.
10. `"nan"`/`"inf"`/`"-inf"` strings → `float()` accepts them silently, poisoning the running total; reject explicitly.
11. Scientific notation (`"1e3"`) parses silently; decide if that's an intended price format.
12. Negative `price` or `qty` → parses fine but silently allows refunds/errors into the sum; require explicit sign policy.
13. Extremely large values → float precision loss / potential `inf` on overflow; cap or use `Decimal`.
14. Repeated float addition of money → cumulative rounding drift; use `Decimal` or integer cents instead of `float`.
15. No rounding policy on final total → result like `19.999999999998`; define rounding (e.g., 2 dp, `ROUND_HALF_UP`) at the end, not mid-sum.
16. Duplicate rows are summed without question → add a dedup/validation step if duplicates are a known data issue.
17. Unicode currency symbols or non-ASCII digits in the string (`"€12,50"`) → `float()` raises; strip/normalize or reject with a clear message.
18. Any raised exception currently surfaces as a bare `ValueError`/`KeyError` with no context → wrap each row's parse in try/except and re-raise with row index, field name, and raw value.

--

Model/effort check: this was a self-contained, well-scoped code-review task with clear deliverables — current model and reasoning settings were suitably matched, no change recommended.
