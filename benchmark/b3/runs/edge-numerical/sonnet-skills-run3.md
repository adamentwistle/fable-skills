1. Missing/None `price` or `qty` key → KeyError; fix: `.get()` with default or explicit validation raising a clear error.
2. Non-numeric `price`/`qty` (e.g. "N/A", "") → ValueError; fix: try/except with row-identifying error message.
3. `qty` as float string ("2.0") → `int()` raises ValueError; fix: parse via `int(float(x))` or `Decimal` with policy.
4. Negative `price` or `qty` (returns/refunds vs bad data) → silently accepted; fix: validate sign per business rule, reject or flag.
5. `price` as currency string ("$12.34", "1,234.56") → ValueError; fix: strip currency symbols/thousands separators before parsing.
6. `price`/`qty` with surrounding whitespace → usually fine via float()/int(), but confirm; fix: `.strip()` defensively.
7. Float binary rounding on money (`float(r['price'])`) → cumulative cent drift; fix: use `Decimal(r['price'])` for price arithmetic.
8. `qty` empty string `""` → ValueError on `int()`; fix: reject with row context or default to 0 per policy.
9. Extremely large `qty`/`price` (overflow-adjacent, e.g. 1e308 * huge qty) → inf or huge total masking bad data; fix: sanity-cap or flag outlier rows.
10. NaN/Inf strings ("nan", "inf") parse successfully via float() → poisons total silently; fix: explicitly reject non-finite values.
11. `rows` is empty list → returns 0, likely fine but ambiguous with "no data ingested"; fix: document/return distinguishable signal if needed.
12. `rows` is None or not iterable → TypeError; fix: validate input type upfront.
13. One bad row aborts the entire aggregation with no indication which row → fix: catch per-row, collect/report failing row indices, don't let one bad row crash the whole batch silently (or loudly, deliberately).
14. Unit mismatch (price in cents vs dollars across sources) → silent misprice; fix: document/enforce a single unit convention at ingestion.
15. No rounding policy applied to final total → downstream display inconsistency; fix: round once at output boundary with a named policy (e.g. ROUND_HALF_UP).