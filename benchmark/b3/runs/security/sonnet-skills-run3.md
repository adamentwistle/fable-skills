## Review

**1. SQL injection — critical.** `user_id` and `status` come straight from the HTTP request and are interpolated into the query with `%s` and quotes. Any of `' OR '1'='1`, `'; DROP TABLE orders; --` etc. runs as SQL. Fix: parameterized query (`?` placeholders), never string-format user input into SQL.

**2. Missing authorization (IDOR) — critical.** The function trusts `user_id` from the request and returns whatever orders match it, with no check that the caller (the authenticated session) actually owns that `user_id`. Anyone can pass any other user's ID and read their orders. Fix: derive `user_id` from the authenticated session/token server-side, or verify the requested `user_id` matches the caller's identity before querying — never take it as an unchecked request parameter.

**3. `format_receipt` will crash — high.** `order[0]` is the integer `id` column; `"Order #" + order[0]` raises `TypeError: can only concatenate str`. This is a correctness bug that fires on every call, not an edge case. Fix: `str(order[0])`, or an f-string.

**4. Division by zero in `average_order_value` — high.** Empty `orders` list → `ZeroDivisionError`. This is a normal input (a user with no orders), not a rare edge case. Fix: return `0.0` (or `None`, decide the contract) when `orders` is empty.

**5. Money represented as float — high (data integrity).** `amount` is summed/divided/discounted as a float throughout (`average_order_value`, `apply_discount`). Binary floats don't represent currency exactly and errors compound across arithmetic — this will eventually misstate a total by a cent or more. Fix: use `Decimal` (or integer minor units, e.g. cents) for all money arithmetic; convert only at the display boundary.

**6. `status` and `user_id` not validated — medium.** Even after parameterizing the query, arbitrary strings for `status` (or non-numeric `user_id`) reach the database. There's no allowlist for known status values and no type check that `user_id` is the expected shape (e.g. int). Fix: validate `user_id` is an int; validate `status` against a fixed set of known order statuses before querying.

**7. Connection/cursor never closed — medium.** `conn`/`cur` are never closed, and if `cur.execute` raises, the connection leaks. Under load this exhausts file handles / DB connections. Fix: use `with sqlite3.connect(...) as conn:` and close explicitly, or wrap in try/finally.

**8. No error handling around the DB call — medium.** A malformed query, locked DB, or missing file raises an unhandled exception straight out of the HTTP handler's call, likely surfacing a raw traceback (and potentially schema/path details) to the client. Fix: catch `sqlite3.Error`, log it with context, raise/return a sanitized error to the caller.

**9. `apply_discount` doesn't validate `pct` — medium.** A negative `pct` increases the price; `pct > 100` produces a negative amount. Both are silent data-integrity bugs, not exceptions. Fix: validate `0 <= pct <= 100`, raise `ValueError` otherwise.

**10. No rounding policy on the discounted amount — medium.** `apply_discount` returns whatever precision floating point (or Decimal) arithmetic produces, with no defined rounding rule for currency. Fix: round once, at the boundary, with an explicit policy (e.g. `ROUND_HALF_UP` to 2 decimal places).

**11. Unbounded result set — low.** No `LIMIT`/pagination on the orders query; a user with a huge order history returns everything in one shot. Fix: add pagination (`LIMIT`/`OFFSET` or keyset) if this is expected to scale.

**12. `average_order_value` trusts `o[1]` is numeric — low.** If a row ever has a non-numeric `amount` (bad data, schema drift), this throws a `TypeError` deep inside a loop with no context. Fix: not worth heavy validation given the DB schema should guarantee this, but if this function receives externally-assembled data elsewhere, validate at that boundary.

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

ALLOWED_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status, limit=100, offset=0):
    if not isinstance(user_id, int):
        raise ValueError(f"user_id must be an int, got {user_id!r}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown order status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(query, (user_id, status, limit, offset))
            return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError("failed to fetch orders") from e


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
    discounted = amount - amount * pct / 100
    return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    return f"Order #{order[0]}: ${order[1]}"
```

Note: the authorization check (finding 2) belongs in the HTTP handler that calls `get_user_orders`, not in this function alone — this module can only validate shape/values, not confirm the caller is entitled to `user_id`. Make sure that check exists at the call site before this ships.