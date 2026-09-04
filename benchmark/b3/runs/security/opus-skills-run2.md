## Review

Two of these crash on the first real call, and one hands over other users' orders. Everything else is money precision and hygiene.

**1. SQL injection — critical.** `user_id` and `status` are interpolated into the query string with `%`. A `status` of `x' OR '1'='1` dumps every order in the table; `'; DROP TABLE orders; --` is blocked only by sqlite3's one-statement-per-`execute` rule, which is luck, not a control. Fix: `?` placeholders with a parameter tuple, and never build SQL by concatenation anywhere in this module.

**2. No authorization check — critical.** `user_id` arrives from the request, so any authenticated caller can read any other user's orders by changing one number (broken object-level authorization). Parameterizing the query does not fix this. Fix: derive the user id from the session in the HTTP handler and pass that; if an admin path genuinely needs to query other users, gate it on an explicit role check at the handler and pass a separate flag. This is a handler change, not a change to this module — the corrected code below validates the id but cannot authorize it.

**3. `format_receipt` raises `TypeError` on every call — critical.** `"Order #" + order[0]` concatenates a `str` with the `id` column, which is an integer. This function cannot ever have run successfully. Fix: f-string.

**4. `average_order_value` raises `ZeroDivisionError` on an empty list — high.** An empty result set is the normal case for a user with no orders in that status, and `get_user_orders` returns `[]` freely. Fix: decide the policy explicitly — return `None` for "no data" (below) rather than `0.0`, which is a real average of zero and lies to the caller.

**5. Money held in binary floats — high.** `total = 0.0`, `total += o[1]`, and the discount arithmetic all use floats. `0.1 + 0.2 != 0.3`; summed over a few thousand orders the total drifts, and `apply_discount(19.99, 10)` returns `17.991000000000003`. Fix: `Decimal` throughout, converting once at the database boundary. See the unverified note below about the column's own type.

**6. `apply_discount` does not validate `pct` — high.** `pct=150` returns a negative amount, i.e. a refund; `pct=-10` silently marks the price *up*. Neither is rejected, and the negative case flows into a receipt as `$-9.99`. Fix: reject anything outside 0–100 with a specific error. Also settle the unit ambiguity — this code means percent (`15`), not fraction (`0.15`), so name and document it.

**7. No rounding policy — high.** The discount result carries sub-cent fractions into storage and display. Fix: round once, half-up, at the point the discount is computed, and again on formatting; never round mid-calculation.

**8. Connection is never closed — high.** No `close()`, no context manager, and an exception in `execute` leaks the handle. Under a request-per-call HTTP handler this exhausts file descriptors. Fix: `contextlib.closing`.

**9. A wrong `db_path` silently returns zero orders — medium.** `sqlite3.connect` creates the file if it does not exist, so a typo'd or unmounted path yields an empty database and an empty list instead of an error, which looks identical to "this user has no orders". Fix: connect with `?mode=ro` via a URI so a missing file raises.

**10. Raw database errors reach the HTTP layer — medium.** There is no `except`, so a `sqlite3.OperationalError` propagates with the table name, and often the file path, in its message. If the handler echoes exception text, that leaks schema and filesystem layout. Fix: catch `sqlite3.Error`, log the detail with the ids, raise a wrapped error whose message carries nothing internal.

**11. `status` is not validated — medium.** Even parameterized, an unrecognised status returns an empty list rather than a 400, so a client typo is indistinguishable from a genuine empty result. Fix: check against a server-side allowlist and reject.

**12. Unbounded `fetchall` — medium.** No `LIMIT`; a user with a large order history loads the whole set into memory per request. Fix: cap it, and log when the cap truncates so the silent-truncation case is visible.

**13. Non-deterministic row order — medium.** No `ORDER BY`, so results come back in whatever order the query plan produces, and pagination built on this later would drop or duplicate rows. Fix: `ORDER BY id`.

**14. `str(order[1])` formats money by accident — medium.** It produces `17.0`, `17.991`, or `1e-05` depending on the value. Fix: explicit two-decimal formatting.

**15. Positional tuple access couples every caller to column order — low.** `o[1]` breaks silently if anyone adds a column to the `SELECT`. Fix: a `NamedTuple`, which keeps `order[0]` working for existing callers while adding names.

**16. A `NULL` amount raises `TypeError` inside the sum — low.** Fix: the conversion helper below treats `NULL` as an error at the boundary, where the offending order id is still in scope, rather than mid-aggregation where it is not.

**17. `format_receipt` on a short tuple raises `IndexError` — low.** Covered by the `NamedTuple`.

**18. No type hints, docstrings, or tests — low.** For money-handling code the tests are the part that matters: the empty-list average, the 100%-discount boundary, and a discount whose exact result lands on a half-cent.

## Corrected code

