## Issues found

**1. SQL injection — critical.** `get_user_orders` builds the query with `%` string formatting on `user_id`/`status`, both attacker-controlled from the HTTP request. A value like `' OR '1'='1` returns every user's orders; malformed quotes break the query or exfiltrate data. Fix: use parameterized queries (`?` placeholders), never string-format SQL.

**2. Missing authorization check — high.** The function trusts `user_id` as passed in, with no check that it matches the authenticated caller's own account. If the HTTP handler forwards a client-supplied `user_id` without binding it to the logged-in session, this is an IDOR — any user can read any other user's orders. Fix: derive `user_id` from the authenticated session server-side, not from request parameters, or explicitly verify the requester owns that `user_id` before calling this function.

**3. No status allowlist validation — medium.** Even after parameterizing, `status` should be checked against the known set of valid order statuses before hitting the DB. An unexpected value silently returns zero rows instead of surfacing a bad request. Fix: validate against an allowlist (e.g. `{"pending","paid","shipped","delivered","cancelled","refunded"}`), reject anything else with a 400-style error.

**4. Connection/cursor never closed — medium.** `conn`/`cur` leak on every call, and doubly so if an exception is raised mid-query (no `try/finally`). Under load this exhausts file handles / DB connections. Fix: use `with sqlite3.connect(...) as conn:` plus `conn.close()` in a `finally`, or a context manager wrapping both.

**5. Unhandled DB exceptions — medium.** A locked DB, missing table, or malformed query raises `sqlite3.OperationalError` straight out of the function; if that propagates to an HTTP error response unmodified it can leak internal schema/path details to the client. Fix: catch DB errors, log the real exception server-side, return a sanitized generic error to the caller.

**6. `average_order_value` divides by zero — high.** Empty `orders` list raises `ZeroDivisionError`, crashing the caller for a user with no orders (a very ordinary case). Fix: return `0.0` (or `None`) when `len(orders) == 0`.

**7. Money handled as binary float — medium.** `amount` is summed and divided as `float` throughout (`total`, `apply_discount`, `format_receipt`). Floats can't represent currency exactly (`0.1 + 0.2 != 0.3`), so totals/discounts will drift by fractions of a cent and can display as e.g. `$19.999999999997`. Fix: store/transport money as integer minor units (cents) or `Decimal`, and round once at the display boundary with an explicit policy (e.g. `ROUND_HALF_UP` to 2 places). This also requires the `orders` table itself to stop using a `REAL` column, which is outside this snippet — flagging it as a limitation of the patch below.

**8. `apply_discount` has no bounds check on `pct` — medium.** A negative percentage increases the price; a percentage over 100 makes the amount negative. Neither is validated. Fix: reject `pct` outside `[0, 100]`.

**9. `format_receipt` crashes on a real DB row — high.** `order[0]` (the `id` column) comes back from SQLite as an `int`, but the code does `"Order #" + order[0]`, concatenating `str + int` — this raises `TypeError` on every call with real data, not just malformed input. Fix: `str(order[0])`, and round `order[1]` to 2 decimals when formatting.

**10. Unbounded result set — low/medium.** No `LIMIT`/pagination on the query; a user with a very large order history returns the entire table in one response. Fix: add a bounded `LIMIT` (with pagination if the caller needs more).

**11. No type/None checks on `db_path`, `user_id`** — low. Not exploitable, but a `None` or wrong-typed `user_id` produces a confusing downstream error rather than a clear one. Fix: basic type validation at the boundary with a clear rejection message.

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
MAX_ORDERS = 1000


def get_user_orders(db_path, user_id, status, limit=MAX_ORDERS):
    """user_id must already be the authenticated caller's own id, verified by the HTTP handler."""
    if not isinstance(user_id, int):
        raise ValueError(f"user_id must be an int, got {type(user_id).__name__}")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status '{status}', must be one of {sorted(VALID_STATUSES)}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "LIMIT ?"
    )
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(query, (user_id, status, limit))
            return cur.fetchall()
    except sqlite3.Error as e:
        # log e with real detail server-side; don't leak it to the caller
        raise RuntimeError("failed to fetch orders") from e


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o[1])) for o in orders)
    avg = total / len(orders)
    return avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (0 <= pct <= 100):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    discounted = amount - amount * pct / 100
    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    order_id, amount, _status = order
    amount_dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"Order #{order_id}: ${amount_dec}"
```

Remaining limitation not fixable in this file alone: if the `orders.amount` column is `REAL` in the schema, values already lose precision on write. That needs a schema change (store cents as `INTEGER`) to fully close the money-as-float hazard.