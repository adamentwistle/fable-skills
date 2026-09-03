## Issues

**Critical — SQL injection.** `query` is built with `%` string formatting from `user_id` and `status`, which come straight off an HTTP request. A `status` of `x' OR '1'='1` dumps every order in the table; `'; DROP TABLE orders; --` is blocked only by `execute` refusing multiple statements, but `UNION SELECT` against other tables is not. Fix: parameterized query with `?` placeholders and a tuple of values. Never interpolate into SQL.

**Critical — no authorization check.** `user_id` is taken from the request and used to select orders. If the HTTP handler passes the requested user ID rather than the authenticated session's user ID, any logged-in user reads anyone's orders (an insecure direct object reference). Fix: the handler must pass the session user's ID, or this function must take the caller's identity and verify it matches. I can't see the handler, so verify this — parameterizing the query does nothing for it.

**High — `format_receipt` crashes on every call.** `"Order #" + order[0]` concatenates a `str` with the `id` column, which SQLite returns as an `int`. That is a `TypeError`, unconditionally. Fix: f-string.

**High — connection leak.** `conn` is never closed and there's no `try`/`finally`. Every request leaks a connection and a file handle until garbage collection; under load this exhausts file descriptors and holds locks on the database file. Fix: `contextlib.closing`. Note that plain `with sqlite3.connect(...)` does *not* close the connection — it only wraps a transaction. That's a common wrong fix.

**High — division by zero.** `average_order_value` computes `total / len(orders)` with no empty check. A user with no orders in that status returns `[]` from the query above, and this raises `ZeroDivisionError` → HTTP 500. Fix: return `None` for empty input and let the caller decide how to render it.

**High — `apply_discount` accepts any percentage.** `pct=150` returns a negative amount; `pct=-50` raises the price. If `pct` ever reaches this from request data or a promo-code table, a negative total is a refund. Fix: reject anything outside 0–100, and reject negative `amount`.

**High — type mismatch will silently return zero rows.** SQLite compares by storage class, so the text `'5'` does not equal the integer `5`. The original code quoted the value so it compared as text; once you parameterize, a `user_id` arriving as a string from the request compares as TEXT against an INTEGER column and matches nothing — no error, just an empty list. Fix: coerce with `int(user_id)` before binding.

**Medium — money is handled as binary floats.** `total = 0.0` and `amount * pct / 100` accumulate representation error; `0.1 + 0.2` is not `0.3`. Summed over many orders, averages and discounted totals drift from the ledger. Fix: `Decimal`, quantized to two places with `ROUND_HALF_UP`. The stronger fix is storing amounts as integer cents in the schema; convert via `Decimal(str(x))`, never `Decimal(float)`.

**Medium — no rounding to cents.** `apply_discount` can return `19.999999999999998`. Fix: quantize the result.

**Medium — no currency formatting.** `str(order[1])` renders `1.5` as `$1.5`, not `$1.50`. Fix: `:,.2f`.

**Medium — `status` is unvalidated.** Any string reaches the database. Not exploitable once parameterized, but it turns typos into silent empty results instead of a 400. Fix: check against an allowlist.

**Medium — a NULL `amount` crashes the sum.** `total += o[1]` raises `TypeError` if the column is NULL. Fix: validate on read, at the boundary, so the failure names the bad row.

**Medium — unbounded result set.** `fetchall()` with no `LIMIT` loads a customer's entire order history into memory and into the response. Fix: `LIMIT`/`OFFSET` with a server-side cap.

**Low — positional tuple indexing.** `o[1]` and `order[0]` break silently and wrongly if the `SELECT` column order ever changes. Fix: `sqlite3.Row` and a `NamedTuple`.

**Low — a wrong `db_path` creates an empty database.** `sqlite3.connect` creates the file if it's missing, so a typo surfaces as "no such table: orders" rather than "database not found". Fix: connect with `?mode=rw` in a URI so a missing file fails loudly.

**Low — no `ORDER BY`.** Row order is unspecified without one, so paginated results can repeat or skip rows.

## Corrected code

```python
"""Order queries and money helpers for the orders service."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, NamedTuple

VALID_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)
MAX_ORDERS = 500
CENTS = Decimal("0.01")


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def _to_money(value) -> Decimal:
    """Convert a stored amount to a 2dp Decimal. Never construct from a float."""
    if value is None:
        raise ValueError("order amount is NULL")
    try:
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
    except ArithmeticError as exc:
        raise ValueError(f"invalid amount: {value!r}") from exc


def get_user_orders(
    db_path: str,
    user_id: int,
    status: str,
    limit: int = MAX_ORDERS,
    offset: int = 0,
) -> list[Order]:
    """Return one user's orders in a given status.

    The caller MUST pass the authenticated session's user id, not a user id
    taken from the request, or this is an IDOR.
    """
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("user_id must be an integer") from None
    if status not in VALID_STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    limit = max(1, min(int(limit), MAX_ORDERS))
    offset = max(0, int(offset))

    uri = f"file:{db_path}?mode=rw"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cur:
            cur.execute(
                "SELECT id, amount, status FROM orders "
                "WHERE user_id = ? AND status = ? "
                "ORDER BY id LIMIT ? OFFSET ?",
                (user_id, status, limit, offset),
            )
            return [
                Order(row["id"], _to_money(row["amount"]), row["status"])
                for row in cur
            ]


def average_order_value(orders: Iterable[Order]) -> Decimal | None:
    """Mean order value, or None when there are no orders."""
    amounts = [_to_money(o.amount) for o in orders]
    if not amounts:
        return None
    total = sum(amounts, Decimal("0"))
    return (total / len(amounts)).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount, pct) -> Decimal:
    """Reduce amount by pct percent. pct must be in [0, 100]."""
    amount = _to_money(amount)
    pct = Decimal(str(pct))
    if amount < 0:
        raise ValueError("amount must not be negative")
    if not Decimal("0") <= pct <= Decimal("100"):
        raise ValueError("pct must be between 0 and 100")
    return (amount - amount * pct / 100).quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${_to_money(order.amount):,.2f}"
```

Two things changed shape for callers: `average_order_value` now returns `None` instead of raising on an empty list, and both it and `apply_discount` return `Decimal` rather than `float`. The database-level fix I'd still push for is storing amounts as integer cents, which removes the float round-trip entirely.