```python
"""Order queries and receipt formatting for the orders service.

Money is handled as Decimal. Amounts are converted once, at the database
boundary, and rounded once, at the point a figure becomes a stored or
displayed value -- never mid-calculation.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import NamedTuple, Sequence
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Server-side allowlist. Replace with this service's real status vocabulary.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

MAX_ORDERS = 1000
CENTS = Decimal("0.01")


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


class OrderQueryError(RuntimeError):
    """The orders query could not be completed. Safe to show to a caller."""


def _to_decimal(value: object, *, field: str, order_id: object = None) -> Decimal:
    """Convert a database or caller-supplied number to Decimal.

    Floats go via str() so we get the shortest round-trip repr (17.99) rather
    than the full binary expansion (17.989999999999998).
    """
    where = f" for order {order_id}" if order_id is not None else ""
    if value is None:
        raise OrderQueryError(f"{field} is NULL{where}")
    try:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, int):
            return Decimal(value)
        if isinstance(value, float):
            return Decimal(str(value))
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OrderQueryError(f"{field} is not a number{where}: {value!r}") from exc


def get_user_orders(
    db_path: str | Path,
    user_id: int,
    status: str,
    limit: int = MAX_ORDERS,
) -> list[Order]:
    """Return one user's orders in a given status.

    `user_id` MUST come from the authenticated session, not from the request
    body or query string -- this function validates the id but cannot
    authorize it.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"user_id must be an integer, got {user_id!r}") from exc
    if uid <= 0:
        raise ValueError(f"user_id must be a positive integer, got {uid}")

    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"unknown order status {status!r}; "
            f"expected one of {sorted(ALLOWED_STATUSES)}"
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")

    # Read-only URI: a missing or unreadable file raises here instead of
    # silently creating an empty database and returning zero orders.
    uri = f"file:{quote(Path(db_path).resolve().as_posix(), safe='/:')}?mode=ro"

    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, amount, status FROM orders "
                "WHERE user_id = ? AND status = ? "
                "ORDER BY id LIMIT ?",
                (uid, status, limit + 1),  # +1 so we can detect truncation
            ).fetchall()
    except sqlite3.Error as exc:
        logger.exception(
            "orders query failed: user_id=%s status=%s db_path=%s", uid, status, db_path
        )
        raise OrderQueryError(f"could not read orders for user_id={uid}") from exc

    if len(rows) > limit:
        logger.warning(
            "orders query truncated: user_id=%s status=%s limit=%d",
            uid,
            status,
            limit,
        )
        rows = rows[:limit]

    return [
        Order(
            id=int(row["id"]),
            amount=_to_decimal(row["amount"], field="amount", order_id=row["id"]),
            status=str(row["status"]),
        )
        for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Decimal | None:
    """Mean order value, or None when there are no orders.

    None rather than 0: an average of zero is a real value and would be
    indistinguishable from "every order was free".
    """
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal(0))
    # Round once, at the end. The average is a display figure.
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal | int | str, pct: Decimal | int | str) -> Decimal:
    """Reduce `amount` by `pct` percent (15 means 15%, not 0.15).

    Rounding policy: the discount is rounded half-up to whole cents and then
    subtracted, so the returned amount is exact cents and the customer is
    never overcharged by more than half a cent.
    """
    amt = _to_decimal(amount, field="amount")
    rate = _to_decimal(pct, field="pct")

    if amt < 0:
        raise ValueError(f"amount must not be negative, got {amt}")
    if not (Decimal(0) <= rate <= Decimal(100)):
        raise ValueError(f"discount pct must be between 0 and 100, got {rate}")

    amt = amt.quantize(CENTS, rounding=ROUND_HALF_UP)
    discount = (amt * rate / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)
    return amt - discount


def format_receipt(order: Order) -> str:
    amount = order.amount.quantize(CENTS, rounding=ROUND_HALF_UP)
    return f"Order #{order.id}: ${amount}"
```

## Before you merge

Check the `amount` column's declared type: `sqlite3 orders.db ".schema orders"`. If it is `REAL`, the precision loss happens in storage, before this module sees it, and the `Decimal` conversion here only stops the drift getting worse. That column wants a migration to integer minor units or `TEXT`, which is a bigger change than this review covers.

Then grep for callers of all four functions. Two return types changed: `average_order_value` now returns `None` instead of raising on an empty list, and amounts are `Decimal` rather than `float`, so any caller doing `float_amount * 1.2` will raise a `TypeError`. Positional access (`order[0]`, `order[1]`) still works — the `NamedTuple` is deliberate for that reason.

I have not run any of this. I did not have the schema, the HTTP handler, the real status vocabulary, or the callers, so items 2, 5, 11 and the empty-database claim in item 9 are reasoned from the code as given, not observed. The tests worth writing first are the empty-order-list average, `apply_discount` at exactly 0 and 100 percent, and a discount landing on a half-cent (`apply_discount("10.05", 50)` should be `5.02`, discount `5.03` rounded up).