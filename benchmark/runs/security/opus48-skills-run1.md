<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: Benchmark treatment (with skills). Content below the line is the agent's final output, unmodified. -->

---

# Code Review: `orders` module

I reviewed all four functions against security, correctness, robustness, data-integrity, and numerical-care lenses. Findings below, ordered by severity, each with a concrete fix. Corrected code follows.

---

## Findings

### CRITICAL

**C1 — SQL injection in `get_user_orders` (security).**
`query = "... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)` concatenates request-controlled values directly into SQL. A `status` of `x' OR '1'='1` dumps every order; `'; DROP TABLE orders;--` (via a multi-statement path or a stacked-query-capable driver) is catastrophic. This is the textbook trust-boundary violation — user input must be *parameterized, never concatenated*.
**Fix:** use `?` placeholders and pass values as the second arg to `execute`:
```python
cur.execute("SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?", (user_id, status))
```

**C2 — Division by zero in `average_order_value` (correctness / numerical-care).**
`total / len(orders)` raises `ZeroDivisionError` when `orders` is empty. A user with no orders (or a filtered query returning zero rows — the common path straight out of `get_user_orders`) crashes the handler. Every `/` needs a denominator-zero plan.
**Fix:** guard the empty case and return a defined value (documented policy) before dividing.

### HIGH

**H1 — Broken object-level authorization / IDOR (security).**
`user_id` comes from the request and is used verbatim as the filter. Any authenticated caller can pass someone else's `user_id` and read their orders. Never trust a client-supplied identity field — the WHO must be derived server-side from the session/token, not accepted from the request.
**Fix:** the HTTP handler must pass the *authenticated* user id, not a request parameter. Enforce and document this at the function boundary (reject a mismatch, or take the session id only). I've added a type/ownership guard and a docstring contract in the corrected code; the real fix lives in the caller.

**H2 — Connection leak in `get_user_orders` (robustness).**
`conn = sqlite3.connect(...)` is never closed. On both the success path and any exception, the connection (and its file handle / lock) leaks. Under load this exhausts handles and holds SQLite locks.
**Fix:** use a `with closing(...)` / `try/finally` to guarantee close.

**H3 — Money stored/computed as binary float (numerical-care).**
`total = 0.0` accumulation, and `apply_discount`'s float arithmetic, use binary floats for currency. This drifts (`0.1 + 0.2 != 0.3`) and accumulates into accounting discrepancies. Money must be integer cents or `Decimal`.
**Fix:** use `Decimal`, converting DB values via `Decimal(str(x))` (or ideally store cents as integers). Flagging that the schema itself likely needs `amount` as INTEGER cents or a fixed-precision type — outside this file but worth raising.

**H4 — `TypeError` in `format_receipt` (correctness — guaranteed crash).**
`"Order #" + order[0]` concatenates a `str` with `order[0]`, which is the `id` (an integer from the DB). This raises `TypeError: can only concatenate str (not "int") to str` on *every* call.
**Fix:** `str(order[0])`, and format the amount to 2 decimals.

### MEDIUM

**M1 — No allowlist validation of `status` (security / robustness).**
Even parameterized, `status` is an unbounded free-text value from the client. It should be validated against a server-side allowlist of known statuses; unexpected values should be rejected loudly, not silently returned as an empty result set.
**Fix:** validate `status in ALLOWED_STATUSES`, raise `ValueError` otherwise.

**M2 — No validation of `pct` range in `apply_discount` (data-integrity).**
`pct` is unbounded: a negative `pct` *increases* the charge, `pct &gt; 100` produces a negative total (a refund/credit the system never intended), and a non-numeric `pct` raises deep in arithmetic. Boundary values (0, 100) and out-of-range must be handled deliberately.
**Fix:** validate `0 &lt;= pct &lt;= 100`; reject otherwise.

**M3 — No rounding policy on discount result (numerical-care).**
`apply_discount` returns an unrounded value, producing fractional cents (e.g. `19.99 * 7 / 100`). Rounding is a policy decision and must be applied once at the boundary.
**Fix:** `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)` (state the policy; match codebase convention if one exists).

**M4 — Unsanitized DB errors leak to the caller (error-message-quality / security).**
Any `sqlite3` error (bad path, locked db, missing table) propagates raw to the HTTP handler, potentially exposing the DB path, SQL, and stack trace to the client.
**Fix:** catch `sqlite3.Error`, log the internals (with the identifiers) for operators, and raise a sanitized, user-safe error that chains the original cause (`raise ... from e`).

### LOW

