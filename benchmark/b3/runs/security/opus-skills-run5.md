I could not run anything — the Bash tool is disabled in this session, so every claim below comes from reading the code, not from an observed execution. The exact commands to confirm are at the end.

## Findings

**1. SQL injection — critical.** `status` (and `user_id`) come straight from the HTTP request and are interpolated into the query string with `%`. A `status` of `paid' OR '1'='1` returns every order in the table; `'; DROP TABLE orders; --` is blocked only by `execute` refusing multiple statements, which is not a security control. Fix: parameterized query with `?` placeholders, plus an allowlist check on `status`.

**2. No authorization check — critical.** `user_id` is taken from the request. Even after fixing the injection, any caller can read any other customer's orders by changing one number. This is the bug that survives the "fix the SQL" pass. Fix: the handler must derive `user_id` from the authenticated session and never from a query parameter or body field; the function should document that contract and reject anything that isn't an `int`.

**3. `average_order_value` crashes on an empty list — high.** `total / len(orders)` raises `ZeroDivisionError` whenever a user has no orders in that status, which is a routine case, not an exceptional one. Fix: return `None` for an empty sequence (a distinct "no data" value, not `0.0`, which reads as "average of zero").

**4. Money is handled as binary floats throughout — high.** `total += o[1]`, the discount arithmetic, and `str(order[1])` all use `float`. Repeated addition drifts, and cents are not exactly representable, so totals and receipts will disagree by fractions of a cent and eventually by a visible cent. Fix: `decimal.Decimal` everywhere, converted at the database boundary. Separately, if `orders.amount` is a `REAL` column, that is a schema-level data-integrity bug — migrate it to `INTEGER` minor units or `TEXT`.

**5. `apply_discount` accepts any percentage — high.** `pct = 150` returns a negative amount (you now owe the customer money); `pct = -50` is a 50% *surcharge* silently applied through a function named "discount". Neither is rejected. Fix: validate `0 <= pct <= 100` and reject a negative `amount`.

**6. `apply_discount` has no rounding policy — high.** `19.99` at 15% gives `16.9915`, which is not a price. Rounding is a decision, not a default. Fix: round the discount half-up to the cent, then subtract, and say so in a comment so the next reader doesn't change it casually.

**7. `format_receipt` raises `TypeError` on every call — high.** `"Order #" + order[0]` concatenates a `str` to the `id` column, which is an integer. This is a guaranteed crash on the first receipt, not an edge case. Fix: f-string.

**8. Receipt amount is unformatted — medium.** `str(12.3)` renders `$12.3`, and a float that has drifted renders `$12.300000000000001`. Fix: format to exactly two decimal places.

**9. The database connection is never closed — medium.** No `try/finally`, no context manager, and on any exception the connection leaks. Note that `with sqlite3.connect(...)` does *not* close the connection — it only commits or rolls back — so the fix is `contextlib.closing`.

**10. Unbounded result set — medium.** `fetchall()` with no `LIMIT` loads a customer's entire order history into memory; a bulk account can exhaust the process. There is also no `ORDER BY`, so "page" boundaries would be undefined. Fix: `ORDER BY id` with a `LIMIT`/`OFFSET` and a hard server-side cap.

**11. No error handling around the query — medium.** A `sqlite3.OperationalError` propagates to the HTTP layer with its message intact, which can leak the schema or the database path to the client. Fix: catch `sqlite3.Error`, log it with the identifiers needed to debug, and raise a wrapped exception carrying a safe message, chained with `from exc` so the cause survives.

**12. Rows are returned as bare tuples — medium.** `o[1]` and `order[0]` couple three functions to the column order in one `SELECT`. Adding a column to that query silently changes what "the amount" means, and nothing fails loudly. Fix: return a typed record.

**13. A NULL `amount` is not handled — medium.** `total += None` raises `TypeError` inside the averaging loop, far from the cause. Fix: reject it at the boundary with the offending order id in the message, since a NULL amount is a data-integrity fault worth surfacing.

**14. `db_path` is unvalidated — low here, critical if it ever moves.** It is a trusted argument today. If a caller ever wires it to request data, `sqlite3.connect` will happily create or open an arbitrary file. Worth a comment, and worth opening read-only on a read path.

**15. No connection timeout — low.** The default 5-second busy timeout is implicit; state it, so a lock contention change doesn't become a mystery hang.

**16. Currency is hardcoded to `$` — low.** Fine for one market, a bug the day a second currency exists.

## Corrected code

