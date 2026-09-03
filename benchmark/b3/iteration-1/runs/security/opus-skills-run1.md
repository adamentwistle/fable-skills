Static review only — I did not execute the module. Two critical issues: the query is SQL-injectable from the HTTP request, and it trusts a client-supplied `user_id`, so any user can read anyone's orders. Three of the four functions also crash outright on inputs this same module produces (empty order list, integer order id).

**Trust boundaries in this code**

- `user_id` (HTTP request) → SQL `WHERE` → must come from the session, not the request; bound as a parameter.
- `status` (HTTP request) → SQL `WHERE` → bound as a parameter, plus a server-side allowlist.
- `db_path` (assumed config) → `sqlite3.connect` → must stay config-only; never request-derived.
- `amount` (database) → arithmetic and receipt text → coerced to `Decimal`, `NULL` rejected.
- `sqlite3.Error` → HTTP response → wrapped; detail logged, generic message returned.

**Issues**

1. **SQL injection — critical.** `user_id` and `status` are interpolated into the query string with `%`. A `status` of `x' OR '1'='1` returns every order in the table; `'; DROP TABLE orders; --` is limited only by `execute()` refusing multiple statements. Fix: `?` placeholders with a parameter tuple.
2. **Missing authorization (IDOR) — critical.** The function filters by whatever `user_id` the request supplied. Anyone can enumerate other users' order IDs and amounts. Fix: derive the ID from the authenticated session; if an admin path needs to query others, add an explicit role check before the call. The signature below renames the parameter to `authenticated_user_id` so a reviewer can see which value is expected.
3. **No status allowlist — high.** Even parameterized, an arbitrary `status` string is an unvalidated filter that reaches the database on every request. Fix: reject anything outside a known set before touching the connection.
4. **Connection is never closed — high.** No `try/finally` or context manager, and `with conn:` would only manage the transaction, not close the handle. On an exception the connection stays open holding a lock until the garbage collector runs. Fix: `contextlib.closing`.
5. **`ZeroDivisionError` in `average_order_value` — high.** `len(orders)` is zero whenever the query matches nothing, which is a normal result of `get_user_orders`. Fix: decide a policy and state it. I return `None`, because `0.00` is indistinguishable from a genuine average of zero-amount orders.
6. **`format_receipt` raises `TypeError` on every call — high.** `order[0]` is the `id` column, an integer, and `"Order #" + 1` is not concatenable. This has never run successfully against a real row. Fix: f-string.
7. **Money held in binary floats — high.** `total = 0.0`, `total += o[1]`, and `amount * pct / 100` all accumulate representation error; summing many order amounts drifts, and `0.1 + 0.2` is not `0.3`. Fix: `Decimal` throughout, with integer minor units in the database as the real long-term fix. I could not check the schema, so the code below coerces defensively via `Decimal(str(value))` for floats — `Decimal(0.1)` directly would preserve the binary noise.
8. **No discount validation — high.** `apply_discount(100, 150)` returns `-50`, and `apply_discount(100, -20)` silently *raises* the price to 120. Either is a money bug reachable from a bad admin input or a promo record. Fix: require `0 <= pct <= 100`, require a non-negative amount, and clamp the result at zero.
9. **No rounding policy — medium.** `total / len(orders)` and the discount both produce values with more precision than a currency has, and nothing rounds them. Fix: round once, at the boundary, half-up to the minor unit, with the policy named in a comment.
10. **`pct` unit is ambiguous — medium.** The name does not say whether 15% is `15` or `0.15`; only the `/100` reveals it. A caller passing `0.15` gets a 0.15% discount and no error. Fix: rename to `discount_pct`, document it, and let the range check catch the fraction form.
11. **Unbounded `fetchall` — medium.** No `LIMIT`. A customer with a large order history loads entirely into memory on every request. Fix: `LIMIT`/`OFFSET` with a hard cap and a stable `ORDER BY`.
12. **No error handling — medium.** A missing table or locked database propagates `sqlite3.OperationalError` to the HTTP layer, and a default framework error page can echo the message, leaking the schema or the database path. Fix: catch `sqlite3.Error`, log it with context, raise a domain error carrying a safe message.
13. **`NULL` amount crashes the sum — medium.** If `amount` is nullable, `total += None` raises `TypeError` inside a loop with no indication of which order was bad. Fix: coerce with a helper that names the offending order id.
14. **Positional tuple indexing — medium.** `o[1]` and `order[0]` encode the `SELECT` column order at three call sites. Adding a column to the query silently changes what "amount" means. Fix: `sqlite3.Row` plus a small `Order` record.
15. **Hardcoded `$` and no fixed decimals — medium.** `str(12.5)` renders as `12.5` and a float sum can render as `12.500000000000002`. Fix: format to exactly two decimals and pass the currency symbol in.
16. **Mixing `Decimal` and `float` raises `TypeError` — low.** Once amounts are `Decimal`, a caller passing a float `pct` gets an unsupported-operand error. Fix: coerce both arguments at the boundary, as below.
17. **No logging anywhere — low.** Nothing records which user, status, or database path was involved when a query fails. Fix: one log line at the failure point with those fields.
18. **No type hints or docstrings — low.** Nothing states that `amount` is money, or what the empty-list contract is.

