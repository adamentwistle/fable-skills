1. Concurrent calls bypass limit in read-modify-write race — use threading.Lock
2. No time window resets count; users permanently blocked — add sliding-window reset
3. Unbounded dict grows indefinitely, memory leak — add entry expiration
4. Separate worker processes use separate dicts, limit multiplied by worker count — use Redis or external cache
5. Negative limits not validated, allow unlimited requests — validate limit > 0