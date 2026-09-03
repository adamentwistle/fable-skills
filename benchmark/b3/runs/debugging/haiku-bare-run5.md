1. Cache never invalidates when file changes — always reload on each call or add file-change detection.
2. Tempting: TTL-based expiry — stale values persist during cached interval.
3. Tempting: Reload() method — requires caller discipline, easily forgotten.
4. Tempting: Reset cache if path argument differs — default path stays permanently cached.
5. Correct: Remove cache, always reload file.
6. Alternative: Track file mtime, invalidate cache only when mtime actually changes.