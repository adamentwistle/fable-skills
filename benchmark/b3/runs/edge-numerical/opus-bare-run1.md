1. `rows` may be `None` or a non-iterable — guard with an early return on falsy input.
2. Missing `'price'` or `'qty'` key raises `KeyError` — use `r.get(...)` with a default or skip-and-count bad rows.
3. `None` value from a null CSV field raises `TypeError` — treat `None` as empty and handle as a bad row.
4. Empty string or whitespace-only field raises `ValueError` — strip and skip blanks explicitly.
5. Currency symbols, thousands separators, or trailing spaces (`"$1,299.00 "`) raise `ValueError` — normalize by stripping `$`, `,`, and whitespace before parsing.
6. `int("3.0")` raises `ValueError` even though the value is a valid integer — parse quantity via `int(Decimal(s))` or `float` then check integrality.
7. `float("nan")` and `float("inf")` parse silently and poison the total — reject non-finite values with `math.isfinite`.
8. Binary floating point loses cents on accumulation — use `decimal.Decimal` for money and quantize once at the end.
9. Adding `float` to the `int` seed `0` returns a float even for empty input, so the return type is inconsistent — seed with `Decimal("0")` (or `0.0`) so the type is fixed.
10. Negative prices or quantities pass silently — validate against a business rule and reject or flag them.
11. Extremely large quantities (Python ints are unbounded) overflow to `inf` when multiplied by a float — cap quantity or stay in `Decimal`.
12. Underscore literals like `"1_000"` are accepted by `int()`/`float()` and silently misparse CSV data — reject strings that aren't a plain numeric pattern.
13. Unicode digits (`"٣"`) parse under `int()` and give unexpected values — restrict to ASCII digits with a regex.
14. Any single bad row aborts the whole run and loses all work — wrap per-row parsing in `try/except` and accumulate errors.
15. Failures are silent to the caller once caught — return or log a count of skipped rows alongside the total.
16. Non-dict entries in `rows` (a stray list or string) raise `TypeError`/`KeyError` — check `isinstance(r, dict)` per row.
17. Locale-specific decimals (`"1.299,50"`) parse to the wrong number rather than erroring — decide and document one input format, then enforce it.
18. Duplicate or already-aggregated rows double-count — deduplicate on a key upstream if the CSV isn't guaranteed unique.
19. `rows` as a generator is consumed once, so retry or reporting passes see nothing — materialize with `list(rows)` if reused.
20. Rounding is deferred to the caller, so downstream code may re-round differently — quantize to 2 decimal places on return with an explicit rounding mode.