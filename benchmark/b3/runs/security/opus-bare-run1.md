## Issues

**1. SQL injection — critical.** `get_user_orders` builds the query with `%` string formatting, so `user_id` and `status` land in the SQL text verbatim. Both come from the request. A `status` of `x' OR '1'='1` returns every user's orders; `x'; DROP TABLE orders--` is blocked only by `execute`'s single-statement rule, and `executescript` or a stacked-statement driver would not block it. Fix: parameterized query with `?` placeholders. Never format user data into SQL, even after escaping.

**2. Quoting bug even without an attacker — high.** The same formatting breaks on any legitimate value containing an apostrophe. Parameterization fixes this too.

**3. No authorization check — critical (outside this module, but it ships with it).** `user_id` comes from the request, and nothing here ties it to the authenticated session. If the handler passes the client-supplied id through, any user reads any other user's orders. Fix: derive `user_id` from the session, or assert `session_user_id == user_id` before calling.

**4. Connection is never closed — high.** `get_user_orders` opens a connection and returns without closing it, and leaks it outright if `execute` raises. Under HTTP load this exhausts file handles. Fix: `with contextlib.closing(...)`, or better, take a connection from the caller so the service can pool it.

**5. `format_receipt` raises TypeError on every call — high.** `order[0]` is the `id` column, an `int` from SQLite, and `"Order #" + int` is a TypeError. This is a guaranteed crash, not an edge case. Fix: f-string.

**6. `average_order_value` divides by zero — high.** A user with no orders matching the status gives `len(orders) == 0` and a `ZeroDivisionError` propagating to the handler as a 500. Fix: return `Decimal("0.00")` (or `None`) for an empty list; decide which explicitly, since "no orders" and "average of zero" are different facts.

**7. `amount` may be NULL — medium.** If the column is nullable, `total += None` is a TypeError. Fix: filter or coerce nulls, and ideally add `NOT NULL` to the schema.

**8. Money handled as binary floats — medium, data integrity.** `total`, `apply_discount`, and the average all use float arithmetic. `0.1 + 0.2` is not `0.3`, and errors accumulate across a receipt or a report. Fix: `Decimal`, converted from strings, not from floats. The durable fix is storing money as integer minor units (cents) in the database.

**9. `apply_discount` does not validate `pct` — medium.** A negative percent increases the charge; a percent over 100 returns a negative amount and turns a charge into a refund. Fix: reject anything outside 0–100, and reject negative `amount`.

**10. Discounts are not rounded — medium.** `apply_discount(19.99, 33)` returns `13.3933`, a fraction of a cent that will differ from whatever the payment processor charges. Fix: quantize to two places with an explicit rounding mode (`ROUND_HALF_UP` is the usual commercial choice).

**11. Unbounded `fetchall` — medium.** A user with a large order history loads the whole result set into memory in one request. Fix: `LIMIT`/`OFFSET` with a maximum page size, or iterate the cursor.

**12. `status` is not validated — medium.** Even parameterized, an arbitrary string is passed to the database on every request. Validating against a known set moves the rejection to the edge, keeps the query planner honest, and catches client bugs. Same for `user_id`: coerce to `int` and reject otherwise.

**13. No error handling — medium.** `sqlite3.Error` from connect or execute escapes raw to the handler, and SQLite error text can disclose schema details in a response body. Fix: catch and re-raise as a service-level error; log the detail, return a generic message.

**14. Positional tuple indexing everywhere — low.** `o[1]` and `order[0]` silently read the wrong column the moment the `SELECT` list changes. Fix: `sqlite3.Row` or a `NamedTuple`.

**15. New connection per call — low.** Connecting per request is wasteful and prevents WAL/pragma tuning. Rolled into the fix for issue 4.

**16. No type hints or docstrings — low.**

## Corrected code

```python
"""Order lookup and money helpers for the orders service."""

from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import NamedTuple, Sequence

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = frozenset({"pending", "paid", "shipped", "cancelled", "refunded"})
MAX_PAGE_SIZE = 200
CENTS = Decimal("0.01")


class OrderError(Exception):
    """Service-level failure; safe to surface to the caller."""


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def to_money(value: object) -> Decimal:
    """Convert a stored amount to an exact 2dp Decimal.

    Goes through str() so a float column does not carry its binary
    representation error into the Decimal.
    """
    try:
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OrderError("invalid amount in orders table") from exc


def get_user_orders(
    conn: sqlite3.Connection,
    user_id: int,
    status: str,
    limit: int = MAX_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a user's orders with the given status.

    Takes an open connection so the caller controls pooling and lifetime.
    The caller MUST have already checked that the authenticated principal
    is allowed to read `user_id`; this function does not authorize.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise OrderError("user_id must be an integer")
    if status not in ALLOWED_STATUSES:
        raise OrderError("unknown status")
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    sql = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )
    try:
        cur = conn.execute(sql, (user_id, status, limit, offset))
        rows = cur.fetchall()
    except sqlite3.Error:
        logger.exception("order lookup failed for user_id=%s", user_id)
        raise OrderError("could not load orders") from None
    finally:
        try:
            cur.close()
        except (NameError, sqlite3.Error):
            pass

    return [
        Order(id=int(r[0]), amount=to_money(r[1] if r[1] is not None else 0), status=r[2])
        for r in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Decimal | None:
    """Mean order value, or None when there are no orders.

    None rather than 0.00 so callers can tell "no data" from "averaged to zero".
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Reduce `amount` by `pct` percent, rounded to whole cents."""
    amount = to_money(amount)
    pct = Decimal(str(pct))
    if amount < 0:
        raise OrderError("amount must not be negative")
    if not (Decimal("0") <= pct <= Decimal("100")):
        raise OrderError("pct must be between 0 and 100")
    discounted = amount - (amount * pct / Decimal("100"))
    return discounted.quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${order.amount:.2f}"
```

Two follow-ups worth doing outside this file: add a `NOT NULL` constraint on `orders.amount`, and move money to integer cents so `to_money` stops being a conversion layer over a lossy column.