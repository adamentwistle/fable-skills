## Review

**1. SQL injection — critical.** `get_user_orders` builds the query with `%` string formatting on `user_id` and `status`, both of which come straight from the HTTP request. `status = "x' OR '1'='1"` returns every order in the table for any user; `'; DROP TABLE orders; --` style payloads are only limited by `execute()` refusing multiple statements (use of `executescript` anywhere would remove even that). Fix: pass values as `?` placeholders so SQLite binds them as data, never as SQL text. Escaping or quote-doubling is not an acceptable alternative.

**2. No authorization check on `user_id` — high.** The function trusts a `user_id` supplied by the caller's request. If the handler passes the request parameter rather than the authenticated session's user, any logged-in user reads anyone else's orders (an insecure direct object reference). Fix: the handler must take `user_id` from the verified session, or this function must receive the session identity and compare. Add a test that asserts user A cannot fetch user B's orders.

**3. Connection and cursor are never closed — high.** On the success path the connection is dropped on the floor, and on an exception it leaks with the exception. In a long-running HTTP service this accumulates file handles and locks, and eventually produces "database is locked" errors. Fix: wrap in `contextlib.closing` or `try/finally`. Note that `with sqlite3.connect(...)` alone does **not** close the connection — it only manages the transaction.

**4. `format_receipt` crashes on every real row — high.** `"Order #" + order[0]` concatenates a string with the `id` column, which is an integer from an `INTEGER PRIMARY KEY`. That raises `TypeError: can only concatenate str (not "int") to str` on the first call. Fix: use an f-string.

**5. `average_order_value` raises `ZeroDivisionError` on an empty list — high.** A user with no orders in the requested status is a normal case, not an error, and `get_user_orders` returns `[]` for it. Fix: return `None` (or raise a domain-specific error) and make the caller decide how to render "no orders". Returning `0.00` is worse — it silently conflates "no orders" with "orders worth nothing".

**6. `apply_discount` accepts any percentage — high.** Nothing constrains `pct`. A negative value *increases* the charge; a value above 100 produces a negative amount, which downstream may turn into a refund or a credit. If `pct` is ever influenced by a request field or a coupon table, this is a direct financial exploit. Fix: validate `0 <= pct <= 100` and reject anything else; also reject negative `amount`.

**7. Money is handled as binary floats — medium, data integrity.** `total += o[1]`, the discount multiplication, and `str(order[1])` all use `float`. Sums drift (`0.1 + 0.2 == 0.30000000000000004`), and discounts produce fractions of a cent such as `19.994999999999997` that get truncated inconsistently at different points in the system. Fix: use `decimal.Decimal` with explicit `ROUND_HALF_UP` quantization to two places, and ideally store amounts as integer cents in the database. Never build a `Decimal` from a `float` — go through `str()`.

**8. `user_id` is compared as text — medium, correctness.** The original query wraps `user_id` in quotes, so the comparison is against a string. In SQLite, `WHERE user_id = '42'` does not match an `INTEGER` column holding `42` under normal type affinity rules — the query silently returns zero rows rather than erroring. Once parameterized, passing the raw request string has the same effect. Fix: coerce to `int` and reject non-numeric input with a 400-level error.

**9. `status` is not validated against known values — medium.** An unknown status silently returns an empty list, which looks identical to "this user has no such orders". Fix: check against an explicit allow-list and reject unknown values, so typos and probing surface as errors.

**10. `fetchall()` on an unbounded query — medium.** A user with a large order history loads the entire result set into memory in one go, and the response size is unbounded. Fix: add `LIMIT`/`OFFSET` with a server-side maximum, and sort deterministically (`ORDER BY id`) so pagination is stable.

**11. No error handling around the database call — medium.** `sqlite3.Error` propagates raw to the HTTP layer, where the message and stack trace may reach the client and disclose schema details. Fix: catch `sqlite3.Error`, log it with context, and raise a sanitized application-level error.

**12. Amounts are formatted with bare `str()` — medium.** `str(10.5)` gives `"$10.5"`, and small or large floats can render in scientific notation (`"$1e-05"`). On a receipt this is a customer-visible defect. Fix: format with two fixed decimal places.

**13. A new connection per call — low, performance.** Each request pays connection setup and gets no shared cache or prepared-statement reuse. Fix: inject a connection (or a pool/`threading.local` handle) from the caller. Related: `sqlite3.connect` has a default busy timeout of 5 seconds, worth setting explicitly, and connections are not safe to share across threads unless you handle `check_same_thread` deliberately.

**14. Rows are returned as bare tuples — low.** Every consumer hard-codes positional indexes (`o[1]`, `order[0]`), so adding a column to the `SELECT` in the wrong position silently corrupts `average_order_value` and `format_receipt` with no type error. Fix: return a `NamedTuple` or set `conn.row_factory`.

