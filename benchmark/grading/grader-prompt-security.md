<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Full blind-grader prompt (includes the 14-item answer key and the two anonymized reviews A/B exactly as fed to the grader) for the security area, unmodified. -->

---

You are grading two independent code reviews (Review A and Review B) of the same Python module. Score them objectively and blind — you know nothing about who wrote them.

Here is the module they reviewed:

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
Context: `get_user_orders` is called from an HTTP handler where `user_id` and `status` come from the request.

Here is the answer key — the 14 distinct issue classes present in the code:
1. SQL injection (user_id/status interpolated into query)
2. DB connection never closed (leak)
3. format_receipt TypeError ("Order #" + int id)
4. Division by zero when orders is empty
5. Money handled as binary float (should be Decimal/cents)
6. apply_discount: pct not range-validated (negative/>100)
7. status not validated against an allowlist
8. Broken object-level authorization / IDOR (user_id trusted from request, not session)
9. Null/None amount not handled
10. Currency not formatted to 2 decimals
11. Raw DB errors leak to caller (no sanitization/chaining)
12. Rounding is a policy decision not applied (fractional cents mid-calc)
13. Unbounded result set (no LIMIT / pagination)
14. Fragile positional tuple indexing (sqlite3.Row / name access more robust)

For EACH of the 14 issues, mark whether Review A caught it (Y/N) and whether Review B caught it (Y/N). Then give: total count each, a list of issues caught by only one of them, and a 2-3 sentence assessment of relative quality (depth, actionability, correctness). Be strict — only mark Y if the review genuinely identifies that specific issue.

Return a markdown table plus the totals and assessment as your final message.

===== REVIEW A =====
1. SQL injection via %-formatting (CRITICAL) — user_id/status from request; quotes don't help; fix with ? placeholders.
2. Connection never closed (HIGH) — no close/finally/context manager; leaks handles; notes SQLite gotcha that `with sqlite3.connect()` manages the transaction but does NOT close, so use contextlib.closing.
3. format_receipt raises TypeError (HIGH) — "Order #" + order[0] concatenates str+int; fix str()/f-string.
4. average_order_value divides by zero on empty input (HIGH) — guard empty, return 0/None.
5. No allowlist/validation of status (MEDIUM) — validate against known statuses, reject with 4xx.
6. Money handled as binary float (MEDIUM) — use decimal.Decimal, store integer cents/NUMERIC.
7. apply_discount doesn't validate pct (MEDIUM) — negative increases price, >100 negative; validate 0<=pct<=100.
8. average_order_value/format_receipt don't handle NULL amounts (LOW) — o[1] can be None; skip/treat None or enforce NOT NULL.
9. Receipt amount not formatted as currency (LOW) — str(order[1]) renders 9.5; format 2dp.
10. No error handling around DB access (LOW) — sqlite3.Error propagates raw to handler, leaking internals; catch and translate, don't surface raw exception text.
Corrected code: parameterized query, ALLOWED_STATUSES allowlist, contextlib.closing, empty+None handling, Decimal, pct range check, f-string 2dp formatting.

===== REVIEW B =====
C1 SQL injection (CRITICAL) — parameterize with ? placeholders.
C2 Division by zero in average_order_value (CRITICAL) — guard empty list.
H1 Broken object-level authorization / IDOR (HIGH) — user_id comes from request and is trusted; any authenticated caller can read others' orders; WHO must be derived server-side from session/token; added boundary guard + docstring contract; real fix in caller.
H2 Connection leak (HIGH) — use with closing()/try-finally.
H3 Money as binary float (HIGH) — use Decimal via Decimal(str(x)); flag schema should be integer cents.
H4 format_receipt TypeError (HIGH) — "Order #" + order[0] where id is int; use str().
M1 No allowlist validation of status (MEDIUM) — validate against server-side ALLOWED_STATUSES, raise ValueError.
M2 No validation of pct range (MEDIUM) — negative increases charge, >100 negative total; validate 0<=pct<=100.
M3 No rounding policy on discount (MEDIUM) — fractional cents; quantize with ROUND_HALF_UP, round once at boundary.
M4 Unsanitized DB errors leak to caller (MEDIUM) — catch sqlite3.Error, log internals for operators, raise sanitized error chained with `raise ... from e`.
L1 Unbounded result set / no LIMIT (LOW) — fetchall loads all rows; add LIMIT/pagination.
L2 Fragile positional tuple indexing (LOW) — use sqlite3.Row for name-based access; nullable amount -> None -> TypeError; handle None.
L3 average_order_value empty-list return semantics undocumented (LOW) — state the policy.
Corrected code: parameterized query + LIMIT 1000, isinstance check on user_id, ALLOWED_STATUSES, contextlib.closing, sqlite3.Row, Decimal money, None-skipping, quantize ROUND_HALF_UP, pct range check, try/except sqlite3.Error with logging + chained RuntimeError, docstrings stating security contract and rounding policy.
