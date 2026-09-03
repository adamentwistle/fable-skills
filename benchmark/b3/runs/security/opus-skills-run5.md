Reviewed statically — I didn't run it. Two of these crash on every call, one is a straight SQL injection, and the money handling is wrong throughout.

## get_user_orders

**1. SQL injection — critical.** `user_id` and `status` come from the request and are interpolated into the query string. `status = "x' OR '1'='1"` returns every order in the table; `x'; DROP TABLE orders; --` doesn't work through `execute` (single statement only) but `UNION SELECT` against other tables does, and that is enough to exfiltrate the whole database. Fix: `?` placeholders, values passed as the second argument to `execute`.

**2. No authorization on the object — critical.** `user_id` is taken from the request, so any authenticated caller can read any other customer's orders by changing one number. This is the classic insecure-direct-object-reference. The fix is in the HTTP handler, not here: derive `user_id` from the session, and never accept it as a request parameter. I've kept the parameter in the corrected code but documented the contract, because the fix has to happen at the call site.

**3. Connection is never closed — high.** No `close()`, no context manager, and an exception in `execute` leaks it outright. Under a request-per-call HTTP handler this accumulates file handles until the garbage collector happens to run. Fix: `contextlib.closing`, or try/finally.

**4. A wrong `db_path` silently creates an empty database — high.** `sqlite3.connect` creates the file if it doesn't exist. A typo in config gives you an empty database and an empty result list, not an error — the worst failure mode, silent wrong behavior that looks like "this customer has no orders". Fix: open read-only through a `file:...?mode=ro` URI, which fails loudly instead of creating.

**5. `status` is not checked against an allowlist — medium.** Even parameterized, an arbitrary string reaches the query and quietly returns nothing. Fix: validate against a known set of statuses and raise on anything else.

**6. Unbounded result set — medium.** `fetchall` with no `LIMIT` loads every matching row into memory. A bulk-buying account or a scripted test user turns one request into hundreds of megabytes. Fix: `LIMIT`/`OFFSET` with a capped page size.

**7. Raw `sqlite3` errors reach the HTTP handler — medium.** An `OperationalError` message contains table and column names and sometimes the file path. If the handler renders exception text, that's an information leak, and if it doesn't, the operator gets no context about which user and status failed. Fix: catch `sqlite3.Error`, wrap in a module exception with the query context, chain the cause with `from e`.

**8. Rows come back as positional tuples — medium.** `o[1]` and `order[0]` are spread across three functions. Reorder the `SELECT` columns and every caller silently changes meaning with no error. Fix: `sqlite3.Row` plus a small frozen dataclass.

