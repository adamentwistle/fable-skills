Biggest problem: SQL injection in `get_user_orders` — `user_id` and `status` are string-formatted directly into the query, and both come straight from an HTTP request. That's a full DB compromise vector (read/write/delete any row, depending on SQLite permissions).

**Issues, most severe first:**

1. **SQL injection (critical)** — `"... = '%s'" % (user_id, status)`. Attacker-controlled request params go straight into SQL. Fix: parameterized query (`?` placeholders), never string-format user input into SQL.
2. **Missing authorization / IDOR risk (critical, assuming it's not handled by the caller)** — nothing here confirms `user_id` is the authenticated caller's own ID. If the HTTP handler passes the request's `user_id` param without checking it against the logged-in session, any user can read any other user's orders. This must be enforced before calling this function (or the function should take the authenticated ID, not a request param).
3. **Division by zero in `average_order_value` (high)** — a user with zero matching orders crashes the request (`ZeroDivisionError` → 500). Fix: return 0 (or `None`) when `orders` is empty.
4. **TypeError in `format_receipt` (high)** — `order[0]` (an `id`, an int) is concatenated with `+` to a string; this raises `TypeError` on every real order. Fix: use an f-string / `str()`.
5. **Money stored/summed as float (high for e-commerce)** — `amount` is floated through `total`, `apply_discount`, string formatting. Binary floats can't represent cents exactly, so totals and discounts will drift. Fix: use `Decimal` (or store money as integer cents) end to end.
6. **No input validation on `status` (medium)** — even after parameterizing, an arbitrary string is accepted and passed to the DB. Fix: validate against a known set of statuses (enum/allow-list), reject/ignore anything else.
7. **`apply_discount` doesn't validate `pct` (medium)** — negative or >100 values silently produce negative or nonsensical prices. Fix: bounds-check (`0 <= pct <= 100`), raise otherwise.
8. **Connection/cursor never closed (medium)** — no `close()`, no `try/finally`, no context manager. Under load this leaks SQLite connections/file handles. Fix: use `with contextlib.closing(...)` (or a `with` block) for both connection and cursor.
9. **Unbounded query / no pagination (medium)** — `fetchall()` with no `LIMIT` lets a user with a huge order history pull the entire table into memory in one call. Fix: add a `LIMIT` (and ideally pagination) parameter.
10. **No exception handling around DB calls (low-medium)** — a locked/corrupt DB or bad path raises a raw `sqlite3` exception up through the HTTP handler, potentially leaking internals in an error response. Fix: catch DB errors at the boundary and return a generic error.
11. **No `status=None` / "all statuses" case (low)** — the function forces a status filter even when the caller might want all orders; not fatal, just an API gap worth deciding on deliberately.
12. **Result rows are unnamed tuples (low)** — `order[0]`, `o[1]` etc. are fragile to any column reorder in the query. Fix: use `sqlite3.Row`, a `namedtuple`, or a dataclass.

**Corrected code:**

```python
import sqlite3
from contextlib import closing
from decimal import Decimal

ALLOWED_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
MAX_ORDERS = 500


def get_user_orders(db_path, user_id, status, limit=MAX_ORDERS):
    """Caller MUST ensure user_id is the authenticated caller's own id."""
    if not isinstance(user_id, int):
        raise ValueError("user_id must be an integer")
    if status is not None and status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    query = "SELECT id, amount, status FROM orders WHERE user_id = ?"
    params = [user_id]
    if status is not None:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def average_order_value(orders):
    if not orders:
        return Decimal("0")
    total = sum(Decimal(str(o[1])) for o in orders)
    return total / len(orders)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (0 <= pct <= 100):
        raise ValueError("pct must be between 0 and 100")
    return amount - (amount * pct / 100)


def format_receipt(order):
    order_id, amount, _status = order
    return f"Order #{order_id}: ${amount}"
```

Note: point 2 (authorization) can't be fully fixed inside this module — it needs the HTTP handler to pass the *session's* user ID, not a request-supplied one. Flag that to whoever owns the handler.