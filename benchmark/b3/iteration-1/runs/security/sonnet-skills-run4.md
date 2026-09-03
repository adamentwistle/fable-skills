## Review

**1. SQL injection — critical.** `query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` builds SQL by string interpolation from request input. An attacker sends `user_id = "' OR '1'='1"` and reads every user's orders, or worse (UNION-based exfiltration, stacked writes if the driver/DB allows it). This also breaks the per-user authorization the function is supposed to enforce — it's an SQLi and an IDOR at once. Fix: parameterized query (`?` placeholders), never string formatting into SQL.

**2. `status` and `user_id` never validated — medium.** Even with parameterization, nothing stops a malformed `status` (typo, wrong case, unexpected value) from silently returning an empty list instead of a clear error, and nothing coerces `user_id` to the expected type. Fix: validate `status` against an allowlist of known statuses; parse/validate `user_id` as an int and raise a specific `ValueError` on failure (caller turns that into a 400, not a 500).

**3. Connection and cursor are never closed — medium.** No `try/finally`, no context manager, no `.close()`. Under load this leaks connections/file handles. Fix: wrap in `try/finally: conn.close()` (or `with contextlib.closing(...)`).

**4. No error handling around the DB call — medium.** Any `sqlite3.Error` (locked DB, corrupt file, bad path) propagates straight out of a function called from an HTTP handler, risking a raw traceback/DB details leaking to the client. Fix: catch `sqlite3.Error`, log it with context, raise a sanitized exception for the handler to map to a 500.

**5. No row limit — medium.** The query has no `LIMIT`/pagination, so a user with a very large order history returns everything into memory in one call. Fix: add `LIMIT` (and ideally offset/cursor pagination).

**6. `average_order_value` divides by zero — high.** `total / len(orders)` raises `ZeroDivisionError` whenever a user has no orders in that status — a routine, expected case, not an edge case. Fix: return `0` (or `None`) when `orders` is empty.

**7. Money handled as binary float — medium.** `average_order_value` sums floats and `apply_discount` does float arithmetic on currency. Both accumulate rounding error (`0.1 + 0.2 != 0.3`) and can produce off-by-a-cent totals. Fix: use `Decimal` (or integer minor units) for all money arithmetic, and round explicitly once at the boundary.

**8. `apply_discount` has no bounds check on `pct` — medium.** A negative `pct` increases the price; `pct > 100` yields a negative price. Both are silent data-integrity bugs with no validation or error. Fix: reject `pct` outside `[0, 100]`.

**9. `format_receipt` crashes on every call — high.** `"Order #" + order[0]` concatenates a `str` with `order[0]`, which is the SQL `id` column — an integer. This raises `TypeError` immediately in production, not in some edge case. Fix: use an f-string (`f"Order #{order[0]}"`), which coerces automatically.

**10. `format_receipt` prints raw float — low.** `str(order[1])` can render as `19.990000000004` or `20.0` instead of `$20.00`. Fix: format to two decimal places from a `Decimal`.

**11. Rows returned as bare tuples — low.** Callers index by position (`o[1]`, `order[0]`) with no names; a column reorder in the `SELECT` silently breaks every caller with no error. Fix: use `sqlite3.Row` (or a small dataclass) so fields are accessed by name.

## Corrected code

```python
import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP

ALLOWED_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
MAX_ORDERS = 500


def get_user_orders(db_path, user_id, status):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError(f"invalid user_id: {user_id!r}, must be an integer")

    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}, must be one of {sorted(ALLOWED_STATUSES)}")

    try:
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT id, amount, status FROM orders "
                    "WHERE user_id = ? AND status = ? LIMIT ?",
                    (user_id, status, MAX_ORDERS),
                )
                return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError(f"failed to fetch orders for user_id={user_id}") from e


def average_order_value(orders):
    if not orders:
        return Decimal("0")
    total = sum((Decimal(str(o["amount"])) for o in orders), Decimal("0"))
    return (total / len(orders)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (0 <= pct <= 100):
        raise ValueError(f"invalid discount pct: {pct}, must be between 0 and 100")
    discounted = amount - (amount * pct / Decimal(100))
    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    amount = Decimal(str(order["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"Order #{order['id']}: ${amount}"
```