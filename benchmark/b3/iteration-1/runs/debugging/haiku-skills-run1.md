1. **Cache persists across calls without revalidation** — check file's modification time before serving cached value; reload if file is newer.

2. **Tempting but wrong: removing the cache entirely** — would fix staleness but unnecessarily abandons the performance optimization.

3. **Tempting but wrong: checking if `_cache` is falsy** — an empty dict is still stale data; emptiness doesn't indicate file changes.

4. **Tempting but wrong: checking only if `path` parameter changed** — config file can change on disk while the path stays the same.