**9. Read-write connection with no busy timeout — low.** The function only reads, but takes a connection that could write, and will raise immediately if a writer holds the lock. Fix: `mode=ro` (same change as #4) and an explicit `timeout`.

**10. Quoting an integer id as a string — low.** `user_id = '5'` only matches an integer `5` because SQLite applies INTEGER affinity from the column. If `orders.user_id` is `TEXT` or has no declared type, the comparison silently fails to match. Disappears once the value is bound as a parameter with its real type.

## average_order_value

**11. `ZeroDivisionError` on an empty list — high.** This is not an exotic input: `get_user_orders` returns `[]` for any customer with no orders in that status, which is the common case. The handler 500s. Fix: decide the empty policy explicitly — I return `None`, so the caller must render "no orders" rather than a fake `0.00`.

**12. Money accumulated in binary floats — high.** `0.1 + 0.2 != 0.3`. Summing many order amounts drifts, and the drift depends on row order. Fix: `Decimal`, converted from the database value via `str()` so the float never enters the arithmetic.

**13. `total = 0.0` breaks the moment amounts are Decimal — medium.** `float + Decimal` raises `TypeError`, so anyone who fixes the storage layer breaks this function. Fix: start from `Decimal("0")`.

**14. A NULL amount raises a bare `TypeError` — medium.** `None` in the `amount` column gives `unsupported operand type(s) for +=: 'float' and 'NoneType'`, with nothing identifying the bad row. Fix: reject it with a message naming the order id.

**15. No rounding policy on the result — low.** An average of cents is rarely representable in cents, and the function returns whatever precision falls out. Fix: quantize once, with the policy named.

## apply_discount

**16. `pct` is not range-checked — high.** `pct=150` returns a negative price, which downstream becomes a credit to the customer; `pct=-20` raises the price. Either one is a live money bug reachable from a promo-code table. Fix: require `0 <= pct <= 100` and a non-negative amount.

**17. No rounding — high.** `100.00` at `12.5%` gives `87.5`, and `89.99` at `15%` gives `76.4915` — a price with sub-cent precision that gets stored or charged. Fix: quantize to the cent once, at the end, with a stated policy (I chose ROUND_HALF_UP; switch the one constant to ROUND_DOWN if the rule is "never overcharge").

**18. The unit of `pct` is ambiguous — medium.** Nothing says whether 15% is `15` or `0.15`, and both are accepted silently — `0.15` just applies a 0.15% discount and nobody notices. Fix: document it as percentage points, and validate. The precedence in the original expression is fine, incidentally: it evaluates as `amount - ((amount * pct) / 100)`.

## format_receipt

**19. `TypeError` on every call — critical.** `order[0]` is an integer id from the database, and `"Order #" + 1` raises `TypeError: can only concatenate str (not "int") to str`. This function cannot ever have been executed. Fix: an f-string.

**20. Money rendered with `str()` — high.** `str(10.5)` is `"10.5"`, not `"10.50"`, and a float that has been through arithmetic prints as `"76.49149999999999"`. On a customer-facing receipt. Fix: format the Decimal to exactly two places.

**21. Hardcoded `$`, no locale — low.** Fine for a single-currency store; becomes a correctness bug the day a second currency appears. Fix: take the symbol as a parameter, defaulted.

**22. No guard on tuple shape — low.** A short row gives `IndexError` with no context. Disappears with the dataclass from #8.

## Cross-cutting

**23. No type hints or docstrings — low.** In a module that mixes ints, floats, and percentages, the signatures carry no information about units or types.

**24. Nothing is logged — low.** No record of which user, status, or database path was involved when a query fails.

**25. SQLite for an e-commerce orders service — low, worth flagging.** Writers block readers in the default journal mode; enable WAL, or plan the move to a server database before write volume matters. Opening a fresh connection per request is also unpooled overhead.

## Corrected code

```python
"""Read-only access to customer orders, plus money helpers.

Money policy
------------
All amounts are ``Decimal`` in major units: ``Decimal("10.50")`` is $10.50.
Values read from SQLite are converted through ``str()`` so that a REAL column
cannot contaminate the arithmetic with binary-float error. The durable fix is
to store integer minor units (cents); until that migration lands, this module
is the boundary where the conversion happens.

Rounding policy: ROUND_HALF_UP to the cent, applied once at the end of a
calculation and never mid-formula. If the business rule becomes "never
overcharge the customer", change ``_ROUNDING`` to ``ROUND_DOWN`` here and
nowhere else.

Authorization contract
----------------------
``get_user_orders`` does NOT authorize. The caller must pass a ``user_id``
derived from the authenticated session, never one taken from the request
body, query string, or path. Passing a client-supplied id makes every
customer's order history readable by every other customer.
"""

from __future__ import annotations

import logging
import pathlib
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, DecimalException, ROUND_HALF_UP
from typing import Optional, Sequence

log = logging.getLogger(__name__)

# Server-side allowlist. A status that is not in here is a bug or an attack,
# never an empty result set.
ALLOWED_STATUSES = frozenset(
    {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
)

_CENT = Decimal("0.01")
_ROUNDING = ROUND_HALF_UP

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000
_DB_TIMEOUT_SECONDS = 5.0


class OrderStoreError(Exception):
    """The orders database could not be reached or queried."""


class OrderDataError(Exception):
    """A row in the orders table is not usable (bad or missing amount)."""


@dataclass(frozen=True)
class Order:
    id: int
    amount: Decimal
    status: str


def _to_money(raw: object, order_id: object) -> Decimal:
    """Convert a database amount to Decimal, naming the row if it is unusable."""
    if raw is None:
        raise OrderDataError(
            f"orders.amount is NULL for order id={order_id}; "
            "every order row must carry an amount"
        )
    try:
        # str() first: Decimal(0.1) captures the float's error, Decimal("0.1")
        # does not.
        return Decimal(str(raw))
    except (DecimalException, ValueError) as exc:
        raise OrderDataError(
            f"orders.amount is not numeric for order id={order_id}: {raw!r}"
        ) from exc


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    """Open the orders database read-only.

    Uses a file: URI with mode=ro so a wrong path raises instead of silently
    creating an empty database — the plain connect() default would return
    "no orders" for a typo in configuration.
    """
    path = pathlib.Path(db_path).resolve()
    try:
        conn = sqlite3.connect(
            f"{path.as_uri()}?mode=ro", uri=True, timeout=_DB_TIMEOUT_SECONDS
        )
    except sqlite3.Error as exc:
        raise OrderStoreError(
            f"cannot open orders database at {path} read-only: {exc}; "
            "check the configured db_path exists and is readable"
        ) from exc
    conn.row_factory = sqlite3.Row
    return conn


def get_user_orders(
    db_path: str,
    user_id: int,
    status: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
) -> list[Order]:
    """Return one page of a user's orders in the given status.

    ``user_id`` must come from the authenticated session — see the module
    docstring. Ordering is by id so that paging is stable.
    """
    # bool is a subclass of int; True would silently query user_id = 1.
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError(
            f"get_user_orders: user_id must be an int, got {type(user_id).__name__}"
        )
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"get_user_orders: unknown status {status!r}; allowed: "
            + ", ".join(sorted(ALLOWED_STATUSES))
        )
    if not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(
            f"get_user_orders: limit must be an int in 1..{MAX_PAGE_SIZE}, got {limit!r}"
        )
    if not isinstance(offset, int) or offset < 0:
        raise ValueError(
            f"get_user_orders: offset must be a non-negative int, got {offset!r}"
        )

    sql = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )
    try:
        with closing(_connect_read_only(db_path)) as conn:
            rows = conn.execute(sql, (user_id, status, limit, offset)).fetchall()
    except sqlite3.Error as exc:
        # Wrapped so the raw driver message — which names tables, columns and
        # the file path — never reaches an HTTP response body.
        log.exception(
            "orders query failed user_id=%s status=%s limit=%s offset=%s",
            user_id,
            status,
            limit,
            offset,
        )
        raise OrderStoreError(
            f"orders query failed for user_id={user_id} status={status!r}: {exc}"
        ) from exc

    return [
        Order(id=row["id"], amount=_to_money(row["amount"], row["id"]), status=row["status"])
        for row in rows
    ]


def average_order_value(orders: Sequence[Order]) -> Optional[Decimal]:
    """Mean order amount, rounded to the cent, or None when there are no orders.

    None rather than 0.00 deliberately: an average of nothing is not zero, and
    the caller should render "no orders" rather than a plausible-looking price.
    """
    if not orders:
        return None
    total = Decimal("0")
    for order in orders:
        total += order.amount
    # Divide first, round once — rounding per-item would compound the error.
    return (total / Decimal(len(orders))).quantize(_CENT, rounding=_ROUNDING)


def apply_discount(amount: Decimal, pct: Decimal) -> Decimal:
    """Apply a percentage discount and round to the cent.

    ``pct`` is in percentage points: 15 means 15%, not 0.15. Both arguments
    accept int or Decimal; float is rejected because it silently reintroduces
    binary-float error into a price.
    """
    for name, value in (("amount", amount), ("pct", pct)):
        if isinstance(value, float):
            raise TypeError(
                f"apply_discount: {name} must be Decimal or int, not float "
                f"(got {value!r}); floats cannot represent money exactly"
            )
        if not isinstance(value, (Decimal, int)) or isinstance(value, bool):
            raise TypeError(
                f"apply_discount: {name} must be Decimal or int, "
                f"got {type(value).__name__}"
            )
    amount = Decimal(amount)
    pct = Decimal(pct)
    if amount < 0:
        raise ValueError(f"apply_discount: amount must not be negative, got {amount}")
    if not Decimal(0) <= pct <= Decimal(100):
        raise ValueError(
            f"apply_discount: pct must be between 0 and 100 percentage points, "
            f"got {pct} (note: 15% is 15, not 0.15)"
        )
    discounted = amount - (amount * pct / Decimal(100))
    return discounted.quantize(_CENT, rounding=_ROUNDING)


def format_receipt(order: Order, currency_symbol: str = "$") -> str:
    """One receipt line, with the amount at exactly two decimal places."""
    amount = order.amount.quantize(_CENT, rounding=_ROUNDING)
    return f"Order #{order.id}: {currency_symbol}{amount:,.2f}"
```

Two things this does not fix, deliberately. The authorization hole (#2) has to be closed in the HTTP handler by taking `user_id` from the session — I've documented the contract and validated the type, but the module cannot enforce it. And amounts are still stored as SQLite `REAL`; converting through `str()` at read time stops the error growing, but two orders of `$0.1` that were stored as floats were already imprecise before this code saw them. The real fix is an `INTEGER` cents column and a migration.