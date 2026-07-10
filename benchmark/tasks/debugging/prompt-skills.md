<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). This is the exact prompt given to each debugging with-skills agent (identical across all runs of this cell, Opus 4.8 and Sonnet 5). -->

---

Bug report: `get_config()` returns stale values after the config file on disk changes; only a process restart picks up the new values. Diagnose the ROOT CAUSE and give the correct fix. Be explicit about which tempting fixes would NOT properly address it.

```python
import json
_cache = None
def get_config(path='config.json'):
    global _cache
    if _cache is None:
        with open(path) as f:
            _cache = json.load(f)
    return _cache
```

APPLY these skills:
- root-cause-debugging: Don't pattern-match the symptom to a familiar fix. Find where the bad STATE is created, not where it's noticed. State the cause as a falsifiable sentence. Distinguish a real fix from a symptom-patch (a TTL / re-read-always / clear-cache that hides rather than cures). Say how you'd reproduce the failure and re-verify the fix.
- workmanship: Ground each claim in the code as written; hunt edge cases (missing/invalid file, first-vs-repeat call, concurrent access, a caller mutating the returned object); separate verified from assumed.

Return a terse NUMBERED list of findings — each one line: the issue + a one-clause fix. No rewritten code, no preamble.
