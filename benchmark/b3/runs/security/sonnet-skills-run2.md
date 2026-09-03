## Issues found

**1. SQL injection — critical.** `query = "... '%s' ... '%s'" % (user_id, status)` builds the query by string interpolation with values that come straight from the HTTP request. Fix: use parameterized queries (`?` placeholders + a tuple), never string formatting.

**2. Missing authorization (IDOR) — critical.** `user_id` comes from the request, and this function trusts it with no check that it matches the authenticated caller. Any logged-in user could pass another user's ID and read their orders. Fix: the HTTP handler must verify the authenticated session's user matches `user_id` (or has admin rights) before calling this function — this can't be fixed inside `get_user_orders` alone, but it must be fixed before this ships.

**3. No status allowlist — medium, defense in depth.** Even with parameterized queries, `status` should be validated against a known set of order statuses at the boundary. An unexpected value should be rejected, not silently sent to the DB.

**4. Division by zero in `average_order_value` — high.** `total / len(orders)` throws `ZeroDivisionError` when `orders` is empty (a legitimate case — a user with a valid account and no matching orders). This will crash the handler with an unhandled 500. Fix: return 0 (or `None`) for the empty case.

**5. Money stored/handled as `float` — high (data integrity).** `amount` is summed and divided as a float. Floating-point arithmetic on currency accumulates rounding error (`0.1 + 0.2 != 0.3`) and can misstate totals. Fix: use `Decimal` (ideally the DB itself should store integer minor units/cents).

**6. `format_receipt` crashes on non-string `order[0]` — high (correctness bug).** `order[0]` is the numeric order ID from SQLite (an int); `"Order #" + order[0]` raises `TypeError: can only concatenate str`. This is called on every order and will always fail as written. Fix: `str()`/f-string the ID.

**7. No rounding on discounted/displayed amounts — medium.** `apply_discount` and `format_receipt` don't round, so results can show as `19.999999999997`. Round once, at the point of display/storage, with a stated policy (half-up here).

**8. `apply_discount` doesn't validate `pct` — medium.** A negative `pct` increases the price; `pct > 100` produces a negative amount. Fix: clamp/reject outside `[0, 100]`.

**9. No connection/cursor cleanup — medium (resource leak).** `conn`/`cur` are never closed, and there's no `try`/`finally` or context manager, so on any exception (including the SQL error you'd hit before the injection fix) the connection leaks. In a long-running service this exhausts the connection pool. Fix: `with sqlite3.connect(...) as conn:`.

**10. No error handling around the DB call — medium (info leak / error-message-quality).** Any `sqlite3.Error` propagates unhandled up to the HTTP layer, risking a raw DB error (schema/path detail) reaching the client. Fix: catch and translate to a generic error for the caller, log the real exception internally.

**11. Unbounded result set — low.** No `LIMIT`/pagination; a user with an enormous order history returns everything in one query. Add a `LIMIT` and pagination if this is user-facing.

**12. No type check on `user_id` — low, but cheap defense in depth.** Validating it's an `int` before use catches malformed input early with a clear error instead of an obscure downstream failure.

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    # Caller (HTTP handler) MUST verify the authenticated session's user
    # owns user_id (or has admin rights) before calling this — not enforced here.
    if not isinstance(user_id, int):
        raise ValueError(f"user_id must be an int, got {user_id!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}")

    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ? LIMIT 1000",
                (user_id, status),
            )
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
    order_id, amount, _status = order
    return f"Order #{order_id}: ${Decimal(str(amount)).quantize(Decimal('0.01'))}"
```

Note: this assumes `orders.amount` is currently stored as `REAL`/float in SQLite. The more durable fix is migrating the column to integer cents; converting to `Decimal` at read time (as above) reduces but doesn't eliminate the risk if the source data already lost precision on write.