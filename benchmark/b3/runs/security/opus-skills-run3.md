Two critical problems (SQL injection and no authorization check), plus four high-severity bugs, three of which crash on ordinary inputs. `format_receipt` cannot run at all against a normal integer order id.

This is a static read of the snippet — I did not execute anything, and I do not have the `orders` schema, so two findings rest on stated assumptions (marked below).

## Trust boundaries in this code

| Source | Sink | Control needed |
|---|---|---|
| `user_id` (HTTP request) | SQL `WHERE` | Do not accept from the client at all — derive from the session |
| `status` (HTTP request) | SQL `WHERE` | Parameter placeholder + server-side allowlist |
| `db_path` (caller) | `sqlite3.connect` | Must come from config, never a request value |
| `amount`, `id` (database rows) | arithmetic, receipt string | Type and NULL validation on read |

## Findings

**1. SQL injection — critical.** `query = "... user_id = '%s' AND status = '%s'" % (user_id, status)` interpolates two request-controlled strings straight into SQL. A `status` of `x' OR '1'='1` returns every order in the table; `x'; DROP TABLE orders--` is blocked only by `execute`'s single-statement rule, and `executescript` or a UNION SELECT against `sqlite_master` is not. Fix: `?` placeholders with a parameter tuple. Never build SQL by concatenation or `%`.

**2. Missing authorization (IDOR) — critical.** `user_id` arrives from the request and is used verbatim as the ownership filter, so any authenticated caller can read any other user's orders by changing one number. Parameterizing the query does not fix this. Fix: take the id from the authenticated session, not the request; if an admin path genuinely needs other users' orders, that path gets its own explicit permission check.

**3. `average_order_value` raises `ZeroDivisionError` on an empty list — high.** A user with no orders in that status is an ordinary case, not an error, and it currently 500s. Fix: return `None` for empty input so callers can distinguish "no orders" from "average of zero". Returning `0` would be wrong — it is a real value that reports and thresholds would act on.

**4. `format_receipt` always raises `TypeError` — high.** `"Order #" + order[0]` concatenates `str` and `int`. Assuming `orders.id` is an INTEGER column (standard for a rowid primary key), this function has never worked. Fix: f-string interpolation. If `id` is TEXT in your schema, this one is inert — check the schema.

**5. Money held in binary floats — high, data integrity.** `total = 0.0`, `total += o[1]`, and `amount * pct / 100` all use floats. Summing many order values drifts, and `0.1 + 0.2 != 0.3` means computed totals will not compare equal to stored ones. Fix: integer minor units (cents) everywhere, `Decimal` for intermediate division. The corrected code assumes `orders.amount` is INTEGER cents; if it is REAL dollars in the live schema, that is a schema bug to fix before shipping, and the code below raises loudly rather than silently truncating.

**6. `apply_discount` accepts any `pct` — high.** `pct = -50` raises the price by 50%; `pct = 150` returns a negative amount that becomes a refund downstream; `pct = None` raises `TypeError`. Fix: validate `0 <= pct <= 100` and reject non-numeric input with a message naming the bad value.

**7. Connection leaked on every call — high.** `conn` is never closed and there is no `try/finally`. Under request load this exhausts file descriptors, and on an exception mid-query the connection leaks immediately. Fix: `contextlib.closing`. Note that `with sqlite3.connect(...) as conn` does **not** close — it is a transaction context manager, a common trap.

**8. No rounding policy on the discount — medium.** `amount - amount * pct / 100` on 1999 cents at 15% gives 1699.15 — a fraction of a cent that propagates into ledgers and fails reconciliation. Fix: round the *discount* once, half-up, to whole cents, then subtract, so `discount + final == amount` exactly. State the policy in a comment; if the business rule is "never overcharge", round the discount up instead.

**9. `status` is not validated against an allowlist — medium.** Any string reaches the query. After parameterization it merely returns empty results, which surfaces to the user as "you have no orders" instead of "that is not a status" — a silent wrong answer. Fix: a server-side `frozenset` of known statuses, rejected with a 400.

