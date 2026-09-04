## Issues

1. **SQL injection — critical.** `query = "... '%s' ... '%s'" % (user_id, status)` builds SQL by string formatting on request-controlled values. Trivial to exfiltrate or modify data (`user_id = "x' OR '1'='1"`). Fix: parameterized query.

2. **Missing authorization check — critical.** The function trusts whatever `user_id` the caller passes with no check that it matches the authenticated session. If the HTTP handler forwards a client-supplied `user_id` instead of deriving it from the session, any user can read any other user's orders (IDOR). Fix: the handler must pass the authenticated user's own ID, not a client-supplied one; this function should not be the authorization boundary but must not make it easy to bypass either.

3. **No allowlist on `status` — high.** Even parameterized, `status` should be validated against the known set of order statuses (e.g. `{"pending","paid","shipped","cancelled","refunded"}`) before hitting the DB. Prevents typos/garbage silently returning zero rows and keeps the query intent explicit.

4. **Connection/cursor never closed — high.** `conn` and `cur` leak on every call (no `close()`, no context manager, no try/finally). Under load this exhausts file handles / DB connections. Fix: use `with sqlite3.connect(...) as conn:` and close the cursor, or wrap in try/finally.

5. **No error handling around DB call — medium.** A malformed DB path, locked DB, or query error raises an unhandled exception straight into the HTTP handler, likely leaking a stack trace / internals to the client. Fix: catch `sqlite3.Error`, log with context, raise a sanitized application-level error.

6. **`average_order_value` divides by zero — high.** Empty `orders` list (a user with no orders, or a status filter matching nothing) raises `ZeroDivisionError`. Fix: return `0.0` (or `None`) when `len(orders) == 0`, decide and document the policy.

7. **`average_order_value` sums by fixed index `o[1]`, coupled to row shape — medium.** If the column order changes upstream, this silently sums the wrong field. Fix: use named access (sqlite3 `Row` factory or a dataclass) instead of positional tuple indexing.

8. **Floating point for currency — high (data integrity).** `amount` is stored/summed as `float` throughout (`total = 0.0`, `apply_discount`). Binary floats can't represent money exactly; summing many orders or applying percentage discounts will drift (e.g. `0.1 + 0.2 != 0.3`). Fix: store amounts as integer minor units (cents) or use `decimal.Decimal`, and do all arithmetic in that type.

9. **`apply_discount` has no bounds/type checking — medium.** A negative `pct`, `pct > 100`, or non-numeric `amount`/`pct` produces nonsensical charges (negative discount = price increase, >100% = negative price) with no validation. Fix: validate `0 <= pct <= 100` and raise on invalid input rather than silently computing garbage.

10. **`apply_discount` rounds nowhere — low/medium.** Result isn't rounded to currency precision, compounding issue #8. Fix: round once at the boundary using the chosen rounding policy (e.g. round-half-up) after switching to `Decimal`.

11. **`format_receipt` assumes `order[0]` is a string — medium.** `order[0]` is the SQLite integer `id`; `"Order #" + order[0]` raises `TypeError: can only concatenate str`. Fix: `str(order[0])`, and use an f-string.

12. **`format_receipt` doesn't format currency — low.** `str(order[1])` on a float can print as `19.989999999999998` or in scientific notation for very small/large values, and never shows two decimal places. Fix: format with `f"{amount:.2f}"` after converting to `Decimal`/cents.

13. **`format_receipt` doesn't escape/sanitize for its output context — low (context-dependent).** If this string is ever rendered as HTML rather than plain text/log, an amount or ID sourced from data an attacker influenced (unlikely for `id`, more plausible if this pattern is reused elsewhere) could inject markup. Not exploitable as written since values are numeric, but worth flagging if `format_receipt` output goes to a web page — escape at the render site.

14. **No logging at the point of DB failure or empty result — low.** For a production service, an operator debugging "wrong totals" or "empty receipts" has nothing to grep. Fix: log query failures with `user_id`/status (not raw amounts if sensitive) and a request/correlation ID if available.

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

VALID_STATUSES = {"pending", "paid", "shipped", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid order status: {status!r}")

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?",
                (user_id, status),
            )
            return cur.fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to fetch orders for user_id={user_id}") from exc


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o["amount"])) for o in orders)
    return (total / len(orders)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (0 <= pct <= 100):
        raise ValueError(f"discount pct must be between 0 and 100, got {pct}")
    result = amount - amount * pct / Decimal(100)
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    amount = Decimal(str(order["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"Order #{order['id']}: ${amount}"
```

Note: `get_user_orders` still takes `user_id` as a parameter, but the calling HTTP handler must set it from the authenticated session, never from request input the client controls — that authorization boundary can't be fixed inside this function alone.