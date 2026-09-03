The module has one critical injection bug, and as written it crashes on its own output: `format_receipt` raises `TypeError` for every row `get_user_orders` returns. Issues, most severe first.

1. **SQL injection. Critical.** `user_id` and `status` come from the request and are spliced into the query with `%`. A status of `' OR '1'='1` returns every user's orders. A `'` in either value also crashes the query. Fix: parameterized query with `?` placeholders, plus an allowlist for `status` and an `int()` coercion for `user_id`.

2. **`format_receipt` crashes on real rows. High.** The `id` column is an integer, and `"Order #" + order[0]` raises `TypeError` because Python will not concatenate `str` and `int`. Fix: f-string.

3. **Division by zero. High.** `average_order_value([])` raises `ZeroDivisionError`. A user with no orders in that status is the common case, not the edge case. Fix: count while iterating and return `None` for zero orders. Returning `0.0` would look like a real average in a dashboard, so it is the wrong default.

4. **Connection leak. High.** The connection is never closed, and an exception in `execute` leaks it too. Note that `with sqlite3.connect(...) as conn` only commits or rolls back, it does not close. Fix: `contextlib.closing` or try/finally.

5. **Authorization boundary. High, but in the caller.** The function will happily return any user's orders for any `user_id` it is given. If the HTTP handler passes `user_id` from the request rather than from the authenticated session, that is an insecure direct object reference. The fix belongs in the handler: derive `user_id` from the session, never from the request.

6. **Wrong path silently creates an empty database. Medium.** `sqlite3.connect` creates the file if it does not exist. A bad deploy config produces an empty DB and every user sees zero orders, with no error. Fix: open with a `file:` URI and `mode=ro` so a missing file raises `OperationalError`.

7. **Money as float. Medium.** `total = 0.0` accumulates binary rounding error, and `apply_discount` compounds it. Fix: `Decimal`, quantized to cents. The real fix is storing integer cents in the schema.

8. **`apply_discount` accepts anything. Medium.** A negative `pct` raises the price. `pct > 100` produces a negative amount. A string `pct` from a request gives a `TypeError` or, for an integer amount, string repetition followed by a crash. Fix: coerce to `Decimal` and reject values outside 0 to 100.

9. **Positional tuple coupling. Medium.** `o[1]` and `order[0]` depend on the SELECT column order. Reorder the SELECT and `average_order_value` silently averages ids. Fix: return a small dataclass and use field names.

10. **NULL amount crashes the average. Medium.** A NULL `amount` becomes `None` and `total += None` raises `TypeError`. Fix: reject it explicitly when building the row, or add `NOT NULL` to the schema.

11. **`user_id` type relies on SQLite affinity. Medium.** The query compares an integer column to a quoted string. It works only because SQLite coerces text to the column's affinity. Fix: coerce to `int` before the query and pass it as an integer parameter.

12. **Unbounded, unordered result. Low.** `fetchall` with no `LIMIT` loads every matching row, and with no `ORDER BY` the order is not guaranteed. Fix: add both.

13. **Receipt amount formatting. Low.** `str(order[1])` prints `$12.300000000000001` or `$5.0`. Fix: format to two decimals.

14. **`len(orders)` fails on iterators. Low.** Passing a generator to `average_order_value` raises `TypeError`. Counting during the loop fixes this for free.

Corrected code:

```python
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

# Must match the real set of status values in the orders table.
VALID_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled"})
CENT = Decimal("0.01")
MAX_ROWS = 1000


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _decimal(value, what: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{what} must be a number")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{what} must be a number") from None


def _money(value, what: str = "amount") -> Decimal:
    return _decimal(value, what).quantize(CENT, rounding=ROUND_HALF_UP)


def get_user_orders(db_path: str, user_id, status: str, limit: int = MAX_ROWS) -> list[Order]:
    # user_id must already be the authenticated user's id, set by the handler
    # from the session, not taken from the request.
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer") from None
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    if not 1 <= limit <= MAX_ROWS:
        raise ValueError(f"limit must be between 1 and {MAX_ROWS}")

    # mode=ro fails loudly on a missing file instead of creating an empty database.
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5)) as conn:
        rows = conn.execute(
            "SELECT id, amount, status FROM orders "
            "WHERE user_id = ? AND status = ? "
            "ORDER BY id LIMIT ?",
            (user_id, status, limit),
        ).fetchall()

    return [Order(id=r[0], amount=_money(r[1]), status=r[2]) for r in rows]


def average_order_value(orders: Iterable[Order]) -> Optional[Decimal]:
    total = Decimal(0)
    count = 0
    for o in orders:
        total += o.amount
        count += 1
    if count == 0:
        return None
    return (total / count).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct) -> Decimal:
    amount = _money(amount)
    pct = _decimal(pct, "pct")
    if not 0 <= pct <= 100:
        raise ValueError("pct must be between 0 and 100")
    return (amount - amount * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```

Two decisions to confirm before shipping: the `VALID_STATUSES` set must match the database, and `average_order_value` now returns `None` for no orders rather than raising, so callers must handle that.