Two things I did **not** change, deliberately: `db_path` stays a parameter, on the assumption it comes from application config rather than a request — if it can ever be request-derived, that is a critical path-traversal issue and must be pinned to a fixed path. And opening a fresh connection per call is left as-is; it is a performance concern, not a bug, and fixing it properly means passing in a shared connection from the handler.

```python
"""Order queries and money helpers for the orders service.

Money is handled as ``Decimal`` throughout. Amounts are never binary floats:
values read from SQLite are converted via ``str`` so that a stored REAL does
not carry its binary representation error into the arithmetic. The durable fix
is to store amounts as integer minor units (cents) in the database.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
MAX_PAGE_SIZE = 500
DB_TIMEOUT_SECONDS = 5.0

# Server-side allowlist. Anything not in here never reaches the database.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)


class OrderQueryError(RuntimeError):
    """The orders store could not be read. Safe to show to an API client."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal  # major units, e.g. Decimal("12.50")
    status: str


def _to_decimal(value: object, *, field: str, order_id: object = None) -> Decimal:
    """Coerce a database value to Decimal, or raise with the offending row named."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, float):
        # str() first: Decimal(0.1) would preserve the binary error, Decimal("0.1") does not.
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError(
                f"order {order_id!r}: {field} is not a valid number, got {value!r}"
            ) from None
    raise ValueError(
        f"order {order_id!r}: {field} must be numeric, got {type(value).__name__} "
        f"({value!r}) -- a NULL amount usually means an incomplete order row"
    )


def get_user_orders(
    db_path: str,
    authenticated_user_id: int,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Order]:
    """Return one page of orders for the *authenticated* user.

    ``authenticated_user_id`` MUST come from the verified session, never from
    the request body, query string or a client-supplied header. Passing a
    request-supplied id here reintroduces an authorization bypass: the caller
    would be able to read any user's orders.

    Raises:
        ValueError: ``status``, ``limit`` or ``offset`` is invalid.
        OrderQueryError: the database could not be read.
    """
    if not isinstance(authenticated_user_id, int) or isinstance(authenticated_user_id, bool):
        raise ValueError(
            "authenticated_user_id must be an int from the session, got "
            f"{type(authenticated_user_id).__name__}"
        )

    normalised_status: Optional[str] = None
    if status is not None:
        normalised_status = status.strip().lower()
        if normalised_status not in ALLOWED_STATUSES:
            # Do not echo the raw value back to the client; log it, report the allowed set.
            logger.warning(
                "orders.query.rejected_status user_id=%s status=%r",
                authenticated_user_id,
                status,
            )
            raise ValueError(
                "unknown order status: must be one of "
                + ", ".join(sorted(ALLOWED_STATUSES))
            )

    if not isinstance(limit, int) or limit < 1:
        raise ValueError(f"limit must be a positive integer, got {limit!r}")
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"offset must be zero or a positive integer, got {offset!r}")
    limit = min(limit, MAX_PAGE_SIZE)

    sql = "SELECT id, amount, status FROM orders WHERE user_id = ?"
    params: list[object] = [authenticated_user_id]
    if normalised_status is not None:
        sql += " AND status = ?"
        params.append(normalised_status)
    # Stable ordering, otherwise paging can repeat or skip rows.
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    try:
        with closing(sqlite3.connect(db_path, timeout=DB_TIMEOUT_SECONDS)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
    except sqlite3.Error:
        # Log the internals; return a message that leaks neither path nor schema.
        logger.exception(
            "orders.query.failed user_id=%s status=%s limit=%d offset=%d db=%s",
            authenticated_user_id,
            normalised_status,
            limit,
            offset,
            db_path,
        )
        raise OrderQueryError("could not read orders, please retry") from None

    return [
        Order(
            id=row["id"],
            amount=_to_decimal(row["amount"], field="amount", order_id=row["id"]),
            status=row["status"],
        )
        for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, rounded half-up to the cent.

    Returns ``None`` for an empty sequence: the average of no orders is
    undefined, and returning 0.00 would be indistinguishable from a real
    average of zero-amount orders. Callers must handle ``None``.
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), start=Decimal("0"))
    # Round once, at the end. Rounding per-order would compound the error.
    return (total / Decimal(len(orders))).quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, discount_pct: Decimal) -> Decimal:
    """Subtract ``discount_pct`` percent from ``amount``.

    ``discount_pct`` is expressed in percentage points: 15 means 15%, not 0.15.
    The discount is rounded half-up to the cent before subtraction, so the
    returned amount is always an exact currency value.

    Raises:
        ValueError: negative amount, or a percentage outside 0-100.
    """
    amount = _to_decimal(amount, field="amount")
    discount_pct = _to_decimal(discount_pct, field="discount_pct")

    if amount < 0:
        raise ValueError(f"amount must not be negative, got {amount}")
    if not (Decimal("0") <= discount_pct <= Decimal("100")):
        raise ValueError(
            "discount_pct must be between 0 and 100 percentage points, got "
            f"{discount_pct} (note: 15% is 15, not 0.15)"
        )

    discount = (amount * discount_pct / Decimal("100")).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    # The range check above already guarantees this, but a pricing bug must
    # never reach the customer as a negative charge.
    return max(amount - discount, Decimal("0.00"))


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """Render one receipt line, with the amount at exactly two decimal places."""
    amount = order.amount.quantize(CENT, rounding=ROUND_HALF_UP)
    return f"Order #{order.id}: {currency_symbol}{amount:.2f}"
```