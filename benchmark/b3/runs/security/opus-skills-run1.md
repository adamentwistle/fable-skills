SQL injection in `get_user_orders` is the headline: `user_id` and `status` come straight from the request into a string-formatted query, so `status = "x' OR '1'='1"` returns every order in the table and a stacked statement can drop it. Close behind is that nothing checks the caller is allowed to read the `user_id` they asked for.

## Findings

**Critical**

1. **SQL injection** (`get_user_orders`, the `%` query build). Request-controlled `user_id` and `status` are interpolated into SQL. Fix: parameterised query with `?` placeholders and a values tuple. Never build SQL by concatenation or `%`/f-string.

2. **Missing authorisation — insecure direct object reference.** `user_id` arrives from the HTTP request and is used as-is, so anyone can read anyone's orders by changing a number. Fix: derive `user_id` from the authenticated session, or pass the session's user and check ownership before querying. The function cannot tell the two apart, so it must document the requirement and the handler must honour it. This is the one fix that has to happen in the caller as well.

**High**

3. **`ZeroDivisionError` on an empty list** (`average_order_value`, `total / len(orders)`). A user with no matching orders is normal, so this is a 500 on ordinary input. Fix: return `None` for an empty list, and make that the documented contract so callers handle "no average" explicitly.

4. **`format_receipt` raises `TypeError` on every real row.** `"Order #" + order[0]` concatenates a str with an int, and `id` from an `INTEGER PRIMARY KEY` is an int. Fix: f-string.

5. **Money held in binary floats with no rounding policy.** `total = 0.0`, `amount * pct / 100`, and the division in the average all accumulate representation error, and nothing ever rounds to cents. `apply_discount(10.0, 15)` returns `8.5`, but `apply_discount(0.7, 5)` returns `0.6649999999999999`. Fix: `Decimal` (or integer minor units) throughout, with an explicit `ROUND_HALF_UP` quantise to cents applied once at the boundary. Long term the `amount` column should be integer cents, not `REAL`.

6. **`apply_discount` validates nothing.** `pct=-50` raises the price 50%, `pct=150` produces a negative total that will refund money, and `pct=0.15` silently means 0.15% rather than 15%. Fix: require `0 <= pct <= 100`, reject anything else with a message naming the value, and document that the unit is percentage points.

7. **Connection and cursor are never closed.** No `close()`, no context manager, no `try/finally`; an exception mid-query leaks the handle. Fix: `contextlib.closing` around both, and a connection timeout so a locked database fails fast instead of hanging the request thread.

**Medium**

8. **Unbounded result set and unspecified order.** No `LIMIT`, no `ORDER BY`. A user with 500k orders loads them all into memory; and without `ORDER BY` any pagination added later silently returns overlapping pages. Fix: `ORDER BY id`, mandatory `limit`/`offset` with a server-side maximum.

9. **Raw database exceptions escape to the handler.** `sqlite3.OperationalError: no such table: orders` reaching a 500 body leaks the schema and `db_path`. Fix: catch `sqlite3.Error`, log the detail with a stack trace, raise a domain error with a safe message, and chain the cause with `from exc`.

10. **`status` is not allowlisted.** Even parameterised, it should be checked against a fixed server-side set so a typo fails loudly instead of quietly returning zero rows. Fix: `frozenset` of valid statuses, rejected at the boundary.

11. **A `NULL` or non-numeric `amount` crashes with a bare `TypeError`.** `total += o[1]` on `None` gives `unsupported operand type(s)`, naming no order. Fix: convert amounts through one helper that raises a message naming the offending value.

12. **`str(order[1])` is not money formatting.** Produces `$12.3` or `$12.300000000000001`. Fix: quantise to two decimal places when formatting.

13. **`user_id` type is never coerced.** SQLite's affinity rules paper over the string/int mismatch here, but that is luck, not design, and it breaks on a port to Postgres. Fix: coerce to `int` and reject non-integers.

14. **Positional tuple indexing spreads through the module.** `o[1]`, `order[0]`, `order[1]` — adding a column to the `SELECT` breaks all three functions silently. Fix: return a `NamedTuple` (or `sqlite3.Row`) so fields are named.

15. **No logging at all.** When this fails in production there is no record of which user or status was involved. Fix: one `logger.exception` on the query failure path carrying `user_id` and `status` — no `db_path`, no credentials.

**Low**

16. **Currency hardcoded as `$`** with no currency code on the order. Fine for a single-market service; a bug the day it isn't.

17. **No escaping in `format_receipt`.** Harmless as plain text, an XSS if this string is ever interpolated into HTML. Escape at the rendering sink, not here — worth a note so nobody drops it into a template raw.

18. **`db_path` is unvalidated.** It is a caller-supplied argument today. If it ever becomes request-influenced, that is arbitrary file access. Keep it a fixed configuration value.

19. **A fresh connection per call, no pooling and no `timeout`.** Under load this is slow and prone to `database is locked`. Fix at minimum: pass `timeout`; better: reuse a per-thread connection.

