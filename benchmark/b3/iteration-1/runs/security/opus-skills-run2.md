Nineteen issues. Three are guaranteed production failures, not edge cases.

I could not run anything this session — the Bash tool is disabled — so the corrected code below is unexecuted. Treat the behaviour claims as read-from-code, not observed.

## Critical

**1. SQL injection in `get_user_orders`.** `user_id` and `status` come straight off the HTTP request and are interpolated into the query string with `%`. Passing `status = "' OR '1'='1"` returns every order in the table for any user. A second statement via `'; DROP TABLE orders; --` is blocked only by `execute()` refusing multiple statements — `executescript` or a sqlite build with them enabled removes even that. Fix: parameterised query with `?` placeholders, values passed as the second argument to `execute`.

**2. No authorization check — anyone can read anyone's orders.** Even with placeholders, `user_id` is attacker-chosen. Incrementing it walks the whole customer base. This is the more valuable bug of the two, because fixing the injection does nothing for it. Fix: the handler must take the user id from the session, never the request body or query string. If an admin path genuinely needs to read another user's orders, it needs its own explicit role check on that specific object. I've documented the contract on the function, but the real fix lives in the caller.

**3. `format_receipt` raises `TypeError` on every call.** `order[0]` is the `id` column, an `INTEGER`, and `"Order #" + order[0]` is `str + int`: `TypeError: can only concatenate str (not "int") to str`. This function has never worked against real rows. Fix: f-string with explicit formatting.

## High

**4. `average_order_value` raises `ZeroDivisionError` on an empty list.** This is not a rare input — it is the normal result of filtering by a status the user has no orders in. `len(orders)` is zero and the division blows up in the handler. Fix: decide a policy and state it. I return `None` for "no orders", so the caller chooses how to display it; returning `0.0` would be a lie (an average of nothing is not zero).

**5. The database connection is never closed.** No `close()`, no `try/finally`, no context manager. Every request leaks a connection and a file handle until the garbage collector happens to run. Under load this exhausts file descriptors. Note the trap in the fix: `with sqlite3.connect(...) as conn` does *not* close the connection in `sqlite3` — it manages a transaction. You need `contextlib.closing`, or an explicit `finally`.

**6. `apply_discount` accepts any percentage, including ones that invert the sale.** `pct = 150` returns a negative amount, meaning you pay the customer. `pct = -20` silently raises the price by 20%. If `pct` ever comes from a coupon record, an admin form, or a promotions API, this is a money-loss bug. Fix: reject anything outside 0–100 with a specific error.

**7. Money is handled as binary floats throughout.** `total = 0.0`, `total += o[1]`, and `amount * pct / 100` all accumulate representation error — `0.1 + 0.2` is not `0.3`. Averages and discounts drift in the last cents, and totals computed in different orders disagree. Fix: `Decimal` end to end, with a single conversion at the database boundary.

That boundary conversion is a patch over a schema problem I am flagging rather than fixing: if `orders.amount` is a `REAL` column, the precision is already lost before this code sees it, and no amount of `Decimal` downstream recovers it. The real fix is storing integer minor units (cents) in an `INTEGER` column, or a `TEXT` decimal. That is a migration, outside this review's scope — but until it happens, the values here are approximate by construction.

## Medium

**8. `status` is not validated against an allowlist.** With placeholders the injection is gone, but an unknown status still silently returns an empty list, which the caller cannot distinguish from "no matching orders". Fix: check membership in a server-side `frozenset` of known statuses and raise a specific error. You will need to correct my list to match your schema — I guessed at the values.

**9. `fetchall()` is unbounded and unordered.** A customer with a large order history loads the entire result set into memory in one go, which is a cheap denial of service against a shared process. There is also no `ORDER BY`, so row order is whatever SQLite happens to produce — once you add paging on top of that, pages overlap and drop rows. Fix: `ORDER BY id` with `LIMIT`/`OFFSET` and a hard cap on page size.

**10. Database errors propagate raw to the HTTP layer, and nothing is logged.** An `OperationalError` carrying the schema or the database path can end up in a 500 response body. Meanwhile the operator gets no record of what failed. Fix: catch `sqlite3.Error`, log it with the stack trace and the identifiers you'd want at 3am (user id, status, path), and re-raise a domain error with a message safe to show a user, chaining the original with `from e`.

**11. Rows are raw tuples indexed by position.** `o[1]` and `order[0]` are coupled to the column order in the `SELECT` string. Add a column to that list and both functions read the wrong field with no error — a silent data bug. Fix: `sqlite3.Row` plus a small frozen dataclass.

**12. No rounding policy is stated anywhere.** `average_order_value` returns full float precision, `apply_discount` returns whatever the division produced. Fix: round once, at the boundary, with the policy named in code. I chose half-up on the discount amount. Note that this favours you, not the customer, by up to a cent — if your rule is "never overcharge", round the discount *up* instead. Pick deliberately; do not inherit my choice by default.

**13. A `NULL` amount crashes with no context.** If `orders.amount` is nullable, `total += None` raises a bare `TypeError` naming no order and no column. Fix: convert at the boundary and raise an error that names the offending value and type.

**14. `sqlite3.connect` creates an empty database on a wrong path.** A typo in `db_path` produces a fresh empty file, and the first symptom is `no such table: orders` — misleading, and it litters the filesystem. Fix: connect with a `file:...?mode=rw` URI so a missing file fails immediately and honestly.

**15. `pct` carries no unit.** Nothing says whether `15` or `0.15` means fifteen percent, and the two differ by 100×. Fix: document it as percentage points and validate the range, which makes `0.15` (a 0.15% discount) at least visible as suspicious rather than silently wrong.

## Low

