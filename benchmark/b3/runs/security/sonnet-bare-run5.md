## Issues found

**1. SQL injection — critical.** `query = "... '%s' ... '%s'" % (user_id, status)` builds SQL by string interpolation directly from HTTP request input. Any request can inject arbitrary SQL (read other users' orders, drop tables, etc.). Fix: use parameterized queries (`?` placeholders), never string-format user input into SQL.

**2. `format_receipt` crashes on every call — critical/correctness.** `order[0]` is the `id` column, which SQLite/`sqlite3` returns as an `int`. `"Order #" + order[0]` raises `TypeError: can only concatenate str (not "int") to str`. Fix: `str(order[0])`.

**3. Division by zero in `average_order_value` — high.** If `orders` is empty (valid case — a user with no matching orders), `total / len(orders)` raises `ZeroDivisionError`. Fix: guard for empty list, return `0.0` or `None`.

**4. Connection/cursor never closed — high (resource leak).** `conn`/`cur` are never closed, and nothing runs if `cur.execute` raises. Under load this exhausts SQLite handles/connections. Fix: use a `with` block / `try...finally`, or a context manager wrapper.

**5. No error handling around the DB call — medium.** A malformed query or locked DB raises an unhandled exception straight into the HTTP handler (potential 500 with a stack trace leaking to the client, depending on the framework). Fix: catch `sqlite3.Error`, translate to a proper application-level error.

**6. `status` not validated against an allowlist — medium.** Even after parameterizing the query, arbitrary strings reach the DB layer as a "status" filter. If status is meant to be one of a fixed set (`pending`, `shipped`, etc.), validate it before querying so bad input fails fast with a clear error instead of just silently returning zero rows.

**7. Money represented as `float` — medium (data integrity).** `total`, `apply_discount`, amounts from the DB — all `float`. Floating-point arithmetic on currency accumulates rounding errors. Fix: use `Decimal` or store/compute in integer cents.

**8. `apply_discount` doesn't validate `pct` — medium.** A negative `pct` increases the price; a `pct > 100` produces a negative amount. Fix: clamp/validate `0 <= pct <= 100`, raise on invalid input.

**9. No `LIMIT`/pagination on the orders query — low.** A user with a huge order history returns everything in one shot; fine at small scale, a latency/memory risk at production scale. Fix: add pagination (`LIMIT`/`OFFSET` or keyset).

**10. `user_id`/`status` types not checked — low.** Nothing stops `user_id` being `None` or the wrong type before it reaches the query. Fix: validate at the HTTP boundary (this module can assume validated input, but note the boundary that must enforce it).

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from contextlib import closing

ALLOWED_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status, limit=100, offset=0):
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "LIMIT ? OFFSET ?"
    )
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cur:
            try:
                cur.execute(query, (user_id, status, limit, offset))
                return cur.fetchall()
            except sqlite3.Error as e:
                raise RuntimeError(f"failed to fetch orders for user {user_id}") from e


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o[1])) for o in orders)
    return (total / len(orders)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (0 <= pct <= 100):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    result = amount - amount * pct / 100
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    return "Order #" + str(order[0]) + ": $" + str(order[1])
```

Note: `user_id` and `status` type/None checks are assumed to happen at the HTTP handler boundary before this module is called — this module now also fails loudly (`ValueError`) if an unexpected status slips through.