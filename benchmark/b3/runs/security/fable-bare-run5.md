**1. SQL injection in `get_user_orders` — critical.** Both request values are spliced into the query with `%`. A `status` of `x' OR '1'='1` returns every user's orders, and a `UNION SELECT` reads any table. Stacked statements are blocked by sqlite3's one-statement rule, so this is data exposure rather than destruction, but it is still a full read of the database. Any legitimate value containing a quote also crashes with a syntax error. Fix: bind with `?` placeholders.

**2. `format_receipt` crashes on every call — high.** `"Order #" + order[0]` adds a string to an integer id and raises `TypeError`. Fix: use an f-string.

**3. `average_order_value` divides by zero — high.** A user with no orders, or none in the requested status, is the normal case and raises `ZeroDivisionError`. Fix: return `None` (or a documented sentinel) when the list is empty.

**4. `apply_discount` accepts any percentage — high.** Negative `pct` raises the price. `pct` over 100 gives a negative amount, which is a refund. Nothing rejects a negative `amount` either. Fix: validate `0 <= pct <= 100` and `amount >= 0`, raise `ValueError` otherwise.

**5. Float arithmetic on money — medium.** `total = 0.0`, `amount * pct / 100`, and `str(order[1])` all use binary floats. Sums drift by fractions of a cent, `apply_discount(19.99, 15)` yields `16.9915` with no rounding, and receipts print `$12.5` or `$12.300000000000001`. Fix: use `Decimal`, quantize to two places with `ROUND_HALF_UP`, and format with `:.2f`. Longer term, store amounts as integer cents.

**6. Connection never closed — medium.** `conn` is opened and abandoned, and any exception after `connect` leaks it. Under an HTTP handler this exhausts file handles. Fix: wrap in `contextlib.closing`. Note that `with sqlite3.connect(...)` alone only manages transactions, not closing.

**7. No input validation — medium.** `status` should be checked against the known set of statuses, and `user_id` coerced to `int`. Parameter binding stops injection, but unvalidated values still produce silent empty results or type-mismatch queries.

**8. NULL or text `amount` breaks the maths — medium.** SQLite does not enforce column types. A NULL or `"12.50"` in `amount` raises `TypeError` inside `average_order_value`. Fix: coerce every amount through one conversion helper that rejects NULL.

**9. Positional tuple coupling — low.** Three functions depend on the column order of one query. Reordering the `SELECT` silently breaks them. Fix: `sqlite3.Row` and a small `Order` dataclass.

**10. Unbounded result set — low.** No `LIMIT`, so a heavy account pulls its entire history into memory per request. Fix: add a `LIMIT` with a bound parameter and an `ORDER BY`.

**11. Read-write connection for a read-only query — low.** Open with `mode=ro` via a URI so a future bug cannot write. Left out of the code below because URI paths need forward slashes on Windows.

**12. No type hints or docstrings — low.** Added in the corrected code.

```python
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

VALID_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled"})
CENTS = Decimal("0.01")


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _to_money(value) -> Decimal:
    """Convert a DB value to a two-place Decimal. Rejects NULL."""
    if value is None:
        raise ValueError("amount is NULL")
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def get_user_orders(db_path: str, user_id, status: str, limit: int = 1000) -> list[Order]:
    """Return up to `limit` orders for one user in one status. Raises ValueError on bad input."""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer") from None
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status: {status!r}")

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, amount, status FROM orders "
            "WHERE user_id = ? AND status = ? ORDER BY id LIMIT ?",
            (user_id, status, limit),
        ).fetchall()
    return [Order(id=r["id"], amount=_to_money(r["amount"]), status=r["status"]) for r in rows]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, or None when there are no orders."""
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / len(orders)).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct) -> Decimal:
    """Apply a percentage discount in [0, 100] to a non-negative amount."""
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not (0 <= pct <= 100):
        raise ValueError("pct must be between 0 and 100")
    return (amount - amount * pct / 100).quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```

The one behaviour change to confirm with the handler: `average_order_value` now returns `None` for an empty list instead of raising, and `get_user_orders` raises `ValueError` on bad input, which the handler should map to a 400.