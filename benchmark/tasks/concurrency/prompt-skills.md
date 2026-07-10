<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). This is the exact prompt given to each concurrency with-skills agent (identical across all runs of this cell, Opus 4.8 and Sonnet 5). -->

---

Review this in-process rate limiter for a multi-threaded, multi-worker web service. List every correctness and robustness problem.

```python
counts = {}
def allow_request(user_id, limit=100):
    count = counts.get(user_id, 0)
    if count < limit:
        counts[user_id] = count + 1
        return True
    return False
```

APPLY these skills:
- concurrency-reasoning: Ask — can two runs overlap? Is there a check-then-act gap (read count → compare → write is not atomic, so two threads both pass the check)? Shared mutable state without a lock? Lost updates on the increment? Does it hold across multiple processes/workers, or is per-process state a correctness bug for a global limit?
- edge-case-sweep: state that never resets (no time window — is this a rate limit or a lifetime cap?), unbounded memory growth, missing/None user_id, limit boundary (exactly at limit).

Return a terse NUMBERED list of findings — each one line: the issue + a one-clause fix. No rewritten code, no preamble.
