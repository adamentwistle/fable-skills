1. Race condition: multiple threads read same count before either increments — lock entire operation
2. No time window: counter never resets, permanently blocking users after limit — add timestamps and reset per time period
3. Memory leak: old user entries never removed — implement cleanup/eviction of stale entries
4. Not thread-safe: concurrent dict access unsynchronized — use threading.Lock()
5. Not multi-process safe: each worker process has own dict copy — use Redis or shared backend