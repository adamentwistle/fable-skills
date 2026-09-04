I could not execute anything this session — the Bash tool is disabled — so the corrected code below is verified by inspection only. Before merging, run the checks listed at the end.

## Issues

**1. SQL injection — critical.** `user_id` and `status` are interpolated straight into the query with `%s`, and they come from the HTTP request. `status = "x' OR '1'='1"` returns every order in the table; a payload with `;` or a subselect reads other tables. Fix: parameterised query with `?` placeholders, values passed as a tuple.

**2. No authorization check — critical.** The function reads whatever `user_id` the request supplied. Any logged-in user can enumerate ids and read everyone's orders (insecure direct object reference). Fix: derive the user id from the session and compare it with the requested one, rejecting a mismatch. In the code below that's the `viewer_id` argument; the better end state is that the handler never accepts `user_id` from the client at all.

**3. `format_receipt` raises `TypeError` on every call — critical.** `"Order #" + order[0]` concatenates a `str` with the `INTEGER PRIMARY KEY` id. This function cannot ever have been run. Fix: f-string.

**4. `average_order_value` divides by zero — high.** `len(orders)` is 0 whenever a user has no orders in that status, which is exactly what `get_user_orders` returns for a new user. `ZeroDivisionError` → 500. Fix: return `None` for an empty sequence. `None`, not `0.00`: "no orders" and "orders averaging zero" are different facts and a caller that prints `0.00` for a new customer is wrong.

**5. Money held in binary floats — high.** `total = 0.0`, `+=`, and the multiply/divide in `apply_discount` all accumulate representation error. `apply_discount(10.0, 33)` returns `6.699999999999999`, which `format_receipt` then prints verbatim. Fix: `Decimal` throughout, converted via `Decimal(str(x))` (never `Decimal(0.1)`, which imports the float error). The deeper fix is storing integer minor units (pence/cents) in the `amount` column; I have flagged that rather than changed the schema.

**6. No rounding policy — high.** Nothing ever quantises to 2 decimal places, so fractional pennies flow into totals and receipts. Fix: pick a policy, name it, apply it exactly once at the boundary. I chose `ROUND_HALF_UP` to 2 dp on the final payable amount. If the business rule is "never overcharge", that becomes `ROUND_FLOOR` on the discounted amount — a decision someone must confirm, not a default.

**7. `apply_discount` accepts any percentage — high.** `pct=200` returns a negative amount (the customer is owed money); `pct=-10` raises the price by 10% while calling itself a discount. Neither is caught downstream. Fix: reject anything outside 0–100, and reject a negative `amount`.

**8. Database connection is never closed — high.** No `close()`, no context manager, and an exception mid-query leaks the handle. Note that `with sqlite3.connect(...)` does *not* close a connection — it only wraps a transaction — so `contextlib.closing` is required. Under request load this exhausts file handles.

**9. `status` is not validated against an allowlist — medium.** Even parameterised, an arbitrary status silently returns an empty list, so a typo'd or hostile value looks identical to "no orders". Fix: server-side allowlist, rejected with a specific 400. Also guard the non-string case — `status=None` or a list from a query parser would otherwise crash on the comparison or on slicing in the error message.

**10. Unbounded result set — medium.** `fetchall()` with no `LIMIT` loads a user's entire order history into memory; a bulk account is a memory spike and a slow request. Fix: `LIMIT`/`OFFSET` with a clamped page size and a deterministic `ORDER BY id` (pagination without an explicit order can repeat or skip rows).

**11. Raw database errors reach the caller — medium.** Any `sqlite3.Error` propagates out of the function with internal detail — table names, and with a corrupt or missing file, the database path — into whatever the handler renders. Fix: log the exception with its stack for operators, raise a wrapped `OrderLookupFailed` chained with `from e`, and have the handler map it to a generic 500 body.

**12. A missing database file is created silently — medium.** `sqlite3.connect(path)` on a nonexistent path makes an empty database, so a misconfigured `db_path` fails later as "no such table: orders" instead of "config points at a file that isn't there". Fix: check the file exists and open read-only via a `file:...?mode=ro` URI. Read-only also means an injection that slipped through could not write.

