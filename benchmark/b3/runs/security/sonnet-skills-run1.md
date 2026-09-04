## SQL injection — critical
`query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` builds SQL by string interpolation from request-controlled `user_id`/`status`. Any of `' OR '1'='1`, `'; DROP TABLE orders; --`, or a `UNION SELECT` lets an attacker read or modify any row, including other users' orders. This is also the IDOR vector — it doesn't just break the query, it can bypass any per-user filtering entirely. Fix: use a parameterized query (`?` placeholders, params passed to `execute`).

## Missing authorization check — critical
Even with the query fixed, nothing verifies the caller is allowed to see `user_id`'s orders — `user_id` comes straight from the request. Any authenticated user could pass someone else's ID and get their order history. Fix: in the HTTP handler, derive `user_id` from the authenticated session (or verify the requested `user_id` matches the caller / caller has admin role) before calling this function — never trust a client-supplied user_id for authorization.

## `format_receipt` crashes on every call — high
`"Order #" + order[0]` — `order[0]` is the `id` column, an int, not a str. `str + int` raises `TypeError`. Fix: `str(order[0])` or an f-string.

## Division by zero in `average_order_value` — high
`total / len(orders)` raises `ZeroDivisionError` when `orders` is empty (e.g., a user with no orders in that status — a normal, reachable case). Fix: return `0` (or `None`) when `orders` is empty.

## Money handled as binary float — medium
`total`, `amount`, and the discount math all use plain floats. Float arithmetic on currency accumulates rounding error and can misprice orders (`0.1 + 0.2 != 0.3` class of bug). Fix: use `Decimal` (or integer minor units, if that's what the schema stores) for all money arithmetic, and round once at the display boundary.

## `apply_discount` doesn't validate `pct` — medium
A negative `pct` increases the price; `pct > 100` gives a negative amount. Neither is checked. Fix: reject `pct` outside `[0, 100]`.

## `status` not validated against a known set — medium
Defense in depth: even after parameterizing, an unexpected `status` value silently returns zero rows instead of surfacing a clear error, which can mask a bug upstream (e.g., a typo'd status enum). Fix: allowlist known statuses and raise on anything else.

## Connection/cursor never closed — medium
`get_user_orders` opens a `sqlite3.connect` and never closes it (no `close()`, no context manager, no `try/finally`). Under load this leaks connections/file handles. Fix: use `with sqlite3.connect(...) as conn:`.

## Unbounded result set — low
No `LIMIT` on the query — a user with a huge order history returns everything into memory in one `fetchall()`. Fix: add a `LIMIT` and/or paginate.

## No error handling around the DB call — low
A bad `db_path`, a locked database, or a malformed row propagates a raw `sqlite3` exception (or a `TypeError`/`InvalidOperation` from bad `amount` data) straight to the caller with no context. Fix: at minimum let it propagate with a clear boundary — don't swallow it silently; if the handler needs a user-safe message, wrap and log it there rather than in this module.

---

```python
import sqlite3
from decimal import Decimal, InvalidOperation

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown order status: {status!r}")

    query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ? LIMIT 1000"
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
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
    return amount - amount * pct / 100


def format_receipt(order):
    order_id, amount, _status = order
    try:
        amount = Decimal(str(amount))
    except InvalidOperation:
        amount = Decimal("0")
    return f"Order #{order_id}: ${amount:.2f}"
```

Note: `get_user_orders` still takes `user_id` as given — the authorization check (does the caller own or have rights to this `user_id`) must happen in the HTTP handler before this function is ever called; no amount of parameterization here fixes that.