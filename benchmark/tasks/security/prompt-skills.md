<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). This is the exact prompt given to each security (Benchmark 1) treatment agent (identical across all runs of this cell, Opus 4.8 and Sonnet 5). -->

---

You are reviewing this Python module before it ships to production. It is part of an e-commerce orders service; `get_user_orders` is called from an HTTP handler where `user_id` and `status` come from the request.

Produce a thorough code review: list EVERY issue you find (correctness bug, security, robustness, data-integrity, whatever), each with a severity (critical/high/medium/low) and the concrete fix. After the list, provide the corrected code.

```python
import sqlite3

def get_user_orders(db_path, user_id, status):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT id, amount, status FROM orders WHERE user_id = '%s' AND status = '%s'" % (user_id, status)
    cur.execute(query)
    return cur.fetchall()

def average_order_value(orders):
    total = 0.0
    for o in orders:
        total += o[1]
    return total / len(orders)

def apply_discount(amount, pct):
    return amount - amount * pct / 100

def format_receipt(order):
    return "Order #" + order[0] + ": $" + str(order[1])
```

You have access to the following engineering discipline skills. APPLY them systematically to this review — walk their checklists against the code.

===== SKILL: security-reflexes =====
Any value from a user/client/external system: parameterize never concatenate (SQL via placeholders; shell via arg arrays; paths via join+canonicalize+prefix check). Validate at the boundary by allowlist (enums/slugs through a server-side whitelist; reject unexpected keys). HTML: escape by default (XSS). URLs the server fetches: allowlist scheme+host (SSRF). AuthN/AuthZ: every mutating endpoint checks WHO is calling and MAY they touch THIS object (ownership check on the specific row, not just "logged in"); never trust client-supplied identity/scope fields (user IDs, account IDs, prices) — derive them server-side. Secrets: from env/secret managers only, never hardcoded/in logs/in error messages echoed to users. Sanitize external API errors before showing users. Dangerous defaults: JSON.parse/deserialization without try/catch + shape validation; comparing secrets with ==; missing rate limiting/size caps; CORS *; predictable temp paths. If the diff touches auth/crypto/session/permissions: match the existing codebase pattern, state which security property you preserved. Report discovered vulnerabilities rather than silently fixing beyond scope.

===== SKILL: edge-case-sweep =====
Sweep against every new/changed code path: INPUTS — empty ("", [], {}, zero rows), absent (null/undefined/missing key — distinct from empty), boundaries (0, -1, exactly-at-limit, limit+1, first/last), huge (10^6 items), weird text (unicode, newlines-in-fields, quotes, whitespace, case), duplicates/unsorted. STATE & TIME — called twice (idempotency), concurrently, retried after partial success; stale state (record deleted between fetch and update); timezone/DST/end-of-month. ENVIRONMENT — dependency down/slow/erroring (what does the caller see?), permissions denied, disk full, network cut mid-op. For each applicable case: handle or reject-loudly. Silent wrong behavior is unacceptable; a stated limitation is fine, a hidden one is a bug waiting.

===== SKILL: numerical-care =====
Never compare floats with ==. Money is integers (cents) or Decimal — never binary floats (accumulating float currency drifts into accounting incidents); match what the codebase uses, flag it if it uses floats for money. Rounding is a policy decision (round-half-up/banker's/floor) — pick deliberately, round once at the boundary. Division needs a zero plan — averages of empty lists, percentages of zero totals: every / gets the "denominator 0?" question; check integer vs true division. Representation limits: silent overflow, JS >2^53 int corruption (big IDs as strings), precision loss on casts. Units travel with the value (ms vs s, cents vs dollars) — name variables with units. Aggregating many floats loses precision — use compensated sum. Test: for each arithmetic line, "what value makes this wrong — zero, negative, huge, or 0.1?"

===== SKILL: error-message-quality =====
Every error: three parts — what failed, with what value, what to do — include identifiers (which file/record/endpoint). Never swallow the cause (chain original; log exception with stack; except-pass is a crime scene with evidence removed). Match audience: user-facing says what the user can do and never leaks internals (paths, SQL, stack traces); operator logs get internals. Make messages greppable (stable phrasing, variable parts as values). Log at decision points. Right level: errors are actionable, warnings are tomorrow's errors, info is narrative.

===== SKILL: workmanship =====
Evidence before assertion: every load-bearing claim traces to something you actually read in the code, not assumption. The done gate: re-read as a hostile reviewer — every issue real, no missed call sites, edge cases hunted consciously (empty/zero/null, first-vs-repeat, concurrent, error path). Report what happened: lead with the outcome, claims match evidence exactly, distinguish verified/probable/assumed, no overclaiming.

Return your review as your final message. Do not edit any files.