**13. Rows are passed around as bare tuples — medium.** `o[1]` and `order[0]` hard-code the column order of the `SELECT`. Add a column to the query and every caller silently reads the wrong field — a data-integrity bug with no error. Fix: `sqlite3.Row` at the boundary, converted into a small `Order` dataclass.

**14. Receipt amount is unformatted — medium.** `str(order[1])` prints `12.5`, not `12.50`, and prints float artifacts in full. Fix: `:,.2f`.

**15. Type confusion between session id and request id — medium.** The session's `viewer_id` is an `int`; the request's `user_id` arrives as the string `"5"`. Comparing them directly denies a legitimate request (and any comparison-based check is fragile). Fix: coerce both to bounded ints *before* the ownership comparison, as the code below does.

**16. Currency is assumed — low.** `"$"` is hardcoded and the `orders` table has no currency column, so a non-USD order is mislabelled rather than failing. I made the symbol a parameter; storing the currency per order is the real fix.

**17. `db_path` is trusted — low.** It is a filesystem path used to open a file. It must come from configuration only; if any request value ever reaches it, that is arbitrary-file read. Worth a comment at the call site.

**18. No logging, no type hints, no docstrings, no tests — low.** Nothing records who was refused, which query failed, or how long it took. Added a structured warning on the authorization denial and an exception log on query failure, matching the `key=value` style; adopt whatever the surrounding service already uses.

**19. No connection reuse or timeout — low.** A fresh connection per request, with SQLite's default 5-second lock timeout left implicit. Fine at low volume; use a shared read-only connection or a pool if this is hot.

## Corrected code

