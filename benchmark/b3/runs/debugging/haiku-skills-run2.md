1. Root cause: indefinite cache with single `_cache is None` check; reload only happens on first call, never when file changes.
2. Wrong fix—checking file existence: File still exists after modification; `os.path.exists()` detects presence, not changes.
3. Wrong fix—periodic reload on timer: Arbitrary intervals; doesn't detect actual changes, wastes I/O on unchanged files.
4. Wrong fix—caller-controlled reload parameter: Callers don't know when the file changed; burden is shifted, not solved.
5. Correct fix: Store file mtime when loading; reload cache whenever `os.path.getmtime(path)` differs from the cached mtime.