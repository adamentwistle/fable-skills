---
name: perf-sanity
description: Catch the algorithmic and I/O performance classics before shipping — O(n²) on unbounded input, N+1 queries, sync calls in hot/async paths, unbounded memory. Use when writing loops over data of unknown size, database access in loops, or anything on a request path.
---

# perf-sanity

Not optimization — just refusing to ship the five classics that account for most real slowdowns:

1. **Nested iteration over the same collection** (`for x in items: if y in items`) is O(n²); fine at 100 items, dead at 100k. If the input size is unbounded (user data, DB rows, log lines), use a set/map lookup. Know which of your inputs are unbounded.
2. **Query-in-a-loop is the N+1.** A DB/API call inside `for row in rows` turns one round-trip into a thousand. Batch it: `WHERE id IN (...)`, a join, or the API's bulk endpoint. Same for file opens and subprocess spawns in loops.
3. **Loading the whole thing to use a piece:** reading a full file for its first line, fetching all rows to count them, deserializing a payload to check one field. Stream, LIMIT, or push the filter down to the source.
4. **Sync blocking in async/hot paths:** a synchronous HTTP call or `sleep` inside an async handler stalls the event loop for everyone. Use the async client or move it off-path.
5. **Unbounded growth:** caches without eviction, lists appended per-request, listeners registered but never removed. Anything that grows with traffic needs a bound.

Calibration: don't micro-optimize (that's scope creep — see scope-discipline); a readable O(n) beats a clever O(n log n) hack. The bar is "no complexity-class surprises on realistic input sizes." When unsure what's realistic, check the actual data: `SELECT COUNT(*)`, `wc -l`.
