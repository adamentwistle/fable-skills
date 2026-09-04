Twenty issues; four are ship-blockers. The SQL injection and the missing ownership check are the two that matter most — together they let any authenticated caller read every order in the table.

## Issues

**1. SQL injection — critical.** `user_id` and `status` are interpolated into the query string with `%`. A `status` of `x' OR '1'='1` returns every order in the table; a subquery in the same position can read other tables. `sqlite3.execute` refuses multiple statements, so this is not stacked-query RCE, but it is full read exfiltration. Fix: `?` placeholders, values passed as a tuple.

**2. No authorization check (IDOR) — critical.** `user_id` arrives from the request and is used as-is. Any authenticated user reads anyone's orders by changing one number. Parameterizing the query does not fix this. Fix: derive the user from the session and reject when the requested `user_id` is not the caller's, unless an explicit admin flag says otherwise.

**3. `average_order_value` divides by zero — high.** `len(orders)` is 0 whenever the query matched nothing, which is the common case for a status like `refunded`. `ZeroDivisionError` reaches the handler as a 500. Fix: return `None` for an empty input and document it.

**4. `format_receipt` raises `TypeError` on every call — high.** `"Order #" + order[0]` concatenates a string with the integer primary key. This is not an edge case; it fails for all real rows. Fix: f-string.

**5. `apply_discount` accepts any `pct` — high.** A negative percentage *increases* the charge, and a percentage above 100 produces a negative price, which downstream will read as a refund. Fix: reject anything outside 0–100 before computing.

**6. Money is held in binary floats — high.** `total = 0.0` and float multiplication in `apply_discount` mean amounts drift, and there is no rounding policy at all, so a receipt can show `$19.999999999999996` and a total can disagree with the sum of its line items. Fix: `Decimal` end to end, converted at the read boundary, with one stated rounding policy applied once. The durable fix is storing `amount` as integer cents in the schema — flagging that rather than changing it here.

**7. The database connection is never closed — high.** No `close`, no context manager, and an exception between `connect` and `return` leaks the handle for certain. Under sustained traffic the process exhausts file descriptors. Fix: `contextlib.closing` around both connection and cursor.

**8. `status` is not validated against an allowlist — medium.** An unknown status silently returns an empty list, which the caller cannot tell apart from "this user has no shipped orders". Fix: a server-side `frozenset` of valid statuses; reject with a 400 on a miss.

**9. `user_id` is not coerced or validated — medium.** The code currently leans on SQLite's type-affinity rules to match a quoted string against an INTEGER column. Fix: explicit `int()` conversion with a clear rejection, so the behavior does not depend on affinity subtleties.

**10. Unbounded `fetchall` — medium.** No `LIMIT`. One user with a large order history pulls the whole set into memory on every request. Fix: `LIMIT`/`OFFSET` with a capped page size, and mark the result as partial rather than silently truncating.

**11. Raw SQLite errors reach the client — medium.** An `OperationalError` renders as `unable to open database file: E:\...\orders.db`, leaking the filesystem layout into the response. Fix: catch `sqlite3.Error`, log the detail with `db_path` for operators, raise a generic error outward.

**12. No logging anywhere — medium.** Nothing records who asked for what, or that a lookup failed. Fix: log the denial, the failure with its stack, and truncated pages.

**13. Positional tuple indexing — medium.** `o[1]` and `order[0]` break silently into wrong numbers if anyone reorders the `SELECT` columns. Fix: map rows into a dataclass at the boundary.

**14. A NULL `amount` crashes the sum — medium.** `total += None` is a `TypeError` with no indication of which row is bad. Fix: reject loudly, naming the order id.

**15. `pct` units are undocumented — medium.** Nothing says whether 15% is `15` or `0.15`. The code means `15`, but a caller passing `0.15` gets a 0.15% discount and no error. Fix: document it, and name the parameter for its unit.

**16. Currency is assumed, not carried — low/medium.** `"$"` is hardcoded. If the service ever handles more than USD, receipts mislabel amounts. Fix: carry a currency code on the order, or assert single-currency in a comment.