```python
"""Order lookups and receipt formatting for the orders service.

Money contract: amounts are ``Decimal`` values in major units, e.g.
``Decimal("12.34")`` is $12.34.  Amounts are quantized to cents at the
database boundary and never touch a binary float.

Authorization contract: ``get_user_orders`` does NOT authenticate.  The
caller must pass a ``user_id`` derived from the authenticated session.
Passing a user id taken from the request path, query string, or body is
a horizontal privilege-escalation bug.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Sequence

logger = logging.getLogger(__name__)

# Server-side allowlist.  Request-supplied status values are matched
# against this and rejected otherwise; the parameterized query below is
# the injection control, this is the input-validation one.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100
CENT = Decimal("0.01")
DB_TIMEOUT_SECONDS = 5.0


class OrderQueryError(Exception):
    """Raised for a failure the caller should turn into a 5xx.

    Carries a message safe to show a client; the detail is logged.
    """


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal  # major units, quantized to cents
    status: str


def _amount_from_db(raw: object, *, order_id: object) -> Decimal:
    """Convert a stored amount to Decimal cents, loudly on bad data."""
    if raw is None:
        raise OrderQueryError(
            f"orders.amount is NULL for order id={order_id}; "
            f"fix the row or add a NOT NULL constraint"
        )
    try:
        # str() first: Decimal(float) would carry the float's binary error.
        return Decimal(str(raw)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OrderQueryError(
            f"orders.amount is not a number for order id={order_id}: {raw!r}"
        ) from exc


def get_user_orders(
    db_path: str,
    user_id: int,
    status: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a single user's orders in the given status.

    ``user_id`` MUST come from the authenticated session (see module
    docstring).  ``db_path`` must be a trusted server-side constant; it
    is never derived from request input.
    """
    # bool is a subclass of int; True would silently query user 1.
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError(
            f"get_user_orders: user_id must be an int from the session, "
            f"got {type(user_id).__name__}"
        )
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"get_user_orders: unknown status {status!r}; "
            f"allowed: {sorted(ALLOWED_STATUSES)}"
        )
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"get_user_orders: offset must be >= 0, got {offset!r}")
    if not isinstance(limit, int) or limit < 1:
        raise ValueError(f"get_user_orders: limit must be >= 1, got {limit!r}")
    if limit > MAX_PAGE_SIZE:
        logger.warning(
            "get_user_orders: limit %d capped to %d (user_id=%s)",
            limit, MAX_PAGE_SIZE, user_id,
        )
        limit = MAX_PAGE_SIZE

    try:
        with closing(sqlite3.connect(db_path, timeout=DB_TIMEOUT_SECONDS)) as conn:
            with closing(conn.cursor()) as cur:
                # Placeholders, not interpolation: user_id and status are
                # bound values and can never be parsed as SQL.
                cur.execute(
                    "SELECT id, amount, status FROM orders "
                    "WHERE user_id = ? AND status = ? "
                    "ORDER BY id LIMIT ? OFFSET ?",
                    (user_id, status, limit, offset),
                )
                rows = cur.fetchall()
    except sqlite3.Error as exc:
        # Log the internals; hand the caller something safe to render.
        logger.exception(
            "order query failed: user_id=%s status=%s limit=%d offset=%d",
            user_id, status, limit, offset,
        )
        raise OrderQueryError("could not load orders") from exc

    return [
        Order(id=row[0], amount=_amount_from_db(row[1], order_id=row[0]), status=row[2])
        for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Decimal | None:
    """Mean order amount, rounded half-up to the cent.

    Returns None for an empty sequence: there is no average of nothing,
    and 0.00 would be indistinguishable from a real zero-value average.
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Reduce ``amount`` by ``pct`` percent, where 15 means 15%.

    Rounding policy: the discount is rounded half-up to the cent, then
    subtracted, so the returned price is always a whole number of cents.
    """
    if not isinstance(amount, Decimal):
        raise TypeError(
            f"apply_discount: amount must be Decimal, got {type(amount).__name__}; "
            f"floats cannot represent cents exactly"
        )
    if amount < 0:
        raise ValueError(f"apply_discount: amount must be >= 0, got {amount}")
    pct = Decimal(str(pct))
    if not (Decimal(0) <= pct <= Decimal(100)):
        raise ValueError(
            f"apply_discount: pct must be between 0 and 100 (15 means 15%), got {pct}"
        )

    discount = (amount * pct / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    # max() guards the half-cent case where a sub-cent amount rounds its
    # own discount up past itself; a price is never negative.
    return max(Decimal("0.00"), (amount - discount).quantize(CENT, rounding=ROUND_HALF_UP))


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """One receipt line.  Currency symbol is a parameter, not an assumption."""
    return f"Order #{order.id}: {currency_symbol}{order.amount:.2f}"
```

## What I could not verify, and what to run

I have not executed either version — no shell in this session — so the crash claims (7 and 3) and the rounding results rest on reading Python semantics, not on an observed run.

I also could not see the schema, so three things are assumptions: that `orders.id` is an `INTEGER` column (which is what makes finding 7 a certain crash rather than a possible one), that `orders.amount` stores major units rather than integer cents (if it stores cents, `_amount_from_db` needs a `/ 100`), and that the six values in `ALLOWED_STATUSES` are the real status vocabulary — check `orders.status` against the writer side before merging.

Nor could I see the HTTP handler, so I cannot tell you whether finding 2 is currently exploitable or whether the handler already checks ownership. That is the first thing to look at.

Before merging, run: `sqlite3 <db> ".schema orders"` to settle the three schema assumptions; a call to the old `format_receipt((7, 12.30, "paid"))` to see the `TypeError` for yourself; `average_order_value([])` on the old version for the `ZeroDivisionError`; and, against a scratch copy of the database, the old `get_user_orders` with `status="paid' OR '1'='1"` to see other users' rows come back, then the same input against the new one to see it rejected.