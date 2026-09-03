1. Race condition on read-modify-write without synchronization; wrap in a lock.
2. No time window (counts never reset); implement periodic reset per time interval.
3. Unbounded memory growth (old user entries never evicted); implement cleanup or TTL-based removal.
4. Not distributed across workers (each process has separate dict); use centralized store (Redis).