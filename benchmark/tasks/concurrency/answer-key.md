<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07): the answer-key section of the blind-grader prompt for the concurrency area, unmodified. -->

ANSWER KEY — 7 issue classes. Mark Y only if genuinely identified:
- B1 Check-then-act race (TOCTOU): read→compare→write not atomic, two threads both pass the check.
- B2 Lost update on the increment specifically (two threads read same count, both write count+1, one increment dropped) — must be called out as a distinct lost-update/dropped-increment, not just "the race".
- B3 Fix is a lock / atomic increment / atomic backend (INCR).
- B4 No time window / never resets → it's a lifetime cap, not a rate limit.
- B5 Unbounded memory growth (entry per user_id, never evicted).
- B6 Per-process/multi-worker: in-memory dict not shared across workers/processes, so effective limit is limit×workers.
- B7 Missing/None (or unhashable) user_id not validated.
