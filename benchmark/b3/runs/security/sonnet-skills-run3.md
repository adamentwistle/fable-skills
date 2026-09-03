Found 13 issues, two critical (SQL injection, a crash-on-every-call bug). Full list, then corrected code.

**1. SQL injection — critical.** `query = "... = '%s' AND status = '%s'" % (user_id, status)` builds SQL from unvalidated HTTP input. Any request can read or exfiltrate the whole `orders` table (e.g. `status = 'x' OR '1'='1'`), and depending on driver settings can chain further statements. Fix: parameterized query (`?` placeholders), never string interpolation.

**2. `format_receipt` crashes on every call — critical/correctness.** `"Order #" + order[0]` — `order[0]` is the `id` column, an int. Concatenating `str + int` raises `TypeError`. This isn't an edge case, it's the only case. Fix: `str(order[0])`.

**3. Division by zero in `average_order_value` — high.** Empty order list (a user with no orders — a completely normal state) raises `ZeroDivisionError`, which will 500 the handler. Fix: return `None` (or raise a named exception the caller handles) when `orders` is empty.

**4. Money stored/handled as float — high (data integrity).** `amount` arithmetic uses plain floats throughout (`total`, `apply_discount`). Floats can't represent currency exactly (`0.1 + 0.2 != 0.3`); summed over many orders this drifts into visibly wrong totals. Fix: use `decimal.Decimal` for all amount arithmetic, quantized to 2 places at the boundary.

**5. Connection/cursor never closed — medium (resource leak).** No `try/finally` or `with`, and if `execute` raises, the connection leaks. Note: `with sqlite3.connect(...)` only commits/rolls back on exit — it does **not** close the connection, a common gotcha. Fix: explicit `try/finally` calling `conn.close()`.

**6. No exception handling around DB access — medium.** A malformed query, locked DB, or missing file raises an unhandled exception that will surface as a raw traceback in the HTTP response, leaking internals (schema, file paths). Fix: catch `sqlite3.Error`, log it, raise a sanitized application-level error.

**7. `status` not validated against an allowlist — medium (defense in depth).** Even parameterized, passing through arbitrary status strings means typos/garbage silently return zero rows instead of a clear 400. Fix: check `status` against a fixed set of valid statuses before querying.

**8. `user_id` not validated/typed — medium.** Should be an int (or whatever the ID type is); passing a non-numeric string should be rejected at the boundary with a clear error, not silently queried. Fix: `int(user_id)` with a caught `ValueError` → 400.

**9. `apply_discount` accepts any `pct` — medium.** Negative `pct` inflates the price instead of discounting; `pct > 100` produces a negative amount. Neither is caught. Fix: validate `0 <= pct <= 100`, raise `ValueError` otherwise.

**10. `average_order_value` breaks on `NULL` amount — low.** If any `amount` column is `NULL`, `total += None` raises `TypeError`. Fix: treat `NULL` as invalid data — either filter it out explicitly or fail loudly with a clear message, not a bare `TypeError`.

**11. No `LIMIT`/pagination — low (DoS/perf).** A user with a very large order history returns the entire table in one response. Fix: add `LIMIT`/`OFFSET` params with a sane default cap.

**12. `format_receipt` doesn't format currency — low.** `str(order[1])` can print `$19.9` or float noise like `$19.900000000000002`. Fix: format with 2 fixed decimals off the `Decimal`.

**13. New DB connection opened per call, no reuse — low (perf, not a bug).** Fine for correctness, worth noting if this is called per-order-row rather than per-request — flagging so it's a conscious choice, not fixed below since scope is unclear.

```python
import sqlite3
from decimal import Decimal, InvalidOperation

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled", "refunded"}
MAX_ORDERS_PER_QUERY = 500


def get_user_orders(db_path, user_id, status, limit=MAX_ORDERS_PER_QUERY):
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValueError(f"invalid user_id: {user_id!r}, must be an integer")

    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status!r}, must be one of {sorted(VALID_STATUSES)}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, amount, status FROM orders "
            "WHERE user_id = ? AND status = ? "
            "ORDER BY id LIMIT ?",
            (user_id, status, limit),
        )
        rows = cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError("failed to fetch orders") from e
    finally:
        conn.close()

    orders = []
    for row_id, amount, row_status in rows:
        if amount is None:
            raise ValueError(f"order {row_id} has NULL amount")
        orders.append((row_id, Decimal(str(amount)), row_status))
    return orders


def average_order_value(orders):
    if not orders:
        return None
    total = sum((o[1] for o in orders), Decimal("0"))
    return total / Decimal(len(orders))


def apply_discount(amount, pct):
    if not (0 <= pct <= 100):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    return (amount - amount * pct / Decimal(100)).quantize(Decimal("0.01"))


def format_receipt(order):
    order_id, amount, _status = order
    return f"Order #{order_id}: ${amount.quantize(Decimal('0.01'))}"
```

Note: `amount` is converted via `Decimal(str(amount))` rather than `Decimal(amount)` directly — sqlite returns amounts as Python floats, and constructing a `Decimal` straight from a float bakes in the float's binary rounding error; routing through `str()` avoids that.