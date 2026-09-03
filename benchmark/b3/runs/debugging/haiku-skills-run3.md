1. Cache never invalidated once populated; check file modification time before returning cached value.
2. Reloading on every call doesn't fix it; just wastes caching benefit.
3. TTL-based expiry doesn't fix it; doesn't detect actual file changes, only elapsed time.
4. Manual reload parameter doesn't fix it; shifts detection burden to caller instead of automatic.