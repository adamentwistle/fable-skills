1. Race condition on concurrent requests for same user—both can read-check-count before either increments, allowing both through—use threading.Lock to protect read-check-write.

2. Each worker process has its own counts dict in multi-worker deployments; limits aren't shared globally—move counts to shared storage (Redis, database).

3. counts dict grows unbounded; old user entries never removed—implement periodic cleanup/eviction.

4. Counters never reset; users permanently blocked after hitting limit—implement time-windowed resets (e.g., sliding or fixed-window with timestamps).