## Issues

1. **SQL injection — critical.** `query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` builds SQL by string interpolation from request-controlled values. Any input like `' OR '1'='1` or a `UNION SELECT` reads or exfiltrates the whole orders table. Fix: parameterized query (`?` placeholders), never string-format SQL.

2. **Missing per-object authorization — high.** `user_id` comes straight from the request and is used to fetch orders with no check that the authenticated caller is that user (or an admin). This is a classic IDOR: any logged-in user can pass another user's `user_id` and read their orders. Fix: the HTTP handler must derive `user_id` from the authenticated session (or verify the requested `user_id` matches the caller/role) before calling this function — don't trust a client-supplied `user_id` as authorization.

3. **Unvalidated `status` — medium.** Even once parameterized, `status` is passed through unchecked. Not exploitable for injection anymore, but an unrecognized value silently returns an empty result instead of a clear 400. Fix: validate against an allowlist of known status values and raise/return a client error otherwise.

4. **`user_id` type not validated — medium.** If `user_id` arrives as a non-numeric string (e.g. from a malformed request), it's silently passed to the query and just returns zero rows instead of failing loudly. Fix: validate/cast to `int` at the boundary and reject otherwise.

5. **Connection/cursor never closed — medium (resource leak).** `conn`/`cur` are never closed on any path, including exceptions. Under load this exhausts file handles/DB connections. Fix: use `with contextlib.closing(...)` (or a `with` on the connection) so they close deterministically.

6. **`average_order_value` divides by zero — high.** `total / len(orders)` raises `ZeroDivisionError` for an empty order list (a normal case, e.g. a user with no orders in that status). Fix: return `0` (or `None`/raise a specific handled exception) when `orders` is empty.

7. **Money represented as `float` — high (data integrity).** `total` accumulates `float` amounts and `apply_discount` does `float` arithmetic. Binary floats cannot represent currency exactly (`0.1 + 0.2 != 0.3`), so totals/discounts will drift from the true cent value over many orders. Fix: use `Decimal` (or integer minor units/cents) for all money math, and round once at the boundary with an explicit policy (e.g. `ROUND_HALF_UP` to 2 places).

8. **`apply_discount` has no bounds check — medium.** A negative `pct` increases the price; a `pct > 100` produces a negative amount. Fix: validate `0 <= pct <= 100` and raise `ValueError` otherwise.

9. **`format_receipt` crashes on the common case — high (correctness bug).** `"Order #" + order[0]` assumes `order[0]` is a `str`, but it's the SQLite `id` column, which comes back as an `int`. `str + int` raises `TypeError` on every call. Fix: use an f-string or `str(order[0])`.

10. **`format_receipt` prints raw float — medium.** `str(order[1])` can render as `$19.999999999999996` for float amounts, and doesn't enforce 2-decimal currency formatting. Fix: format via `Decimal` quantized to cents (falls out once amounts are `Decimal` end-to-end).

11. **No result cap on `get_user_orders` — low.** A user with a very large order history returns unbounded rows in one call, and the caller has no way to paginate. Fix: add `LIMIT`/`OFFSET` (or keyset pagination) parameters.

## Corrected code

```python
import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}

TWO_PLACES = Decimal("0.01")


def get_user_orders(db_path, user_id, status, limit=100, offset=0):
    """Caller (HTTP handler) must ensure user_id is the authenticated
    caller's own id, or that the caller is authorized to view it."""
    if not isinstance(user_id, int):
        raise ValueError(f"user_id must be an int, got {type(user_id).__name__!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown order status: {status!r}")

    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, amount, status FROM orders "
                "WHERE user_id = ? AND status = ? "
                "LIMIT ? OFFSET ?",
                (user_id, status, limit, offset),
            )
            return cur.fetchall()


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o[1])) for o in orders)
    return (total / len(orders)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (Decimal("0") <= pct <= Decimal("100")):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    discounted = amount - amount * pct / Decimal(100)
    return discounted.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_receipt(order):
    order_id, amount, _status = order
    price = Decimal(str(amount)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f"Order #{order_id}: ${price}"
```

Note: authorization (issue 2) can't be fully fixed inside this module — it has to be enforced by whatever HTTP handler calls `get_user_orders`, by binding `user_id` to the authenticated session rather than trusting a request parameter.