Fifteen-line module, twelve issues. The first four alone mean it must not ship as is.

1. **Critical, SQL injection.** Both `user_id` and `status` are pasted into the SQL string with `%`. A user_id of `1' OR '1'='1` returns every user's orders. A `UNION SELECT` in status reads any table. Stacked statements fail in sqlite3's `execute`, but data exfiltration and blind probing work fine. Fix: `?` placeholders with a parameter tuple.

2. **High, no authorization check.** The user_id comes straight from the request. Nothing ties it to the authenticated caller, so any logged-in user can read any other user's orders. This module cannot fix it alone. The handler must pass the authenticated principal's id, or verify the caller may view the requested one. Flag to whoever owns the handler.

3. **High, connection leak.** `conn` and `cur` are never closed. Every request leaks a file handle and a SQLite lock. Under load this becomes "too many open files" or "database is locked". Fix: wrap the connection in `contextlib.closing`. Note that `with conn:` alone only commits or rolls back. It does not close.

4. **High, `format_receipt` crashes on every call.** `order[0]` is an integer id from the database. `"Order #" + int` raises `TypeError`. Fix: f-string.

5. **High, `average_order_value` divides by zero.** An empty list raises `ZeroDivisionError`. A user with no orders in a given status is the normal case, not an edge case. Fix: guard the empty case and raise a clear `ValueError`, or return `None`. The caller decides how to render "no orders".

6. **Medium, money as float.** Totals accumulate in a float, and `str(order[1])` prints `12.5` or `12.300000000000001`. Discount math compounds the rounding error. Fix: use `Decimal` and quantize to cents. Longer term, store integer cents in the database.

7. **Medium, `apply_discount` has no bounds.** A negative pct raises the price. A pct over 100 returns a negative amount. A string pct from the request raises `TypeError` deep in the call. Fix: validate 0 to 100 and a non-negative amount, coerce to `Decimal`.

8. **Medium, no validation of `status` or `user_id`.** Once parameterized, any status string is accepted and silently returns zero rows, including case mismatches like `Shipped`. A non-numeric user_id also silently returns nothing. Fix: allowlist statuses, require a positive int user_id, and have the handler return 400 on `ValueError`.

9. **Medium, positional tuple coupling.** `o[1]`, `order[0]` and `order[1]` depend on the SELECT column order. Reordering the SELECT silently breaks the math and receipts. Fix: map rows to a dataclass.

10. **Medium, unbounded `fetchall`.** No `LIMIT` and no `ORDER BY`. A heavy user pulls their whole history into memory, and results are not deterministically ordered. Fix: cap with `LIMIT` and order by id.

11. **Low, raw `sqlite3.Error` reaches the HTTP layer.** Depending on the handler, schema details leak in 500 responses. Fix: catch at the handler boundary, log, return a generic error.

12. **Low, one connection per call and no type hints.** Fine for SQLite at low volume. Add hints so the int-versus-string bugs above are caught by a type checker.

```python
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

VALID_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled"})
MAX_ORDERS = 500
CENTS = Decimal("0.01")


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _money(value) -> Decimal:
    # str() first so a REAL column does not drag its binary float noise into Decimal.
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def get_user_orders(db_path: str, user_id: int, status: str,
                    limit: int = MAX_ORDERS) -> list[Order]:
    """Caller MUST have already verified the authenticated principal may view user_id."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}")
    if not 1 <= limit <= MAX_ORDERS:
        raise ValueError(f"limit must be between 1 and {MAX_ORDERS}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ?"
    )
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.execute(query, (user_id, status, limit))) as cur:
            return [Order(id=r[0], amount=_money(r[1]), status=r[2]) for r in cur.fetchall()]


def average_order_value(orders: Sequence[Order]) -> Decimal:
    if not orders:
        raise ValueError("cannot average an empty list of orders")
    total = sum((o.amount for o in orders), Decimal("0"))
    return _money(total / len(orders))


def apply_discount(amount, pct) -> Decimal:
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError("pct must be between 0 and 100")
    return _money(amount - amount * pct / Decimal(100))


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```

The handler still has to do three things this module cannot: convert the request's user_id with `int()` and map `ValueError` to a 400, enforce that the caller is allowed to see that user's orders, and catch `sqlite3.Error` so database internals stay out of responses.