Twelve issues; four are shipping blockers. The two guaranteed crashes are `format_receipt` (string + int) and `average_order_value` on an empty list — both fire on ordinary input, so this module has almost certainly never been run against real data.

**Critical**

1. **SQL injection in `get_user_orders`.** `user_id` and `status` come from the request and are interpolated into the query string. A `status` of `x' OR '1'='1` dumps every order in the table; `'; DROP TABLE orders; --` is available via `executescript` paths and multi-statement drivers. Fix: parameterized query with `?` placeholders, always. Never format SQL with `%`, `+`, or f-strings.

2. **No authorization check (insecure direct object reference).** `user_id` arrives from the request, so any caller can read any other user's orders by changing one number. Parameterizing the query does not fix this. Fix: the handler must pass the *authenticated* session's user id, or this function must take the authenticated id and compare. This is a policy decision I can't make for you, so the corrected code documents the contract loudly rather than inventing an auth model.

**High**

3. **Connection is never closed.** Every call leaks a `sqlite3.Connection` and its file handle until the garbage collector happens to run. Under load this exhausts file descriptors. Fix: `contextlib.closing`, or hold one long-lived connection. Note the common wrong fix: `with sqlite3.connect(...)` manages the *transaction*, not the connection — it does not close anything.

4. **`average_order_value` divides by zero.** `len(orders) == 0` is the normal case for a new user, and it raises `ZeroDivisionError` straight into the HTTP handler as a 500. Fix: return `None` for an empty list and let the caller decide what to render. Returning `0.0` is a silent lie — zero average and no orders are different facts.

5. **`format_receipt` raises `TypeError` on every call.** `order[0]` is the `id` column, an `INTEGER` from SQLite, and `"Order #" + 1` is not valid Python. Fix: f-string.

6. **`apply_discount` accepts any percentage.** A negative `pct` *increases* the charge; a `pct` over 100 produces a negative amount, which downstream becomes a refund or a free order. If `pct` is user-supplied anywhere in the call chain this is a direct financial exploit. Fix: validate `0 <= pct <= 100` and reject otherwise.

**Medium**

7. **Money is handled as binary floating point.** `total += o[1]` and `amount - amount * pct / 100` both accumulate representation error, and the discount result is never rounded to cents — you get values like `19.999999999999996` written back or charged. Fix: `Decimal`, quantized to two places with `ROUND_HALF_UP`. The real fix one layer down is storing amounts as integer cents; the code below converts at the boundary via `Decimal(str(x))`, which is correct but a workaround for the schema.

8. **`NULL` amounts crash the sum.** If `amount` is nullable, `total += None` raises `TypeError`. Fix: either make the column `NOT NULL` in the schema or skip/raise explicitly. The code below raises, so bad data is loud rather than silently mis-totalled.

9. **`fetchall()` is unbounded.** A user with 200,000 orders loads all of them into memory in one request. Fix: `LIMIT`/`OFFSET` with a server-side cap.

10. **Raw `sqlite3.Error` reaches the handler.** The default traceback can expose the database path and schema in logs or, if the framework echoes errors, in the response. Fix: catch and re-raise as an application-level error; log the detail server-side only.

**Low**

11. **Rows are indexed by position.** `o[1]` and `order[0]` silently return the wrong column the moment someone reorders the `SELECT`. Fix: `conn.row_factory = sqlite3.Row` and index by name.

12. **`status` is not validated and the lookup has no stated index.** An arbitrary status string is a guaranteed empty result rather than a clear 400, and `WHERE user_id = ? AND status = ?` needs a composite index on `(user_id, status)` or it table-scans. Fix: allowlist the status values; add the index in a migration.

```python
"""Order queries, totals, and receipt formatting for the orders service."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterator, Optional, Sequence

ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)
MAX_ROWS = 500
CENTS = Decimal("0.01")


class OrderLookupError(RuntimeError):
    """Database failure. Carries no schema detail; log the cause server-side."""


def _money(value: object) -> Decimal:
    """Convert a stored amount to exact decimal. Raises on NULL or junk."""
    if value is None:
        raise ValueError("order amount is NULL")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"order amount is not numeric: {value!r}") from exc


@contextmanager
def open_connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection that is always closed, with rows addressed by name."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def get_user_orders(
    conn: sqlite3.Connection,
    user_id: int,
    status: str,
    limit: int = MAX_ROWS,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Return one page of a single user's orders in a given status.

    SECURITY: `user_id` must be the id of the *authenticated* caller, taken
    from the session. Passing a request-supplied id lets any user read any
    other user's orders. This function does not and cannot check that.
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id must be an integer") from exc

    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown status: {status!r}")

    limit = max(1, min(int(limit), MAX_ROWS))
    offset = max(0, int(offset))

    try:
        with closing(conn.cursor()) as cur:
            cur.execute(
                """
                SELECT id, amount, status
                FROM orders
                WHERE user_id = ? AND status = ?
                ORDER BY id
                LIMIT ? OFFSET ?
                """,
                (user_id, status, limit, offset),
            )
            return cur.fetchall()
    except sqlite3.Error as exc:
        raise OrderLookupError("order lookup failed") from exc


def get_user_orders_from_path(
    db_path: str, user_id: int, status: str, **kwargs
) -> list[sqlite3.Row]:
    """Convenience wrapper. Prefer passing a shared connection: opening one
    per request costs a file open and loses SQLite's page cache."""
    with open_connection(db_path) as conn:
        return get_user_orders(conn, user_id, status, **kwargs)


def average_order_value(orders: Sequence[sqlite3.Row]) -> Optional[Decimal]:
    """Mean order value, rounded to cents. None when there are no orders."""
    if not orders:
        return None
    total = sum((_money(o["amount"]) for o in orders), Decimal("0"))
    return (total / len(orders)).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Reduce `amount` by `pct` percent, rounded to cents.

    Rejects percentages outside 0-100 so a bad input cannot inflate a charge
    or produce a negative one.
    """
    amount = _money(amount)
    pct = _money(pct)
    if amount < 0:
        raise ValueError("amount must not be negative")
    if not (Decimal("0") <= pct <= Decimal("100")):
        raise ValueError(f"discount percent must be 0-100, got {pct}")
    discounted = amount - (amount * pct / Decimal("100"))
    return discounted.quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: sqlite3.Row) -> str:
    """One receipt line, e.g. 'Order #42: $19.50'."""
    return f"Order #{order['id']}: ${_money(order['amount']):.2f}"
```

Two things the code can't fix on its own: add the composite index on `orders(user_id, status)`, and settle whether `amount` should become integer cents in the schema. And decide who supplies `user_id` — that's issue 2, and it's the one I'd resolve before merging.