```python
"""Order lookup, discounting and receipt formatting for the orders service.

Money policy: every amount is a Decimal. Arithmetic is exact; the result is
rounded ROUND_HALF_UP to 2 decimal places exactly once, at the point it is
returned to a caller. Storing integer minor units in the `amount` column would
remove the float round-trip entirely — see review note 5.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

# Server-side allowlist. A status not in here is rejected at the boundary,
# never passed through to the query.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
MAX_USER_ID = 2**63 - 1

CENTS = Decimal("0.01")
ROUNDING = ROUND_HALF_UP


class OrderError(Exception):
    """Base class for order-service failures."""


class InvalidStatus(OrderError, ValueError):
    """The requested status is not one this service recognises."""


class OrderLookupFailed(OrderError):
    """The orders could not be read. Message is operator-facing; the HTTP layer
    must map this to a generic 500 body."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _to_decimal(value, *, name: str) -> Decimal:
    """Convert to Decimal via str(): Decimal(0.1) carries the binary float
    error, Decimal(str(0.1)) does not."""
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(
            f"{name} must be a number or numeric string, got {type(value).__name__}"
        )
    else:
        try:
            d = Decimal(str(value))
        except InvalidOperation as e:
            raise ValueError(f"{name} must be a number, got {value!r}") from e
    if not d.is_finite():
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    return d


def _bounded_int(value, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    try:
        n = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be an integer, got {value!r}") from e
    if not minimum <= n <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {n}")
    return n


def _money_from_row(value, *, field: str) -> Decimal:
    if value is None:
        raise OrderLookupFailed(
            f"orders.{field} is NULL; every order row must carry an amount"
        )
    try:
        return _to_decimal(value, name=f"orders.{field}").quantize(
            CENTS, rounding=ROUNDING
        )
    except (TypeError, ValueError) as e:
        raise OrderLookupFailed(
            f"orders.{field} is not a usable amount: {value!r}"
        ) from e


def get_user_orders(
    db_path: str,
    *,
    viewer_id: int,
    user_id: int,
    status: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a user's orders in the given status.

    `db_path` must come from configuration, never from a request.
    `viewer_id` must be derived from the session, never from the request body.
    """
    # Coerce before comparing: the session id is an int, the request id arrives
    # as a string, and "5" != 5 would deny a legitimate request.
    viewer_id = _bounded_int(viewer_id, name="viewer_id", minimum=1, maximum=MAX_USER_ID)
    user_id = _bounded_int(user_id, name="user_id", minimum=1, maximum=MAX_USER_ID)

    if viewer_id != user_id:
        logger.warning(
            "orders.forbidden viewer_id=%s target_user_id=%s", viewer_id, user_id
        )
        raise PermissionError(
            f"user {viewer_id} may not read orders owned by user {user_id}"
        )

    if not isinstance(status, str) or status not in ALLOWED_STATUSES:
        raise InvalidStatus(
            f"unknown order status {str(status)[:32]!r}; expected one of: "
            f"{', '.join(sorted(ALLOWED_STATUSES))}"
        )

    limit = _bounded_int(limit, name="limit", minimum=1, maximum=MAX_PAGE_SIZE)
    offset = _bounded_int(offset, name="offset", minimum=0, maximum=10**9)

    if not os.path.isfile(db_path):
        raise OrderLookupFailed(
            f"orders database not found at {db_path!r}; check the service's "
            f"database path configuration"
        )

    # Read-only URI: a missing file fails loudly instead of being created empty,
    # and no statement reaching this connection can write.
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"

    sql = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )

    try:
        # closing(), not `with sqlite3.connect(...)`: the latter commits a
        # transaction but leaves the connection open.
        with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cur:
                cur.execute(sql, (user_id, status, limit, offset))
                rows = cur.fetchall()
    except sqlite3.Error as e:
        logger.exception(
            "orders.query_failed user_id=%s status=%s limit=%s offset=%s",
            user_id, status, limit, offset,
        )
        raise OrderLookupFailed(
            f"could not read orders for user_id={user_id} status={status!r}"
        ) from e

    return [
        Order(
            id=int(row["id"]),
            amount=_money_from_row(row["amount"], field="amount"),
            status=row["status"],
        )
        for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, or None when there are no orders.

    None rather than 0.00: "this customer has no orders" and "this customer's
    orders average zero" are different facts and callers must not conflate them.
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUNDING)


def apply_discount(amount, pct) -> Decimal:
    """Amount after a percentage discount, rounded half-up to 2 dp.

    `pct` is a percentage (15 means 15%), not a fraction.
    """
    amount = _to_decimal(amount, name="amount")
    pct = _to_decimal(pct, name="pct")
    if amount < 0:
        raise ValueError(f"amount must not be negative, got {amount}")
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError(
            f"discount percentage must be between 0 and 100, got {pct}"
        )
    # Bounded pct keeps the result in [0, amount], so no negative total.
    return (amount - amount * pct / Decimal(100)).quantize(CENTS, rounding=ROUNDING)


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """Single-line receipt. The orders table has no currency column, so the
    symbol is the caller's assertion — see review note 16."""
    return f"Order #{order.id}: {currency_symbol}{order.amount:,.2f}"
```

## What to run before merging

Nothing here has been executed. The checks that would confirm it:

- `apply_discount(Decimal("10.00"), 33)` must equal `Decimal("6.70")`, and `apply_discount("19.99", 15)` must equal `Decimal("16.99")` (19.99 − 2.9985, rounded half-up). Compare against hand arithmetic, not against the function's own output.
- `average_order_value([])` returns `None`; `format_receipt(Order(7, Decimal("1234.5"), "paid"))` returns `Order #7: $1,234.50`.
- Against a temporary database: `status="paid' OR '1'='1"` raises `InvalidStatus`; `user_id="1 OR 1=1"` raises `ValueError`; `viewer_id=1, user_id=2` raises `PermissionError`; `status=None` raises `InvalidStatus` rather than `TypeError`.
- `Decimal.__format__` with `,.2f` — I am confident it is supported, but it is the one line most worth seeing print.

Two things I could not check from the module alone: the real column types of `orders` (if `amount` is already integer minor units, `_money_from_row` needs a divide-by-100 instead of a `str()` round-trip), and every existing caller of these four functions. All four signatures changed — `get_user_orders` now takes keyword arguments and a `viewer_id`, and the other three now take `Order` objects and return `Decimal` — so each call site needs updating, and any code doing float arithmetic on these return values will raise `TypeError` on mixing `Decimal` with `float`.