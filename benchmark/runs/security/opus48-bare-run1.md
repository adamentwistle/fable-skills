<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: Benchmark control (no skills). Content below the line is the agent's final output, unmodified. -->

---

This is a self-contained review task — the code is provided inline and I was told not to edit files, so no repo exploration is needed. Here is my review.

---

# Code Review: orders service module

## Issues

### 1. SQL injection via string-formatted query — CRITICAL
`get_user_orders` builds the query with `%`-formatting of `user_id` and `status`, both of which come straight from the HTTP request. A `status` of `x' OR '1'='1` dumps every order; `'; DROP TABLE orders;--` (or a UNION to read other tables) is equally reachable. Wrapping the values in quotes does nothing — the attacker just closes the quote.
**Fix:** Use a parameterized query with `?` placeholders and pass values as a tuple to `cur.execute`. Never interpolate user input into SQL text.

### 2. Database connection is never closed — HIGH
`conn = sqlite3.connect(...)` has no `close()`, no `try/finally`, and no context manager. Every call leaks a connection/file handle; under HTTP load this exhausts file descriptors and eventually breaks the service. If `cur.execute` raises, the leak is guaranteed.
**Fix:** Wrap in `contextlib.closing(...)`. Note the SQLite gotcha: `with sqlite3.connect(...) as conn:` manages the *transaction* (commit/rollback) but does **not** close the connection — you still need `closing()` (or an explicit `finally: conn.close()`).

### 3. `format_receipt` raises `TypeError` on every call — HIGH
`"Order #" + order[0]` concatenates a `str` with an `int` (the `id` column), which raises `TypeError: can only concatenate str (not "int") to str`. This function is currently broken for all valid rows.
**Fix:** Use an f-string (or `str(order[0])`).

### 4. `average_order_value` divides by zero on empty input — HIGH
`total / len(orders)` raises `ZeroDivisionError` when `orders` is `[]` — which is exactly what `get_user_orders` returns when a user has no orders in that status (a normal, common case).
**Fix:** Guard the empty case and return `0` (or `None`) before dividing.

### 5. No allowlist / validation of `status` — MEDIUM
Even after parameterizing (#1), `status` is an unvalidated free-form string from the request. Parameterization stops injection, but an invalid status silently returns an empty result set, masking client bugs and enabling scanning behavior.
**Fix:** Validate `status` against an explicit allowlist of known statuses and reject anything else with a 4xx/`ValueError`. Defense in depth plus clearer errors.

### 6. Money handled as binary `float` — MEDIUM
`total += o[1]`, `amount * pct / 100`, etc. operate on floats. Binary floating point can't represent decimal currency exactly (e.g. `0.1 + 0.2`), so totals, averages, and discounts drift by fractions of a cent and fail to reconcile — a data-integrity problem for an orders/billing system.
**Fix:** Use `decimal.Decimal` for monetary values (and ideally store amounts as integer cents or NUMERIC in the DB).

### 7. `apply_discount` doesn't validate `pct` — MEDIUM
Nothing constrains `pct`. A negative `pct` *increases* the price; `pct &gt; 100` produces a negative amount (effectively paying the customer). If `pct` is ever request-derived, this is an abuse vector; even internally it's a correctness landmine.
**Fix:** Validate `0 &lt;= pct &lt;= 100` and raise on out-of-range values.

### 8. `average_order_value` / `format_receipt` don't handle `NULL` amounts — LOW
If the `amount` column is nullable, `o[1]` can be `None`; `total += None` raises `TypeError`, and `format_receipt` prints `$None`. 
**Fix:** Skip/treat `None` amounts explicitly, or enforce `NOT NULL` at the schema level.

### 9. Receipt amount isn't formatted as currency — LOW
`str(order[1])` renders values like `9.5` or `9.500000000001` rather than `9.50`.
**Fix:** Format with two decimal places (`f"${order[1]:.2f}"`).

### 10. No error handling around DB access — LOW
`sqlite3.Error` (locked DB, missing table, I/O error) propagates raw to the HTTP handler, potentially leaking internal details in a stack trace. Consider catching and translating to a clean error, and never surfacing raw DB exception text to the client.

---

## Corrected code

```python
import sqlite3
from contextlib import closing
from decimal import Decimal

# Defense in depth: reject unknown statuses before they reach the DB.
ALLOWED_STATUSES = {
    "pending", "paid", "shipped", "delivered", "cancelled", "refunded",
}


def get_user_orders(db_path, user_id, status):
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    query = (
        "SELECT id, amount, status FROM orders "
        "WHERE user_id = ? AND status = ?"
    )
    # closing() guarantees the connection is closed even on error;
    # `with sqlite3.connect(...)` alone would NOT close it.
    with closing(sqlite3.connect(db_path)) as conn:
        with closing(conn.cursor()) as cur:
            cur.execute(query, (user_id, status))
            return cur.fetchall()


def average_order_value(orders):
    amounts = [Decimal(str(o[1])) for o in orders if o[1] is not None]
    if not amounts:
        return Decimal("0")
    return sum(amounts) / len(amounts)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    if not (Decimal("0") &lt;= pct &lt;= Decimal("100")):
        raise ValueError(f"pct must be between 0 and 100, got {pct}")
    return amount - amount * pct / Decimal("100")


def format_receipt(order):
    amount = Decimal(str(order[1])) if order[1] is not None else Decimal("0")
    return f"Order #{order[0]}: ${amount:.2f}"
```

Notes on the corrected version:
- `user_id`/`status` are now bound parameters (#1) and `status` is allowlisted (#5).
- `closing()` guarantees no connection/cursor leak (#2).
- Empty-list and `None`-amount cases are handled (#4, #8).
- `Decimal` throughout for money (#6); `pct` range is validated (#7).
- `format_receipt` uses an f-string and 2-decimal formatting, fixing the `TypeError` and display (#3, #9).

If `amount` is stored as `float`/`REAL` in SQLite, the `Decimal(str(...))` conversions above avoid inheriting the binary-float noise; longer term, migrate the column to integer cents or `NUMERIC`.

---

**Model suitability:** This is a bounded review of a short, self-contained snippet — a well-scoped reasoning task with no large-context or agentic search demands. Opus 4.8 (1M context) handles it correctly but is heavier than necessary; Sonnet (without extended thinking) would have been an appropriate and more cost-effective choice for a review of this size. Extended thinking was not required here.
