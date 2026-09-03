1. Race condition on read-check-write; concurrent threads read the same value and all increment — use a lock.

2. No time window; users blocked indefinitely after limit exceeded — add periodic reset by timestamp.

3. Unbounded memory; entries never expire, dict grows with unique users — add cleanup by last-request timestamp.

4. No inter-process sharing; each worker process has its own dict — use shared store (Redis/database).