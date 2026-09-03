Twelve issues, three of which will fail on the first real request.

1. **Critical, SQL injection.** `user_id` and `status` are pasted into the query with `%` formatting, and both come from the request. A `status` of `' OR '1'='1` dumps every order in the table. A benign apostrophe also breaks the query. Fix: bind with `?` placeholders and pass a tuple.

2. **High, `format_receipt` crashes on every row.** `"Order #" + order[0]` adds a string to an integer `id`, which raises `TypeError`. Fix: use an f-string.

3. **High, `average_order_value` raises on an empty list.** A user with no orders in that status is the normal case, and it produces `ZeroDivisionError`, so the handler returns 500. Fix: return `None` for empty input and let the handler render it.

4. **High, connection leak.** The connection and cursor are never closed, and an exception in `execute` leaks them. Note that `with sqlite3.connect(...)` only commits or rolls back; it does not close. Fix: wrap in `contextlib.closing`.

5. **High, missing ownership check (fix in the handler).** Any caller can read any user's orders by changing `user_id`. The id should come from the authenticated session, not the request, or the handler must verify the match.

6. **Medium, float arithmetic for money.** Totals, averages and discounts accumulate binary rounding error and are never rounded to cents. `apply_discount(19.99, 10)` returns `17.991`. Fix: convert to `Decimal` at the DB boundary and quantize to cents. Store amounts as integer cents or TEXT in the schema, not REAL.

7. **Medium, `apply_discount` accepts anything.** A negative or over-100 `pct` inflates the price or makes it negative, and a string `pct` raises deep inside. Fix: validate `0 <= pct <= 100` and `amount >= 0`.

8. **Medium, no input validation after parameterization.** `status` should be checked against an allowlist, and `user_id` coerced to `int`, so garbage fails fast with a 400 instead of a silent empty result or a 500.

9. **Medium, NULL `amount` crashes the average.** If the column is nullable, `0.0 + None` raises `TypeError`. Fix: make the column `NOT NULL` and fail loudly in the conversion so bad data is not silently averaged.

10. **Low, positional tuple indexing.** `o[1]` and `order[0]` are coupled to the column order in the SELECT. Reordering the query breaks callers silently. Fix: return a small dataclass.

11. **Low, receipt money formatting.** `str(order[1])` prints `5.0` or `17.991`, not `$5.00`. Fix: format with two decimals.

12. **Low, unbounded `fetchall`.** A user with many orders loads them all into memory. Add pagination in the handler and pass a limit and offset through; I have not added a default limit below because a hidden default silently truncates results.

Corrected code. Callers that index rows as tuples must switch to the attributes on `Order`.

```python
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

ALLOWED_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled"})
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _to_money(value) -> Decimal:
    if value is None:
        raise ValueError("order amount is NULL")
    # str() first so a REAL 19.99 becomes Decimal("19.99"), not 19.98999...
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def get_user_orders(db_path: str, user_id, status: str) -> list[Order]:
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer") from None
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id"
    )
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(query, (user_id, status)).fetchall()
    return [Order(id=r[0], amount=_to_money(r[1]), status=r[2]) for r in rows]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / len(orders)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct) -> Decimal:
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if amount < 0:
        raise ValueError("amount must not be negative")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    return (amount - amount * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```

The `ValueError`s from validation should map to HTTP 400 in the handler. Everything else that escapes is a 500.