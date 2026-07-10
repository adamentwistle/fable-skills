<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). This is the exact prompt given to each edge-numerical with-skills agent (identical across all runs of this cell, Opus 4.8 and Sonnet 5). -->

---

Harden this revenue aggregator. `rows` is a list of dicts parsed from a CSV, where 'price' and 'qty' are strings. List every edge case, numerical hazard, and failure mode.

```python
def total_revenue(rows):
    total = 0
    for r in rows:
        total += float(r['price']) * int(r['qty'])
    return total
```

APPLY these skills:
- edge-case-sweep: empty rows list; missing 'price'/'qty' keys (KeyError) — distinct from empty/None values; non-numeric or empty strings; negative values; huge values; whitespace; duplicate rows; unicode.
- numerical-care: float for money drifts — use Decimal/cents; `int('3.0')` and `int('')` raise ValueError; rounding policy; what value makes each arithmetic line wrong (zero, negative, huge)?
- error-message-quality: a parse failure should name the offending row/field/value, not raw-crash with a bare ValueError.

Return a terse NUMBERED list of findings — each one line: the issue + a one-clause fix. No rewritten code, no preamble.