**17. Amounts are formatted with `str()` — low.** Produces `$12.5`, and `$1e-05` for very small values. Fix: quantize to cents before formatting.

**18. `average_order_value` needs a sized sequence — low.** `len()` fails on a generator. Fix: materialize the input once.

**19. A fresh connection per call, in read/write mode — low.** This is a pure read path. Opening read-only would prevent an accidental write, and connection reuse would cut per-request cost.

**20. No index is guaranteed on `(user_id, status)` — low.** Without one this is a full table scan per request. Verify against the schema.

Also worth stating as an invariant rather than a bug: `db_path` must remain a server-side constant. If it ever becomes request-derived, this becomes arbitrary file read, since `sqlite3.connect` opens any path the process can reach.

## Corrected code

```python
"""Order lookup and money arithmetic for the orders service.

Money is Decimal end to end. The durable fix is storing ``orders.amount``
as integer minor units (cents); until the schema changes, values are
converted with ``Decimal(str(...))`` at the read boundary and never touch
a binary float.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")

# Server-side allowlist: request-supplied status is matched against this
# before it reaches the database. Confirm these against the schema.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


class InvalidOrderQuery(ValueError):
    """Caller-supplied parameters were rejected. Handler maps this to 400."""


class OrderAccessDenied(Exception):
    """Caller may not read these orders. Handler maps this to 403."""


class OrderLookupError(Exception):
    """Orders could not be read. Handler maps this to 500, generic body."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


@dataclass(frozen=True)
class OrderPage:
    orders: tuple[Order, ...]
    has_more: bool  # True means this page is partial; request the next offset.


def _validate_user_id(value, name="user_id"):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InvalidOrderQuery(
            f"{name} must be an integer, got {type(value).__name__}"
        )
    try:
        user_id = int(value)
    except ValueError:
        raise InvalidOrderQuery(f"{name} must be an integer, got {value!r}") from None
    if user_id <= 0:
        raise InvalidOrderQuery(f"{name} must be positive, got {user_id}")
    return user_id


def _validate_status(value):
    if not isinstance(value, str):
        raise InvalidOrderQuery(
            f"status must be a string, got {type(value).__name__}"
        )
    # Assumes the column stores lowercase status values; verify against schema.
    status = value.strip().lower()
    if status not in ALLOWED_STATUSES:
        raise InvalidOrderQuery(
            f"status must be one of {sorted(ALLOWED_STATUSES)}, got {value!r}"
        )
    return status


def _validate_page(limit, offset):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise InvalidOrderQuery(
            f"limit must be an integer in 1..{MAX_PAGE_SIZE}, got {limit!r}"
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise InvalidOrderQuery(
            f"offset must be a non-negative integer, got {offset!r}"
        )


def _as_decimal(value, name):
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidOrderQuery(f"{name} must be a number, got {type(value).__name__}")
    else:
        try:
            result = Decimal(str(value))
        except InvalidOperation:
            raise InvalidOrderQuery(f"{name} must be a number, got {value!r}") from None
    if not result.is_finite():
        raise InvalidOrderQuery(f"{name} must be a finite number, got {value!r}")
    return result


def _row_amount(raw, order_id):
    if raw is None:
        raise OrderLookupError(
            f"orders.amount is NULL for order id={order_id}; every order must carry an amount"
        )
    try:
        amount = Decimal(str(raw))
    except InvalidOperation:
        raise OrderLookupError(
            f"orders.amount is not a number for order id={order_id}: {raw!r}"
        ) from None
    if not amount.is_finite():
        raise OrderLookupError(
            f"orders.amount is not finite for order id={order_id}: {raw!r}"
        )
    return amount


def get_user_orders(
    db_path,
    user_id,
    status,
    *,
    session_user_id,
    is_admin=False,
    limit=DEFAULT_PAGE_SIZE,
    offset=0,
):
    """Read one page of a user's orders with the given status.

    ``db_path`` must be a server-side constant. Never pass a request-derived
    value: sqlite3 will open any path the process can read.

    ``session_user_id`` comes from the authenticated session, never from the
    request body or query string.
    """
    user_id = _validate_user_id(user_id)
    status = _validate_status(status)
    session_user_id = _validate_user_id(session_user_id, "session_user_id")
    _validate_page(limit, offset)

    # Authorization: ownership of the specific rows, not merely "is logged in".
    if user_id != session_user_id and not is_admin:
        logger.warning(
            "order access denied: caller=%s requested_user_id=%s",
            session_user_id,
            user_id,
        )
        raise OrderAccessDenied("you may only read your own orders")

    try:
        with closing(sqlite3.connect(db_path)) as conn:
            with closing(conn.cursor()) as cur:
                # Fetch one extra row to detect a partial page without a COUNT.
                cur.execute(
                    "SELECT id, amount, status FROM orders "
                    "WHERE user_id = ? AND status = ? "
                    "ORDER BY id LIMIT ? OFFSET ?",
                    (user_id, status, limit + 1, offset),
                )
                rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.exception(
            "order lookup failed: db_path=%s user_id=%s status=%s",
            db_path,
            user_id,
            status,
        )
        raise OrderLookupError("could not read orders") from exc

    has_more = len(rows) > limit
    orders = tuple(
        Order(id=int(row[0]), amount=_row_amount(row[1], row[0]), status=row[2])
        for row in rows[:limit]
    )
    if has_more:
        logger.info(
            "order page truncated: user_id=%s status=%s limit=%s offset=%s",
            user_id,
            status,
            limit,
            offset,
        )
    return OrderPage(orders=orders, has_more=has_more)


def average_order_value(orders):
    """Mean order amount, rounded half-up to whole cents.

    Returns None when there are no orders — callers must handle that rather
    than treat it as zero. Note this averages exactly the orders passed in;
    on a truncated OrderPage that is a page average, not a lifetime average.
    """
    orders = tuple(orders)
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct):
    """Subtract ``pct`` percent from ``amount``.

    ``pct`` is a percentage, so 15 means 15% — not the fraction 0.15.

    Rounding policy: the discount is rounded half-up to whole cents and then
    subtracted, so ``price + discount == amount`` exactly and the price never
    carries a fraction of a cent.
    """
    amount = _as_decimal(amount, "amount")
    pct = _as_decimal(pct, "pct")
    if amount < 0:
        raise InvalidOrderQuery(f"amount must not be negative, got {amount}")
    if not Decimal(0) <= pct <= Decimal(100):
        raise InvalidOrderQuery(f"pct must be a percentage in 0..100, got {pct}")
    discount = (amount * pct / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)
    return amount - discount


def format_receipt(order):
    """One receipt line. Assumes all amounts are USD."""
    amount = order.amount.quantize(CENTS, rounding=ROUND_HALF_UP)
    return f"Order #{order.id}: ${amount}"
```

## What to run before merging, and what I could not check

I did not execute any of this — no schema, no database, and no test suite was provided, so every claim above comes from reading the code, not from a run. Three things to do before shipping:

Confirm the injection is closed: call `get_user_orders` with `status="x' OR '1'='1"` and assert it raises `InvalidOrderQuery` rather than returning rows. Confirm the authorization check: call with `user_id=2, session_user_id=1, is_admin=False` and assert `OrderAccessDenied`. Then trigger the error path — point `db_path` at a nonexistent file and read the rendered message to confirm the path appears in the log and not in the exception.

Four things I could not verify from the material given. The `ALLOWED_STATUSES` set is my guess at the domain and must be reconciled with the actual `orders.status` values, including their casing — `_validate_status` lowercases, which is wrong if the column stores `Pending`. Whether an index exists on `(user_id, status)` is unknown. Whether `amount` is stored as REAL, INTEGER cents, or TEXT changes the `Decimal(str(...))` conversion, and if it is REAL then precision was already lost before this code ran. And I do not know the callers of these four functions, so the signature changes — a required `session_user_id`, an `OrderPage` instead of a list of tuples, `Order` objects instead of tuples — will break them and need updating at each call site.