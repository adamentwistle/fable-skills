## Review

**1. SQL injection — critical.** `"... = '%s' ...\" % (user_id, status)` builds SQL by string interpolation from HTTP-request-controlled values (`user_id`, `status`). Trivial to break out of the quotes and run arbitrary SQL (data exfiltration, `UNION` reads of other tables, etc.). Fix: use parameterized queries (`?` placeholders), never string formatting, for any value from outside the process.

**2. Division by zero in `average_order_value` — high.** A user with zero orders (completely normal, e.g. new account or a status filter that matches nothing) makes `total / len(orders)` raise `ZeroDivisionError`, crashing the handler. Fix: return `0.0` (or `None`) when `orders` is empty.

**3. `format_receipt` assumes `order[0]` is a string — high.** sqlite returns the `id` column as an `int`; `"Order #" + order[0]` raises `TypeError: can only concatenate str`. Fix: `str(order[0])`.

**4. Resource leak: connection/cursor never closed — medium.** `conn`/`cur` are never closed, and there's no `try/finally`, so an exception (or just forgetting) leaks a connection per call. Under load this exhausts file handles / DB connections. Fix: use `with sqlite3.connect(...)` (or explicit `try/finally: conn.close()`).

**5. No error handling around the DB call — medium.** Any sqlite error (locked db, bad path, corrupt file) propagates raw out of the function into the HTTP handler, likely surfacing an internal stack trace / file path to the client. Fix: catch `sqlite3.Error`, log it with context, raise/return a sanitized error at the API boundary.

**6. Money represented as raw `float` — medium.** `amount` is summed and discounted as `float`; float arithmetic isn't exact for currency (`0.1 + 0.2 != 0.3`), so totals/discounts can be off by fractions of a cent and drift under aggregation. Fix: store/compute money as integer minor units (cents) or `Decimal`, and round once at the display boundary with a stated policy.

**7. `apply_discount` doesn't validate `pct` — medium.** No check that `0 <= pct <= 100`. A negative `pct` increases the price silently; `pct > 100` produces a negative amount silently. Both are silent-wrong-answer bugs in a pricing function. Fix: validate range, raise `ValueError` outside it.

**8. `status` not validated against known values — low.** Even after parameterizing the query, an arbitrary/misspelled status string just silently returns zero rows rather than surfacing "not a real status." Fix: check against an allowlist (`{"pending", "paid", "shipped", "cancelled", ...}`) before querying and reject/loudly-error on unknown values.

**9. `user_id` not validated — low.** No check that it's a plausible ID (e.g. positive int). Parameterization prevents injection, but a malformed `user_id` (empty string, negative, non-numeric) should be rejected at the boundary rather than silently querying and returning nothing.

**10. Unbounded result set — low.** No `LIMIT`/pagination; a user with a huge number of orders returns everything in one shot. Fine for typical scale, but worth a cap plus pagination if this is public-facing.

**11. Fragile positional tuple access — low.** `o[1]`, `order[0]`, `order[2]` throughout rely on column order matching the `SELECT` list by memory. A future column reorder silently breaks callers. Fix: use `row_factory = sqlite3.Row` or a small `NamedTuple`/dataclass and access by name.

## Corrected code

```python
import sqlite3
import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"user_id must be a positive integer, got {user_id!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown order status {status!r}")

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ? LIMIT 1000",
                (user_id, status),
            )
            return cur.fetchall()
    except sqlite3.Error:
        logger.exception("get_user_orders failed for user_id=%s status=%s", user_id, status)
        raise RuntimeError("could not load orders") from None


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o["amount"])) for o in orders)
    return (total / len(orders)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    if not (0 <= pct <= 100):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    pct = Decimal(str(pct))
    result = amount - amount * pct / 100
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_receipt(order):
    return "Order #" + str(order["id"]) + ": $" + str(order["amount"])
```

Note: this assumes `orders.amount` is already a decimal-safe column (e.g. `NUMERIC`/text cents). If the schema itself stores `amount` as `REAL`, that's a data-integrity issue one level up — flag it, since converting to `Decimal` at read time doesn't undo precision already lost at write time.