**10. Unbounded `fetchall()` — medium.** A bulk-order account pulls its whole history into memory in one request. Fix: `LIMIT`/`OFFSET` with a capped page size.

**11. Raw `sqlite3.Error` escapes to the HTTP handler — medium.** The exception text can carry the database file path and SQL fragments into a 500 page. Fix: catch `sqlite3.Error`, log it with the stack and the query parameters, and re-raise a domain error whose message is safe to show.

**12. `str(order[1])` renders money wrong — medium.** Produces `$12.5` or `$12.340000000000001`, never `$12.50`. Fix: format minor units explicitly as `units.cents` with two digits.

**13. A NULL `amount` crashes with an opaque `TypeError` — medium.** `total += o[1]` on `None` gives `unsupported operand type(s)` with no order id. Fix: validate on read and log the offending order id.

**14. Positional tuple indices couple three functions invisibly — medium.** `o[1]` and `order[0]` silently break if the `SELECT` column order changes; nothing fails at edit time. Fix: a frozen dataclass.

**15. No logging anywhere — medium.** Nothing records the query, its outcome, or failures, so an incident here is undebuggable. Fix: log the failure path with `user_id`, `status`, and the exception.

**16. `sqlite3.connect` creates a missing database file — medium.** A typo in `db_path` yields a fresh empty database and "no such table: orders" rather than "database not found", and the read path holds a writable handle it does not need. Fix: open read-only via `file:...?mode=ro` with `uri=True`.

**17. Status matching is case-sensitive — low.** `"Shipped"` silently returns nothing. Fix: normalize to lowercase before the allowlist check.

**18. Currency symbol is hardcoded to `$` — low.** Fine for a single-market service; a parameter costs nothing.

**19. No type hints or docstrings — low.** The units of `amount` and `pct` (cents or dollars, `15` or `0.15`) are unknowable from the signatures, which is exactly how unit-mismatch bugs get in.

**20. Receipt output is not HTML-escaped — low.** Currently safe because both fields are numeric, but it becomes an XSS if a future field carries user text into an HTML template. Escape at the render site, not here.

Two behaviour changes below need caller updates: `apply_discount` now returns a `DiscountResult` pair rather than a single number, and `average_order_value` returns `None` instead of raising on an empty list.

## Corrected code

