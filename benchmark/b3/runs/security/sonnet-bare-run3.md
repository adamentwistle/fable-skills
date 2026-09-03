## Issues

**1. SQL injection — critical.** `query = "... = '%s' ... '%s'" % (user_id, status)` builds SQL from unsanitized request input. Any request can read/alter/drop data (`user_id = 1' OR '1'='1`, or worse). Fix: parameterized query with `?` placeholders, never string-format values into SQL.

**2. No input validation — high.** `status` should be checked against a known enum of order statuses; `user_id` should be validated/coerced to an int. Without this, even the parameterized version accepts garbage and silently returns zero rows, masking bugs and letting malformed IDs through the handler.

**3. Connection/cursor never closed — high (resource leak).** `conn`/`cur` are never closed, including on the exception path (e.g. injection attempt causing a syntax error). Under load this exhausts file handles/DB connections. Fix: `try/finally` with `conn.close()` (note: `with sqlite3.connect(...) as conn:` only commits/rolls back the transaction — it does **not** close the connection, a common gotcha).

**4. No connect timeout — medium.** `sqlite3.connect(db_path)` with no `timeout` can block indefinitely on a locked database. Set a `timeout`.

**5. Division by zero in `average_order_value` — high.** `total / len(orders)` raises `ZeroDivisionError` when `orders` is empty (e.g., a user with no matching orders), which will 500 the handler. Fix: return 0 (or `None`) for empty input.

**6. Money stored/summed as `float` — high (data integrity).** Floats cannot represent currency exactly (`0.1 + 0.2 != 0.3`); summing/averaging amounts will drift. Fix: use `Decimal` for all money arithmetic, quantized to 2 places.

**7. `apply_discount` has no bounds checking — medium.** A negative `pct` increases the price; `pct > 100` produces a negative amount. Both are business-logic bugs if this value ever comes from user input. Fix: validate `0 <= pct <= 100`.

**8. `apply_discount` doesn't round — low/medium.** Result can have many decimal places (e.g. `9.987`), which is invalid for a currency amount. Fix: quantize to cents.

**9. `format_receipt` will crash — high (correctness bug, not just style).** `order[0]` (the `id` column) is an `int`; `"Order #" + order[0]` raises `TypeError: can only concatenate str`. This is broken on any real row, not an edge case.

**10. `format_receipt` doesn't format cents — low.** `str(order[1])` prints `$19.9` instead of `$19.90`. Fix: format to 2 decimal places.

**11. No result bound/pagination — low.** A user with many orders returns everything in one shot; fine at small scale, but worth a `LIMIT`/pagination if this is user-facing at scale.

## Corrected code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError(f"invalid user_id: {user_id!r}")

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?",
            (user_id, status),
        )
        return cur.fetchall()
    finally:
        conn.close()


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
    amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"Order #{order_id}: ${amount}"
```