**15. Missing index — low, performance.** The `WHERE user_id = ? AND status = ?` filter needs a composite index on `(user_id, status)`, otherwise this is a full table scan that degrades as the table grows. Verify with `EXPLAIN QUERY PLAN`.

**16. `db_path` is unvalidated — low.** Not exploitable as written, since the handler supplies it, but if it ever becomes request-influenced it is arbitrary file access. Fix: keep it in configuration, never in a request.

**17. No type hints, docstrings, or tests — low.** Several bugs above (the `int`/`str` concatenation, the empty-list division) would have been caught by a type checker or a single unit test each.

## Corrected code

```python
"""Order queries and money helpers for the orders service.

Amounts are handled as Decimal throughout. Never introduce float
arithmetic into these paths -- binary floats cannot represent cents
exactly, and the error accumulates across sums and discounts.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import NamedTuple, Optional, Sequence

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = frozenset({
    "pending", "paid", "shipped", "delivered", "cancelled", "refunded",
})

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

CENTS = Decimal("0.01")


class OrderError(Exception):
    """Base class for errors this module raises."""


class InvalidInput(OrderError):
    """Caller supplied a value that failed validation. Map to HTTP 400."""


class OrderLookupFailed(OrderError):
    """The database call failed. Map to HTTP 500, without the detail."""


class Order(NamedTuple):
    id: int
    amount: Decimal
    status: str


def to_money(value: object) -> Decimal:
    """Convert a stored amount to a two-place Decimal.

    Goes through str() so a float from the database does not drag its
    binary representation error into the Decimal.
    """
    if value is None:
        raise InvalidInput("order amount is missing")
    try:
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidInput(f"order amount is not a number: {value!r}") from exc


def _validate_user_id(user_id: object) -> int:
    """Coerce a request-supplied user id to int, or reject it."""
    try:
        return int(user_id)
    except (TypeError, ValueError) as exc:
        raise InvalidInput("user_id must be an integer") from exc


def _validate_status(status: object) -> str:
    if not isinstance(status, str) or status not in ALLOWED_STATUSES:
        raise InvalidInput(f"unknown status: {status!r}")
    return status


def get_user_orders(
    conn: sqlite3.Connection,
    user_id: object,
    status: object,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a user's orders in the given status.

    The caller MUST pass the authenticated session's user id, not a
    user id taken from the request body or query string. This function
    performs no authorization of its own.
    """
    user_id = _validate_user_id(user_id)
    status = _validate_status(status)

    if not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise InvalidInput(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if not isinstance(offset, int) or offset < 0:
        raise InvalidInput("offset must be zero or greater")

    # Values are bound as parameters. Never interpolate them into the SQL.
    query = (
        "SELECT id, amount, status "
        "FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id "
        "LIMIT ? OFFSET ?"
    )

    try:
        with closing(conn.cursor()) as cur:
            cur.execute(query, (user_id, status, limit, offset))
            rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.exception("order lookup failed for user_id=%s status=%s", user_id, status)
        raise OrderLookupFailed("could not load orders") from exc

    return [Order(id=int(r[0]), amount=to_money(r[1]), status=str(r[2])) for r in rows]


def get_user_orders_from_path(
    db_path: str,
    user_id: object,
    status: object,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Open a short-lived connection and delegate to get_user_orders.

    Prefer injecting a shared connection in the request path; this
    wrapper exists for scripts and tests. db_path must come from
    configuration, never from a request.
    """
    with closing(sqlite3.connect(db_path, timeout=5.0)) as conn:
        return get_user_orders(conn, user_id, status, limit, offset)


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, or None when there are no orders.

    None means "undefined", not "zero". A caller rendering this must
    distinguish the two -- a user with no orders has not spent nothing,
    they have no average.
    """
    if not orders:
        return None
    total = sum((to_money(o.amount) for o in orders), Decimal("0"))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Reduce amount by pct percent, rounded to whole cents.

    Rejects percentages outside 0..100, so a bad coupon cannot inflate
    a charge or turn it into a credit.
    """
    amount = to_money(amount)
    if amount < 0:
        raise InvalidInput("amount must not be negative")

    try:
        pct = Decimal(str(pct))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidInput(f"pct is not a number: {pct!r}") from exc
    if not Decimal("0") <= pct <= Decimal("100"):
        raise InvalidInput("pct must be between 0 and 100")

    discounted = amount - (amount * pct / Decimal("100"))
    return discounted.quantize(CENTS, rounding=ROUND_HALF_UP)


def format_receipt(order: Order) -> str:
    """One receipt line for an order."""
    return f"Order #{order.id}: ${to_money(order.amount):,.2f}"
```

Two things to settle outside this file. Confirm that the HTTP handler passes the session's user id rather than the request's — issue 2 is the most damaging problem here after the injection, and it cannot be fixed inside this module. And check whether `orders.amount` is stored as `REAL`; if it is, migrate it to integer cents, since `to_money` only limits the damage rather than removing it.