Static review only — I have no schema, no callers, and ran nothing. Two assumptions: `orders.id` is an INTEGER primary key, and `orders.amount` is a REAL column (the code's `float` handling implies it). Both matter to the fixes below.

## Trust boundaries in this code

- `user_id` (HTTP request) → SQL predicate → parameter binding + integer coercion, and it must come from the session instead.
- `status` (HTTP request) → SQL predicate → server-side allowlist + parameter binding.
- `db_path` (caller) → `sqlite3.connect` → open in `rw` mode so a wrong path errors instead of creating an empty database.
- order fields (database, originally user-supplied) → receipt string → typed conversion; escape if it ever reaches HTML.

## Critical

**1. SQL injection in `get_user_orders`.** `status` and `user_id` are interpolated straight into the query with `%`. `status = "x' OR '1'='1"` returns every order in the table; `'; DROP TABLE orders; --` is blocked only by `execute` refusing multiple statements, and `executescript` anywhere nearby removes that accident of safety. Fix: `?` placeholders, values passed as the second argument to `execute`.

**2. No authorization — insecure direct object reference.** `user_id` arrives from the request and is used as the whole access-control decision. Any authenticated user can read any other user's orders by changing one parameter. Fix: derive `user_id` from the authenticated session in the handler and never accept it from the client. The corrected function keeps the parameter but the docstring states the contract; the handler is where this must actually be enforced.

## High

**3. `ZeroDivisionError` on a user with no orders.** `average_order_value` divides by `len(orders)` with no guard. A brand-new customer crashes the endpoint with a 500. Fix: return `None` for an empty list and let the caller decide how to display it. Returning `0` is wrong — "no orders" and "orders averaging zero" are different facts.

**4. `format_receipt` raises `TypeError` on every call.** `"Order #" + order[0]` concatenates a `str` with an `int` id. This is not an edge case; it fails on the first real row. Fix: f-string.

**5. Connection and cursor leak.** `conn` is never closed, and on any exception it leaks along with its file handle and lock. Under load this exhausts handles and blocks writers. Fix: `contextlib.closing` around both. Note that `with sqlite3.connect(...)` alone does **not** close the connection — it only commits or rolls back the transaction.

**6. Money in binary floats.** `total += o[1]`, `amount - amount * pct / 100`, and `total / len(orders)` all use floats, which cannot represent 0.10 or 0.01 exactly. Errors compound across a sum and surface as off-by-a-cent totals. Fix: `Decimal` throughout, converted from the stored value via `Decimal(str(value))`. The durable fix is a schema change to INTEGER minor units (cents); I have flagged it rather than assumed it, since I cannot see the schema.

**7. `status` is not validated against an allowlist.** Even parameterized, an arbitrary string reaches the database and quietly returns zero rows, so a typo in a client looks identical to "no orders". Fix: reject anything outside a server-side `ALLOWED_STATUSES` set with a specific error.

**8. Unbounded `fetchall`.** A user with 200,000 orders pulls all of them into memory in one list. Fix: `LIMIT`/`OFFSET` with a hard server-side cap.

## Medium

**9. `apply_discount` never validates `pct`.** A negative percentage *increases* the price; anything over 100 returns a negative amount, which downstream may turn into a refund. Fix: require `0 <= pct <= 100` and `amount >= 0`, raising `ValueError` with the offending value.

**10. No rounding policy anywhere.** The discount and the average are returned at full float precision and printed raw. Fix: pick a policy, name it, and apply it once at the boundary. I used ROUND_HALF_UP on the discount amount, which keeps the invariant `0 <= result <= amount` for any valid `pct`.

**11. A wrong `db_path` silently creates an empty database.** `sqlite3.connect` creates the file if it is missing, so a misconfigured path yields "no orders" instead of an error, for every user, indefinitely. Fix: open with `mode=rw` via a URI so a missing file raises.

**12. Raw `sqlite3` errors reach the HTTP handler.** An `OperationalError` message names tables and columns and may name the database path. Nothing is logged, so the outage leaves no trace. Fix: catch `sqlite3.Error`, log it with the stack and the query parameters, and re-raise a wrapped `OrderQueryError` chained with `from exc`.

**13. A NULL `amount` raises `TypeError` mid-sum.** If the column is nullable, `total += None` fails with a message that does not name the offending order. Fix: check at conversion time and raise an error carrying the order id.

**14. Positional tuple indexing across three functions.** `o[1]` and `order[0]` silently produce wrong output the day someone reorders the `SELECT` columns — no exception, just wrong receipts. Fix: `sqlite3.Row` plus a frozen dataclass.

**15. The quotes around `'%s'` force a text comparison.** With an INTEGER `user_id` column, SQLite compares a TEXT literal against an INTEGER and matching depends on column affinity. Naively swapping in a `?` while passing the string `"42"` can therefore change which rows match. Fix: coerce `user_id` to `int` explicitly and reject non-integers at the boundary.

## Low

**16. No `ORDER BY`.** Row order is unspecified, so pagination can repeat or skip rows. Fix: `ORDER BY id`.

**17. Currency is neither selected nor compared.** Averaging orders in mixed currencies produces a meaningless number. If the schema has a currency column, group by it; if not, this is a data-model gap worth raising.

**18. `format_receipt` hardcodes `$` and drops `status`**, though `status` is selected. Fix: parameterize the symbol, include the status.

**19. Receipt output is unescaped.** It is plain text today, which is fine. If it is ever interpolated into an HTML page or a PDF template, escape it — the values originate from user input.

**20. No connection timeout.** The default 5 seconds under write contention surfaces as a bare `OperationalError`. It is now at least logged and wrapped.

**21. No type hints, docstrings, or tests.** Nothing here documents that `average_order_value` can return `None`, which is exactly the kind of contract callers get wrong.

## Corrected code

```python
"""Order queries and money helpers for the orders service.

Money is handled as Decimal, never binary float. The `orders.amount` column is
assumed to be REAL; values are converted through str() to avoid inheriting the
stored float's representation error. The durable fix is to store amounts as
INTEGER minor units (cents) and drop the conversion entirely.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Sequence, Union

logger = logging.getLogger(__name__)

# Statuses a caller is allowed to filter on. Anything else is rejected at the
# boundary rather than passed to the database, where it would return zero rows
# and look identical to "this user has no orders".
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

MAX_LIMIT = 500
CENTS = Decimal("0.01")

Money = Union[Decimal, int, str, float]


class OrderQueryError(Exception):
    """A failure serving an order query. Message is operator-facing: log it,
    do not return it to an HTTP client."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _as_decimal(value: Money, *, field: str) -> Decimal:
    """Convert to Decimal. Floats go through str() so we get the shortest
    decimal that round-trips, not the full binary expansion."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} is not a valid decimal number: {value!r}") from exc


def _row_to_order(row: sqlite3.Row) -> Order:
    order_id = row["id"]
    amount = row["amount"]
    status = row["status"]

    if amount is None:
        raise OrderQueryError(f"order id={order_id} has a NULL amount")
    try:
        amount_dec = _as_decimal(amount, field="amount")
    except ValueError as exc:
        raise OrderQueryError(
            f"order id={order_id} has a non-numeric amount: {amount!r}"
        ) from exc

    # Rounding policy: amounts are stored to the cent. Quantizing here makes
    # that explicit and keeps every downstream sum exact.
    return Order(
        id=int(order_id),
        amount=amount_dec.quantize(CENTS, rounding=ROUND_HALF_UP),
        status=str(status),
    )


def get_user_orders(
    db_path: str,
    user_id: Union[int, str],
    status: str,
    limit: int = 100,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a user's orders with the given status.

    AUTHORIZATION: `user_id` must be derived from the authenticated session by
    the caller. Passing a client-supplied user id here is an IDOR — any user
    can then read any other user's orders.

    Raises ValueError for invalid arguments and OrderQueryError for database
    failures. Neither message is safe to return to an HTTP client verbatim.
    """
    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"user_id must be an integer, got {user_id!r}") from exc
    if user_id_int <= 0:
        raise ValueError(f"user_id must be positive, got {user_id_int}")

    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"unknown order status {status!r}; "
            f"allowed: {sorted(ALLOWED_STATUSES)}"
        )

    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer in 1..{MAX_LIMIT}, got {limit!r}")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"offset must be a non-negative integer, got {offset!r}")

    # mode=rw so a wrong path raises instead of creating an empty database and
    # silently reporting "no orders" forever. (Does not support ":memory:".)
    db_uri = f"{Path(db_path).resolve().as_uri()}?mode=rw"

    try:
        with closing(sqlite3.connect(db_uri, uri=True, timeout=10.0)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT id, amount, status FROM orders "
                    "WHERE user_id = ? AND status = ? "
                    "ORDER BY id LIMIT ? OFFSET ?",
                    (user_id_int, status, limit, offset),
                )
                rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.exception(
            "order query failed: user_id=%s status=%s db_path=%s",
            user_id_int,
            status,
            db_path,
        )
        raise OrderQueryError(
            f"could not read orders for user_id={user_id_int} status={status}"
        ) from exc

    return [_row_to_order(row) for row in rows]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, rounded to the cent, or None if there are no orders.

    None rather than 0: "this user has no orders" and "this user's orders
    average zero" are different facts and the caller displays them differently.

    Assumes all amounts share a currency. If the schema gains a currency
    column, group by it before calling this.
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount: Money, pct: Money) -> Decimal:
    """Return `amount` less `pct` percent, rounded to the cent.

    Rounding policy: the discount is computed then rounded ROUND_HALF_UP, and
    subtracted once. With 0 <= pct <= 100 this guarantees 0 <= result <= amount.
    """
    amount_dec = _as_decimal(amount, field="amount")
    pct_dec = _as_decimal(pct, field="pct")

    if amount_dec < 0:
        raise ValueError(f"amount must not be negative, got {amount_dec}")
    if not Decimal("0") <= pct_dec <= Decimal("100"):
        raise ValueError(f"pct must be a percentage in 0..100, got {pct_dec}")

    discount = (amount_dec * pct_dec / Decimal("100")).quantize(
        CENTS, rounding=ROUND_HALF_UP
    )
    return (amount_dec - discount).quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """One-line plain-text receipt.

    Plain text only. Escape the result before embedding it in HTML — the id and
    status originate from data the user influenced.
    """
    return (
        f"Order #{order.id}: {currency_symbol}{order.amount:.2f} ({order.status})"
    )
```

Two things I could not settle from the snippet alone: whether `orders.amount` is REAL or already integer cents, and whether an order carries a currency. Both change `_row_to_order`.