**16. `str(order[1])` is not a money format.** It renders `12.5` as `"$12.5"` and a drifted float as `"$12.100000000000001"`. Fix: `:,.2f`.

**17. The dollar sign is hardcoded.** Fine for a single-currency service; a landmine the day you add a second. Worth a note in the code rather than a change now.

**18. No type hints or docstrings.** For a money module that other people will call, the signatures are the documentation.

**19. `user_id` is not type-checked.** A string `"7"` will not match an integer column in SQLite and returns an empty list rather than an error. Fix: require an `int` and reject `bool`, which is an `int` subclass.

## Corrected code

```python
"""Order queries and money formatting for the orders service.

Money is handled as Decimal throughout. See the module review: if
`orders.amount` is a REAL column, precision is already lost before this
module sees the value -- the durable fix is to store integer minor units.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional, Union

logger = logging.getLogger(__name__)

# Server-side allowlist: request-supplied status values are checked against this,
# never passed through. Correct these to match the orders schema.
VALID_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

CENTS = Decimal("0.01")

# Rounding policy: half-up, applied once, at the point a value is stored or
# displayed -- never mid-calculation. Applied to the discount amount, which
# favours the merchant by up to one cent. Switch to ROUND_UP on the discount
# if the business rule is "never overcharge".
ROUNDING = ROUND_HALF_UP

Money = Union[int, str, Decimal, float]


class OrderQueryError(RuntimeError):
    """The orders store could not be read. Safe to log; not safe to show a user."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal  # major units (e.g. dollars), exact
    status: str


def _to_decimal(value: Money, *, field: str = "amount") -> Decimal:
    """Convert a stored or supplied money value to Decimal at the boundary."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; never a money value
        raise TypeError(f"{field}: expected a number, got bool ({value!r})")
    if isinstance(value, (int, str)):
        return Decimal(value)
    if isinstance(value, float):
        # Stopgap for a REAL column: str() gives the shortest repr rather than
        # the full binary expansion. Precision was already lost on write.
        return Decimal(str(value))
    raise TypeError(
        f"{field}: expected int, str or Decimal, "
        f"got {type(value).__name__} ({value!r})"
    )


def get_user_orders(
    db_path: Union[str, Path],
    user_id: int,
    status: str,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of `user_id`'s orders with the given status, ordered by id.

    SECURITY: `user_id` must be the authenticated caller's id, taken from the
    session -- or an id the caller has been explicitly authorized to read.
    Passing a request-supplied user_id straight through makes every customer's
    orders readable by anyone who can increment an integer. This function
    cannot check that for you; the caller must.

    Raises ValueError for bad input (map to 400) and OrderQueryError for
    storage failures (map to 500 with a generic body).
    """
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError(
            f"user_id must be an int, got {type(user_id).__name__} ({user_id!r})"
        )
    if status not in VALID_STATUSES:
        raise ValueError(
            f"unknown order status {status!r}; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )
    if not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(
            f"limit must be an int in 1..{MAX_PAGE_SIZE}, got {limit!r}"
        )
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(f"offset must be a non-negative int, got {offset!r}")

    # mode=rw so a wrong path fails loudly instead of creating an empty database
    # whose first symptom is "no such table: orders".
    db_uri = Path(db_path).resolve().as_uri() + "?mode=rw"

    sql = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )

    try:
        # closing(), not `with sqlite3.connect(...)`: the connection's own
        # context manager commits or rolls back, it does not close.
        with closing(sqlite3.connect(db_uri, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            with closing(conn.cursor()) as cur:
                cur.execute(sql, (user_id, status, limit, offset))
                rows = cur.fetchall()
    except sqlite3.Error as exc:
        logger.exception(
            "orders query failed: user_id=%s status=%s limit=%s offset=%s db=%s",
            user_id, status, limit, offset, db_path,
        )
        raise OrderQueryError("could not read orders") from exc

    return [
        Order(
            id=row["id"],
            amount=_to_decimal(row["amount"], field=f"orders.amount (id={row['id']})"),
            status=row["status"],
        )
        for row in rows
    ]


def average_order_value(orders: Iterable[Order]) -> Optional[Decimal]:
    """Mean order amount, rounded to cents.

    Returns None for an empty sequence: the average of no orders is not zero,
    and the caller decides how to present "no data".
    """
    orders = list(orders)
    if not orders:
        return None
    total = sum((o.amount for o in orders), Decimal(0))
    return (total / Decimal(len(orders))).quantize(CENTS, rounding=ROUNDING)


def apply_discount(amount: Money, pct: Money) -> Decimal:
    """Apply a percentage discount and return the new amount, rounded to cents.

    `pct` is in percentage points: 15 means 15%, not 1500% and not 0.15%.
    """
    amount = _to_decimal(amount, field="amount")
    pct = _to_decimal(pct, field="pct")

    if amount < 0:
        raise ValueError(f"amount must not be negative, got {amount}")
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError(
            f"discount pct must be between 0 and 100 percentage points, got {pct}"
        )

    discount = (amount * pct / Decimal(100)).quantize(CENTS, rounding=ROUNDING)
    return (amount - discount).quantize(CENTS, rounding=ROUNDING)


def format_receipt(order: Order) -> str:
    """One receipt line. Single-currency: the '$' is hardcoded deliberately."""
    amount = order.amount.quantize(CENTS, rounding=ROUNDING)
    return f"Order #{order.id}: ${amount:,.2f}"
```

Three things to settle before this ships. The status allowlist is a guess and must match your schema. The rounding policy favours the merchant by up to a cent, which is a business decision, not a technical one. And `average_order_value` and `format_receipt` now take `Order` objects rather than tuples, so every existing caller needs updating — a grep for both names will find them.