```python
"""Order lookup and money arithmetic for the orders service.

Money is integer minor units (cents) throughout. The `orders.amount`
column is assumed to be INTEGER cents; if the live schema stores REAL
dollars, fix the schema first -- `_to_minor_units` below refuses to
truncate silently.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)
MAX_PAGE_SIZE = 200

_ORDERS_SQL = (
    "SELECT id, amount, status FROM orders "
    "WHERE user_id = ? AND status = ? "
    "ORDER BY id LIMIT ? OFFSET ?"
)


class OrderLookupError(Exception):
    """The orders store could not be read. Message is safe to show a user."""


@dataclass(frozen=True)
class Order:
    id: int
    amount_minor: int  # cents
    status: str


@dataclass(frozen=True)
class DiscountResult:
    discount_minor: int
    final_minor: int  # discount_minor + final_minor == original amount, exactly


def _is_int(value: object) -> bool:
    # bool is an int subclass; True must not pass as an id or an amount.
    return isinstance(value, int) and not isinstance(value, bool)


def _read_only_uri(db_path: str) -> str:
    # mode=ro also means a missing file errors instead of being created.
    return f"{Path(db_path).resolve().as_uri()}?mode=ro"


def _to_minor_units(amount: object, order_id: object, user_id: int) -> int:
    """Validate a raw `amount` column value as integer minor units."""
    if amount is None:
        logger.error(
            "order has NULL amount: order_id=%s user_id=%s", order_id, user_id
        )
        raise OrderLookupError("could not read orders right now")
    if not _is_int(amount):
        # A float here means the schema stores dollars, not cents. Truncating
        # would quietly lose money, so fail instead.
        logger.error(
            "order amount is not integer minor units: order_id=%s user_id=%s type=%s",
            order_id,
            user_id,
            type(amount).__name__,
        )
        raise OrderLookupError("could not read orders right now")
    return amount


def get_user_orders(
    db_path: str,
    requester_id: int,
    status: str,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    """Return one page of the *authenticated caller's* orders in `status`.

    `requester_id` MUST come from the verified session, never from the
    request body or query string -- it is the only ownership check here.
    `db_path` must come from configuration, never from a request.
    """
    if not _is_int(requester_id):
        raise TypeError(
            "requester_id must be the authenticated user's int id, got "
            f"{type(requester_id).__name__}"
        )
    status_key = status.strip().lower() if isinstance(status, str) else ""
    if status_key not in VALID_STATUSES:
        raise ValueError(
            f"unknown order status {status!r}; expected one of "
            f"{sorted(VALID_STATUSES)}"
        )
    if not _is_int(limit) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be an int in 1..{MAX_PAGE_SIZE}, got {limit!r}")
    if not _is_int(offset) or offset < 0:
        raise ValueError(f"offset must be a non-negative int, got {offset!r}")

    try:
        with closing(
            sqlite3.connect(_read_only_uri(db_path), uri=True, timeout=5.0)
        ) as conn:
            rows = conn.execute(
                _ORDERS_SQL, (requester_id, status_key, limit, offset)
            ).fetchall()
    except sqlite3.Error as exc:
        logger.exception(
            "orders query failed: user_id=%s status=%s limit=%s offset=%s",
            requester_id,
            status_key,
            limit,
            offset,
        )
        raise OrderLookupError("could not read orders right now") from exc

    return [
        Order(
            id=row_id,
            amount_minor=_to_minor_units(amount, row_id, requester_id),
            status=row_status,
        )
        for row_id, amount, row_status in rows
    ]


def average_order_value(orders) -> Decimal | None:
    """Mean order value in minor units, or None when there are no orders.

    Rounding policy: half-up to whole minor units. Callers needing exact
    figures should sum `amount_minor` and divide themselves.
    """
    orders = list(orders)  # tolerate a generator; len() would fail on one
    if not orders:
        return None
    total = sum(o.amount_minor for o in orders)
    return (Decimal(total) / Decimal(len(orders))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )


def apply_discount(amount_minor: int, pct) -> DiscountResult:
    """Apply a percentage discount to an amount in minor units.

    `pct` is a percentage, so 15 means 15% -- not 0.15. Rounding policy:
    the discount is rounded half-up to whole minor units once, then
    subtracted, so discount + final always equals the input exactly.
    """
    if not _is_int(amount_minor) or amount_minor < 0:
        raise ValueError(
            f"amount_minor must be a non-negative int of minor units, got {amount_minor!r}"
        )
    try:
        pct_dec = Decimal(str(pct))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"pct must be a number between 0 and 100, got {pct!r}") from exc
    if not Decimal(0) <= pct_dec <= Decimal(100):
        raise ValueError(f"pct must be between 0 and 100 inclusive, got {pct!r}")

    discount = int(
        (Decimal(amount_minor) * pct_dec / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return DiscountResult(discount_minor=discount, final_minor=amount_minor - discount)


def format_minor_units(amount_minor: int, currency_symbol: str = "$") -> str:
    """Render minor units as currency, e.g. -1999 -> '-$19.99'."""
    sign = "-" if amount_minor < 0 else ""
    units, cents = divmod(abs(amount_minor), 100)
    return f"{sign}{currency_symbol}{units:,}.{cents:02d}"


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """Plain-text receipt line. Escape at the render site if this reaches HTML."""
    return (
        f"Order #{order.id}: "
        f"{format_minor_units(order.amount_minor, currency_symbol)}"
    )
```

Worth checking before you merge: the actual column type of `orders.amount` and whether `orders.user_id` is indexed — the added `ORDER BY id LIMIT` makes an unindexed `user_id` noticeably worse under load.