20. **No type hints, docstrings, or tests.** In particular there is no test covering the empty-orders case, which is finding 3.

## Process notes

- **To confirm before merge:** run the injection case against a scratch database — call `get_user_orders(db, 1, "x' OR '1'='1")` on the current code and confirm it returns other users' rows, then confirm the fixed version raises `ValueError`. Also call `average_order_value([])` and `format_receipt((1, 10.0, "paid"))` on the current code to see the two crashes.
- **I did not execute any of this**, original or replacement — no schema and no database were available, and the task said not to edit files. Every claim above is from reading the code; the specific float values quoted (`0.6649999999999999`) and the error text in the replacement are as written, not as observed at a prompt.
- **Unverified:** the `orders` schema. I assume `id` is an integer primary key and `amount` is `REAL`; if `amount` is already integer cents, drop the `Decimal` conversion and work in cents directly. I also could not check the callers of these four functions, so the changed return types (`NamedTuple` instead of tuple, `None` instead of a number from `average_order_value`, `Decimal` instead of `float`) need a grep across the service before merging.

## Corrected code

```python
"""Order queries and money helpers for the orders service.

Amounts are handled as Decimal, never binary float. The `amount` column is
assumed to be REAL for now; it should be migrated to integer minor units.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import NamedTuple, Optional, Sequence

logger = logging.getLogger(__name__)

# Server-side allowlist. Anything not in here is rejected at the boundary
# rather than handed to the database.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

MAX_PAGE_SIZE = 200
CENTS = Decimal("0.01")


class OrderLookupError(Exception):
    """The orders query failed. Message is safe to show a user."""


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def _to_amount(value, *, field: str = "amount") -> Decimal:
    """Convert a stored or supplied money value to Decimal.

    Goes via str() so a float never contributes its binary expansion.
    """
    if value is None:
        raise ValueError(f"{field} is missing (NULL)")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{field} is not a number: {value!r}") from exc


def get_user_orders(
    db_path: str,
    user_id: int,
    status: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a single user's orders, oldest first.

    SECURITY: `user_id` must be derived from the authenticated session, or
    checked against it by the caller before this is called. This function
    performs no ownership check and cannot tell a session-derived id from
    one typed into a query string.

    Raises ValueError for bad input, OrderLookupError if the query fails.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, (int, str)):
        raise ValueError(f"user_id must be an integer, got {user_id!r}")
    try:
        user_id = int(user_id)
    except ValueError as exc:
        raise ValueError(f"user_id must be an integer, got {user_id!r}") from exc

    if status not in ALLOWED_STATUSES:
        raise ValueError(
            "unknown order status %r; allowed: %s"
            % (status, ", ".join(sorted(ALLOWED_STATUSES)))
        )

    if not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(
            f"limit must be an integer in 1..{MAX_PAGE_SIZE}, got {limit!r}"
        )
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"offset must be a non-negative integer, got {offset!r}")

    # ORDER BY is required for stable pagination, not cosmetic.
    sql = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )

    try:
        with closing(sqlite3.connect(db_path, timeout=5.0)) as conn:
            with closing(conn.cursor()) as cur:
                cur.execute(sql, (user_id, status, limit, offset))
                rows = cur.fetchall()
    except sqlite3.Error as exc:
        # Detail goes to the log; the caller gets a message with no schema
        # or file path in it.
        logger.exception(
            "orders query failed: user_id=%s status=%s limit=%s offset=%s",
            user_id,
            status,
            limit,
            offset,
        )
        raise OrderLookupError("could not load orders") from exc

    return [
        Order(id=row[0], amount=_to_amount(row[1]), status=row[2]) for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, rounded half-up to cents.

    Returns None when there are no orders: an empty list is a normal result,
    not an error, and there is no meaningful average to report.
    """
    if not orders:
        return None
    total = sum((_to_amount(o.amount) for o in orders), Decimal(0))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount, discount_pct) -> Decimal:
    """Apply a percentage discount and round half-up to cents.

    `discount_pct` is in percentage points: 15 means 15%, not 1500% and not
    0.15%. Rounding happens once, here, on the discount rather than on the
    running total.
    """
    amount = _to_amount(amount, field="amount")
    pct = _to_amount(discount_pct, field="discount_pct")

    if amount < 0:
        raise ValueError(f"amount must not be negative, got {amount}")
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError(
            f"discount_pct must be between 0 and 100, got {discount_pct!r}"
        )

    discount = (amount * pct / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)
    # Rounding can push the discount a fraction of a cent past an amount that
    # carries sub-cent precision; never return a negative total.
    return max(Decimal(0), amount - discount)


def format_receipt(order: Order) -> str:
    """One receipt line. Plain text — escape at the sink if rendered as HTML."""
    amount = _to_amount(order.amount).quantize(CENTS, rounding=ROUND_HALF_UP)
    return f"Order #{order.id}: ${amount}"
```