---
name: edge-case-sweep
description: Enumerate edge cases against a concrete checklist before declaring code complete. Use when implementing or reviewing any function, handler, parser, or data transformation — after the happy path works, before reporting done.
---

# edge-case-sweep

The happy path is the easy 80%. Sweep this list against every new or changed code path and either handle, explicitly reject, or consciously note each relevant case:

**Inputs**
- empty: `""`, `[]`, `{}`, zero rows, zero-byte file
- absent: null / undefined / missing key / missing flag — distinct from empty
- boundaries: 0, -1, exactly-at-limit, limit+1, first and last element
- huge: 10^6 items, multi-GB file, pathologically long string
- weird text: unicode, emoji, RTL, newlines-in-fields, quotes, leading/trailing whitespace, case variants
- duplicates and unsorted order where uniqueness/order is assumed

**State & time**
- called twice (idempotency), called concurrently, retried after partial success
- stale state: file changed since read, record deleted between fetch and update
- timezone, DST, end-of-month/year, clock skew

**Environment**
- dependency down / slow / returning errors: what does the caller see?
- permissions denied, disk full, network cut mid-operation

For each case that applies: decide handle vs reject-loudly. The unacceptable outcome is silent wrong behavior. If a case is deliberately unhandled, say so in the completion report — a stated limitation is fine, a hidden one is a bug report waiting.