**L1 — Unbounded result set / no `LIMIT` (robustness).**
`fetchall()` loads every matching row into memory. For a pathological account this is a large allocation. Consider a `LIMIT`/pagination. Low because per-user order counts are usually bounded.

**L2 — Fragile positional tuple indexing (`o[1]`, `order[0]`, `order[1]`) (robustness).**
Indexing assumes column order/presence; a nullable `amount` yields `None` → `TypeError` in the sum. `sqlite3.Row` (dict-like access) is more robust and self-documenting.
**Fix:** set `conn.row_factory = sqlite3.Row` and access by name; skip/handle `None` amounts.

**L3 — `average_order_value` empty-list return semantics undocumented (edge-case-sweep).**
Whatever the fix for C2, the "average of zero orders" answer (0? null? error?) is a real policy choice the caller must know. State it explicitly.

---

## Corrected code

```python
import logging
import sqlite3
from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# Server-side allowlist — reject anything not on it (M1).
ALLOWED_STATUSES = frozenset({"pending", "paid", "shipped", "delivered", "cancelled", "refunded"})

CENT = Decimal("0.01")


def get_user_orders(db_path, user_id, status):
    """Return (id, amount, status) rows for one user.

    SECURITY CONTRACT: `user_id` MUST be the authenticated caller's id, derived
    server-side from the session/token by the HTTP handler — NEVER a raw request
    parameter. Passing a client-supplied user_id is an IDOR vulnerability (H1).
    """
    # Validate identity type (H1) and status against an allowlist (M1).
    if not isinstance(user_id, int):
        raise ValueError(f"user_id must be an int, got {type(user_id).__name__}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unknown order status {status!r}; expected one of {sorted(ALLOWED_STATUSES)}")

    try:
        # Guaranteed close (H2).
        with closing(sqlite3.connect(db_path)) as conn:
            conn.row_factory = sqlite3.Row  # name-based access (L2)
            with closing(conn.cursor()) as cur:
                # Parameterized — no string interpolation (C1).
                cur.execute(
                    "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ? LIMIT 1000",
                    (user_id, status),  # LIMIT caps result size (L1)
                )
                return cur.fetchall()
    except sqlite3.Error as e:
        # Log internals for operators; raise a sanitized, chained error (M4).
        logger.exception("order query failed for user_id=%s status=%s db=%s", user_id, status, db_path)
        raise RuntimeError(f"could not load orders for user {user_id}") from e


def average_order_value(orders):
    """Mean order amount as a Decimal rounded to cents.

    Policy: an empty order list returns Decimal('0.00') (C2/L3). Change to raise
    if callers should treat "no orders" as an error instead.
    """
    if not orders:                       # denominator-zero guard (C2)
        return Decimal("0.00")

    total = Decimal("0")
    count = 0
    for o in orders:
        amount = o["amount"]
        if amount is None:               # tolerate nullable amount (L2)
            continue
        total += Decimal(str(amount))    # Decimal money, no float drift (H3)
        count += 1

    if count == 0:
        return Decimal("0.00")
    return (total / count).quantize(CENT, rounding=ROUND_HALF_UP)  # round once (M3)


def apply_discount(amount, pct):
    """Apply a percentage discount to a money amount, rounded to cents.

    pct is a percentage in [0, 100].
    """
    pct = Decimal(str(pct))
    if not (Decimal("0") &lt;= pct &lt;= Decimal("100")):   # range validation (M2)
        raise ValueError(f"discount pct must be between 0 and 100, got {pct}")

    amount = Decimal(str(amount))                      # Decimal money (H3)
    discounted = amount - (amount * pct / Decimal("100"))
    return discounted.quantize(CENT, rounding=ROUND_HALF_UP)  # deliberate rounding (M3)


def format_receipt(order):
    """Format a single (id, amount, status) row as a receipt line."""
    order_id = order["id"]
    amount = Decimal(str(order["amount"])).quantize(CENT, rounding=ROUND_HALF_UP)
    return f"Order #{order_id}: ${amount}"           # str() conversion fixes the crash (H4)
```

### Notes on scope

- **H1 (authorization)** cannot be fully fixed inside this function — the real fix is in the HTTP handler, which must pass the session-derived user id, never the request parameter. I added a boundary guard and a hard contract in the docstring; verify the call site.
- **H3** ultimately points at the schema: if `orders.amount` is a float/REAL column, it should be integer cents (or a fixed-precision type). The `Decimal(str(...))` conversions here contain the damage but don't cure the storage root cause — raising that for the data owners.
- If the codebase already has an established money type or rounding convention, match it rather than introducing `Decimal` ad hoc; I chose `ROUND_HALF_UP` as an explicit, common default.
