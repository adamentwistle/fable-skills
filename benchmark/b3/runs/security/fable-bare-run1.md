Do not ship this. It has one critical hole and three guaranteed runtime crashes, plus a handful of robustness and money-handling problems.

1. **Critical, SQL injection.** The query is built with `%` string formatting from request values. A status of `' OR 1=1 --` returns every customer's orders in the table. Fix: pass values as a parameter tuple with `?` placeholders and never format them into the SQL.

2. **High, broken access control.** The user id comes from the request, so any caller can read another customer's orders by changing the number. Fix belongs in the handler: take the user id from the authenticated session and ignore any user id in the request body or query string.

3. **High, `format_receipt` always crashes.** The id column comes back from SQLite as an int, and adding an int to a string raises TypeError on every call. Fix: use an f-string.

4. **High, `average_order_value` divides by zero.** A user with no orders in the requested status gives an empty list and a ZeroDivisionError. It also fails on generators because it calls `len`. Fix: materialise the input and return None when it is empty.

5. **Medium, connection never closed.** The connection is left to garbage collection, which delays releasing the file lock and leaks handles under load or when an exception is raised. Fix: wrap connection and cursor in `contextlib.closing`. Note that `with conn:` on its own only manages the transaction and does not close.

6. **Medium, money as binary floats.** Totals and discounts use float arithmetic, so results drift and produce values like 8.999999999. Fix: use Decimal throughout and quantize to cents.

7. **Medium, `apply_discount` accepts any percentage.** A negative pct raises the price, a pct over 100 gives a negative total, and nothing rounds to cents. Fix: reject values outside 0 to 100 and quantize the result.

8. **Medium, no input validation.** Even with parameters, an unknown status should fail with a clear error rather than silently return nothing, and the user id should be coerced to int so the handler can return a 400. Fix: allowlist status values, cast user id.

9. **Medium, NULL or non-numeric amounts crash the average.** SQLite does not enforce column types unless the table is STRICT, so a NULL or text amount makes the sum raise TypeError. Fix: convert and validate each amount when reading rows.

10. **Low, unbounded result set.** No LIMIT, so a customer with many orders loads everything into memory. Fix: add a bounded LIMIT and page.

11. **Low, positional tuple access.** Indexing by position means a reordered SELECT silently breaks every consumer. Fix: return a NamedTuple.

12. **Low, receipt amount formatting.** `str()` on a float prints `$9.5` and can print scientific notation. Fix: format with two decimal places.

13. **Low, connection hygiene.** A fresh writable connection is opened per call for a read-only query, and raw sqlite3 errors propagate to the handler. Consider a read-only URI, connection reuse if throughput matters, and mapping `sqlite3.Error` to a 500 without echoing the query.

14. **Low, no type hints or docstrings.** Nothing states that amount is a float, that orders are tuples, or what the function returns.

Assumptions in the corrected code: the status set is a placeholder, replace it with your real values. The amount column holds currency units, not cents. The user id column is INTEGER.

```python
import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, NamedTuple, Optional

# Replace with the real set of order statuses.
VALID_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled"})
MAX_ORDERS = 1000
CENT = Decimal("0.01")


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def _to_money(value) -> Decimal:
    if value is None:
        raise ValueError("order amount is NULL")
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except ArithmeticError as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def get_user_orders(db_path: str, user_id: int, status: str,
                    limit: int = MAX_ORDERS) -> list[Order]:
    """Return up to `limit` orders for `user_id` with the given status.

    `user_id` must come from the authenticated session, never from the request.
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    if not 1 <= limit <= MAX_ORDERS:
        raise ValueError(f"limit must be between 1 and {MAX_ORDERS}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ?"
    )
    with closing(sqlite3.connect(db_path, timeout=5.0)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(query, (user_id, status, limit))
            rows = cur.fetchall()
    return [Order(id=r[0], amount=_to_money(r[1]), status=r[2]) for r in rows]


def average_order_value(orders: Iterable[Order]) -> Optional[Decimal]:
    """Mean order amount, or None if there are no orders."""
    orders = list(orders)
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / len(orders)).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct) -> Decimal:
    """Apply a percentage discount between 0 and 100, rounded to cents."""
    amount = _to_money(amount)
    pct = Decimal(str(pct))
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError("pct must be between 0 and 100")
    return (amount - amount * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```