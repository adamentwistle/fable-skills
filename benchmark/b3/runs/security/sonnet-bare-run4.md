## Issues found

**Critical — SQL injection.** `query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` builds the query by string interpolation. Any request-controlled `user_id` or `status` (e.g. `' OR '1'='1`) lets an attacker read or manipulate arbitrary rows. Fix: use parameterized queries (`?` placeholders), never string-format user input into SQL.

**High — no authorization check (IDOR).** `user_id` comes straight from the request with nothing verifying it matches the authenticated caller. As written, any logged-in user can pass someone else's `user_id` and read their orders. Fix: the HTTP handler must derive `user_id` from the authenticated session, not trust a client-supplied value — or explicitly check the requester owns that `user_id`.

**High — `format_receipt` crashes.** `order[0]` is an int (the id); `"Order #" + order[0]` raises `TypeError: can only concatenate str`. Fix: `str(order[0])`.

**High — connection/cursor never closed.** `conn`/`cur` leak on every call, and leak worse on any exception since there's no `try/finally` or context manager. Under load this exhausts file handles/connections. Fix: use `with` / `contextlib.closing`.

**Medium — unbounded result set.** No `LIMIT`/pagination — a user with a huge order history returns everything in one call, unbounded memory/response size. Fix: add a `LIMIT`/offset parameter.

**Medium — `average_order_value` divides by zero.** Empty `orders` list raises `ZeroDivisionError`. Fix: guard and return `0.0` (or `None`) for empty input.

**Medium — money formatted inconsistently.** `str(order[1])` gives `"$10.0"` instead of `"$10.00"`, and floating-point money is prone to rounding artifacts (`0.1 + 0.2` style errors) in `average_order_value`/`apply_discount`. Fix: format to 2 decimals for display; ideally store/compute money as `Decimal` or integer cents rather than `float`.

**Medium — `apply_discount` doesn't validate `pct`.** Negative `pct` increases the price; `pct > 100` produces a negative price. `amount` isn't validated either. Fix: raise `ValueError` outside `0 <= pct <= 100` (and reject negative `amount`).

**Low — raw DB errors propagate to the HTTP layer.** No `try/except` around `execute`/`fetchall`; a `sqlite3.Error` bubbles up unsanitized, which can leak internals in an error response. Fix: catch `sqlite3.Error`, log it, raise/return a sanitized error.

**Low — `status` not validated against a known set.** Not a security issue once parameterized, but a typo'd status silently returns zero rows with no feedback. Consider validating against an allowed-status enum/list.

## Corrected code

```python
import sqlite3
from contextlib import closing
from decimal import Decimal

ALLOWED_STATUSES = {"pending", "paid", "shipped", "cancelled", "refunded"}


def get_user_orders(db_path, user_id, status, limit=100, offset=0):
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ? "
        "ORDER BY id LIMIT ? OFFSET ?"
    )
    try:
        with closing(sqlite3.connect(db_path)) as conn, closing(conn.cursor()) as cur:
            cur.execute(query, (user_id, status, limit, offset))
            return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError("failed to fetch orders") from e


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    total = sum(Decimal(str(o[1])) for o in orders)
    return total / len(orders)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not (0 <= pct <= 100):
        raise ValueError("pct must be between 0 and 100")
    return amount - amount * Decimal(str(pct)) / 100


def format_receipt(order):
    order_id, amount, _status = order
    return f"Order #{order_id}: ${Decimal(str(amount)):.2f}"
```

Note: this still assumes `user_id` reaching `get_user_orders` has already been authorized against the caller's session — that check belongs in the HTTP handler, not this module, but it must exist somewhere before this code runs.