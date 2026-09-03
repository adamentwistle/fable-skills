## Review

**Critical — SQL injection.** `user_id` and `status` are formatted straight into the query string with `%s`, and both come from the HTTP request. A `status` of `x' OR '1'='1` dumps every order in the table; `'; DROP TABLE orders; --` is limited only because `cur.execute` refuses multiple statements — `executescript` or a UNION-based read would not be. Fix: use bound parameters (`WHERE user_id = ? AND status = ?`) and pass the values as a tuple. Never build SQL by string formatting.

**Critical — no authorization (IDOR).** Even with parameters fixed, `user_id` arrives from the request, so any caller can read any other customer's orders by changing one number. Fix: take the user id from the authenticated session, not the request; if the endpoint legitimately accepts a target user id (admin view), compare it against the requester and reject a mismatch.

**High — the database connection is never closed.** No `close()`, no context manager, and an exception in `execute` leaks it too. Under HTTP load this exhausts file handles and holds SQLite locks. Fix: wrap in `contextlib.closing`. Note that `with sqlite3.connect(...) as conn:` does *not* fix this — that context manager commits or rolls back the transaction and leaves the connection open. This is the usual wrong fix.

**High — `average_order_value` raises `ZeroDivisionError` on an empty list.** A user with no orders in the requested status is the normal case, and it returns `[]`. Fix: check for empty first and return `None` so the caller can distinguish "no orders" from "average of zero" — returning `0.0` silently conflates them.

**High — `format_receipt` crashes on every call.** `"Order #" + order[0]` concatenates a `str` with the `id` column, which SQLite returns as an `int`, giving `TypeError: can only concatenate str (not "int") to str`. Fix: use an f-string.

**High — `apply_discount` accepts any percentage.** `pct=150` returns a negative amount; `pct=-20` silently *increases* the charge. Neither is rejected, and a negative order total flowing into a payment or refund path is a real financial bug. Fix: validate `0 <= pct <= 100` and raise `ValueError` otherwise. Also reject negative `amount`.

**Medium — money is handled as binary floats.** `total = 0.0`, `amount * pct / 100`, and float accumulation across many orders all introduce representation error, and `apply_discount` returns unrounded values like `89.99999999999999`. Fix: use `decimal.Decimal` and quantize to cents with `ROUND_HALF_UP` at each boundary. The stronger fix, if you control the schema, is to store amounts as integer cents.

**Medium — `status` is not validated.** Any string is accepted and silently returns an empty list, so a typo in the client looks identical to a customer with no orders. Fix: check against an explicit allow-list of known statuses and raise on anything else.

**Medium — `sqlite3.connect` creates the database if the file is missing.** A wrong or mistyped `db_path` produces an empty database and then "no such table" — or, if the schema is auto-created elsewhere, an empty result set with no error at all. Fix: open read-only via a `file:...?mode=ro` URI, which fails loudly when the file does not exist. This also prevents any write reaching the database through this path.

**Medium — a `NULL` amount raises `TypeError` in the sum.** `total += None` fails, and one bad row breaks the whole aggregate. Fix: decide explicitly — either enforce `NOT NULL` on the column, or raise a clear error naming the offending order id. Do not coerce `NULL` to zero; that hides missing money.

**Medium — rows are read by tuple position.** `o[1]` and `order[0]` depend on the `SELECT` column order. Add a column to that query and every caller silently reads the wrong field with no exception. Fix: set `conn.row_factory = sqlite3.Row` and map into a `NamedTuple`, so access is by name and the shape is checked once.

**Medium — the result set is unbounded.** `fetchall()` loads every matching order into memory. A customer with a large history, or an injected predicate, becomes a memory-exhaustion vector. Fix: add `LIMIT` with a caller-supplied cap, and paginate.

**Medium — receipt amounts are formatted with `str()`.** An amount of `12.5` prints as `$12.5`, and `12.10` as `$12.1`. Fix: format to exactly two decimal places.

**Medium — no `ORDER BY`.** SQLite may return rows in any order, so receipt listings and any future pagination are non-deterministic. Fix: order by a stable column such as `id`.

**Low — a new connection is opened on every request.** Fine at low volume, wasteful at scale. Consider a per-thread or per-request connection managed by the web framework.

**Low — database errors propagate raw to the handler.** An unhandled `sqlite3.OperationalError` can surface the database path or schema in a 500 response or logs. Fix: catch at the handler boundary, log internally, return a generic error.

**Low — `average_order_value` calls `len()` on its argument.** Passing a generator raises `TypeError`. Fix: materialize with `list()` first.

**Low — no type hints or docstrings, and currency is hardcoded to `$`.** Worth addressing if this service ever handles more than one currency; the currency should come from the order, not the formatter.

**Performance note:** confirm an index exists on `orders(user_id, status)`. Without it this is a full table scan on every request.

## Corrected code

```python
"""Order lookup and receipt helpers for the orders service."""

from __future__ import annotations

from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, NamedTuple, Optional
import sqlite3

ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)
DEFAULT_LIMIT = 500
MAX_LIMIT = 1000
CENTS = Decimal("0.01")


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def _money(value) -> Decimal:
    """Convert a stored amount to Decimal.

    Goes via str() deliberately: Decimal(float) inherits the binary
    floating-point error we are trying to avoid.
    """
    return Decimal(str(value))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def get_user_orders(
    db_path: str | Path,
    user_id: int,
    status: str,
    *,
    requester_id: int,
    limit: int = DEFAULT_LIMIT,
) -> list[Order]:
    """Return one user's orders in the given status.

    `requester_id` must be the authenticated user from the session, never a
    request parameter. `user_id` may only differ from it for callers that have
    passed an admin check upstream.
    """
    if user_id != requester_id:
        raise PermissionError(
            f"user {requester_id} may not read orders for user {user_id}"
        )

    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown order status: {status!r}")

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError(f"invalid user_id: {user_id!r}") from None

    limit = max(1, min(int(limit), MAX_LIMIT))

    # Read-only URI: fails if the file is missing instead of creating an empty
    # database, and blocks any write through this path.
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, amount, status FROM orders "
            "WHERE user_id = ? AND status = ? "
            "ORDER BY id "
            "LIMIT ?",
            (user_id, status, limit),
        ).fetchall()

    orders = []
    for row in rows:
        if row["amount"] is None:
            raise ValueError(f"order {row['id']} has a NULL amount")
        orders.append(Order(row["id"], _money(row["amount"]), row["status"]))
    return orders


def average_order_value(orders: Iterable[Order]) -> Optional[Decimal]:
    """Mean order amount, or None when there are no orders.

    None rather than zero, so callers can tell "no orders" apart from
    "orders totalling nothing".
    """
    orders = list(orders)
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal("0"))
    return _round_money(total / len(orders))


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Reduce `amount` by `pct` percent, rounded to cents."""
    amount = _money(amount)
    pct = _money(pct)

    if amount < 0:
        raise ValueError(f"amount must not be negative: {amount}")
    if not (Decimal("0") <= pct <= Decimal("100")):
        raise ValueError(f"discount percent must be between 0 and 100: {pct}")

    return _round_money(amount - (amount * pct / Decimal("100")))


def format_receipt(order: Order) -> str:
    return f"Order #{order.id}: ${_round_money(order.amount):,.2f}"
```

The two changes that must not be dropped in review are the bound parameters and the `requester_id` check. Everything else degrades quality; those two are the difference between a customer reading their own orders and reading everyone's.