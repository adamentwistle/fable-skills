1. Root cause: the guard only asks whether `_cache` is `None`, never whether the file changed, so the first load is permanent for the life of the process; fix by storing the file's stat signature next to the data and reloading whenever it differs.
2. The signature must be `st_mtime_ns` plus `st_size` plus `st_ino`, not `st_mtime` alone; coarse mtime resolution and same-second same-size rewrites slip past mtime, and atomic-rename writers change the inode.
3. Stat before reading, not after, so a write landing between the two causes one harmless extra reload instead of a permanently stale entry.
4. `path` is ignored once anything is cached, so `get_config('other.json')` returns the first file's contents; key the cache by resolved absolute path.
5. Relative `'config.json'` resolves against the current working directory at first call, so which file gets cached depends on who called first; resolve it against the module or an explicit config directory.
6. A half-written file makes `json.load` raise mid-reload; on failure keep the previous cache and retry next call rather than crash or cache nothing.
7. Callers receive the shared dict and can mutate it for everyone, which looks like staleness from the outside; return a copy or a `types.MappingProxyType`.
8. With reload in play two threads can race the load; assign the whole entry as one tuple, and add a lock only if parsing is expensive.
9. Non-fix: changing `is None` to `if not _cache` still never reloads a non-empty config, and reloads on every call for an empty one.
10. Non-fix: a `reset_config()` or `cache_clear()` hook only helps when the writer is your own code and remembers to call it; editors, deploys, and config management never will.
11. Non-fix: `functools.lru_cache` keys on the argument, not the file, so it is stale forever in exactly the same way.
12. Non-fix: a time-to-live shrinks the stale window but does not close it, and reloads when nothing changed; at most use a short TTL to throttle the stat call.
13. Non-fix: deleting the cache reads and parses on every call, a performance regression that only moves the problem to callers; acceptable only if calls are rare.
14. Non-fix: a file watcher adds a thread and a dependency, and inotify events are unreliable on bind mounts and network filesystems; stat-on-read is simpler and always correct.
15. Non-fix: `importlib.reload` or a process restart is the reported symptom restated, not a fix.