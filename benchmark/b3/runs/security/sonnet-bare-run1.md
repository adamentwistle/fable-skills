## Issues

**SQL injection — critical.** `query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` builds the query by string interpolation with values that come straight from the HTTP request. Any attacker can pass `status = "x' OR '1'='1"` to dump every user's orders, or worse. Fix: parameterized query (`?` placeholders), never string formatting into SQL.

**Crash in `format_receipt` — critical.** `order[0]` is the `id` column, an integer. `"Order #" + order[0]` raises `TypeError: can only concatenate str` on every real order. This function cannot currently run successfully.

**Crash in `average_order_value` on empty list — high.** `total / len(orders)` raises `ZeroDivisionError` when a user has no orders matching the filter — a completely normal case for a new user or a status with no matches.

**Connection/cursor never closed — high.** `conn` and `cur` are left open on every call, including on exception (the query executing before any error would leave the connection dangling). Called from an HTTP handler, this leaks a SQLite handle per request and will exhaust file handles/connections under load. Fix: use `with`/`contextlib.closing` so the connection always closes.

**No status validation / no allow-list — medium.** Beyond injection, nothing stops an arbitrary string being persisted as a filter or returned to the caller. If there's a fixed set of valid statuses, validate against it and reject/400 early instead of hitting the DB.

**Money as raw float — medium.** `amount` flows through as whatever SQLite/Python gives it and `apply_discount` does float arithmetic. Floating point isn't safe for currency (rounding drift accumulates). Use `Decimal`.

**`apply_discount` has no bounds check — medium.** A negative `pct` increases the price instead of discounting it; a `pct > 100` produces a negative amount. Both are silent data-integrity bugs, not exceptions, so they're easy to ship unnoticed. Validate `0 <= pct <= 100`.

**`format_receipt` doesn't format currency — low.** `str(1.5)` renders `"$1.5"` instead of `"$1.50"`. Round/format to 2 decimal places.

**No `ORDER BY` — low.** Result order is undefined and can vary between calls/versions of SQLite; if the caller displays a list, that's a stability bug. Add explicit ordering.

**No connection timeout — low.** `sqlite3.connect(db_path)` with the default timeout can hang the request thread if the DB is locked. Pass an explicit `timeout=`.

**No error handling around the DB call — low.** Any DB error (locked file, missing table, bad path) propagates as a raw exception up through the HTTP handler; depending on the framework this can leak internals in a 500 response. At minimum this should be handled at the handler boundary, not silently trusted here.

## Corrected code

```python
import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP

# Adjust to the actual set of statuses your schema supports.
VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id"
    )
    with closing(sqlite3.connect(db_path, timeout=5)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(query, (user_id, status))
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
        raise ValueError(f"discount pct out of range: {pct}")
    result = amount - amount * pct / Decimal(100)
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    order_id, amount, _status = order
    amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"Order #{order_id}: ${amount}"
```

Note: `get_user_orders` now raises `ValueError` on an invalid status instead of silently querying — the HTTP handler needs to catch that and return a 400.