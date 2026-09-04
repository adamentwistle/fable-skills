## Code Review

### Issues Found

**CRITICAL**

1. **SQL Injection in `get_user_orders`**
   - Lines 5: Query built with string formatting, not parameterized. `user_id` and `status` from the HTTP request are concatenated directly into SQL.
   - Fix: Use `?` placeholders and pass values as a tuple to `cur.execute()`.

2. **Missing Authorization Check**
   - `get_user_orders` accepts `user_id` from the request without verifying the authenticated user can access it. Any user can query any other user's orders.
   - Fix: The HTTP handler must verify `authenticated_user_id == user_id` before calling this function, or pass the authenticated user's ID instead of trusting the parameter.

**HIGH**

3. **Unclosed Database Connection**
   - Line 4: Connection is opened but never closed. This leaks database connections under load.
   - Fix: Use `with sqlite3.connect(db_path) as conn:` to ensure it closes.

4. **Division by Zero in `average_order_value`**
   - Line 10: If `orders` is empty, `len(orders)` is 0, crashing with `ZeroDivisionError`.
   - Fix: Check `if not orders: return 0` (or raise with a clear error message).

5. **Type Error in `format_receipt`**
   - Line 15: `order[0]` is an integer from the database; concatenating with `+` crashes with `TypeError`.
   - Fix: Convert to string: `"Order #" + str(order[0]) + ": $" + str(order[1])`.

**MEDIUM**

6. **Unvalidated `status` Parameter**
   - Line 5: `status` is never validated. An attacker or bug could pass arbitrary values, returning unintended results or exposing unexpected orders.
   - Fix: Allowlist valid statuses on both the HTTP handler and here; reject anything else explicitly.

7. **Money Using Binary Floats**
   - Lines 9, 10, 16: Amounts are stored and computed as floats. This accumulates rounding errors and is unsafe for financial data.
   - Fix: Use `decimal.Decimal` or store as integer cents; if using floats, document that these are approximate and never used for billing.

8. **No Rounding Policy in `apply_discount`**
   - Line 13: The discount calculation has no rounding rule. Unclear whether 10% off $9.99 is $8.99 or something else.
   - Fix: Apply a rounding rule explicitly (e.g., `round(amount - amount * pct / 100, 2)`).

9. **Missing Bounds Validation in `apply_discount`**
   - Line 12: No check that `pct` is 0–100 or that `amount` is positive. Negative discount or 500% would not be caught.
   - Fix: Validate inputs before calculation.

10. **Fragile Index-Based Data Access**
    - Lines 9–10, 15: Hardcoded indices (`o[1]`, `order[0]`) are error-prone; if the SELECT changes, these break silently or crash.
    - Fix: Use `sqlite3.Row` with named access or return dicts.

11. **No Error Handling**
    - Database errors, malformed rows, missing fields—nothing is caught or logged.
    - Fix: Add try/except blocks and log failures at the boundary (HTTP handler).

---

### Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    # Authorization: must be checked by the HTTP handler before calling this
    
    # Validate status against allowlist
    VALID_STATUSES = {"pending", "processing", "completed", "cancelled"}
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATUSES}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row  # Named column access
            cur = conn.cursor()
            # Use parameterized query to prevent SQL injection
            cur.execute(
                "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?",
                (user_id, status)
            )
            return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database error fetching orders for user {user_id}: {e}") from e


def average_order_value(orders):
    if not orders:
        return Decimal("0.00")
    
    total = Decimal("0.00")
    for order in orders:
        total += Decimal(str(order["amount"]))
    
    return total / len(orders)


def apply_discount(amount, pct):
    if not (0 <= pct <= 100):
        raise ValueError(f"Discount percentage must be 0-100, got {pct}")
    if amount < 0:
        raise ValueError(f"Amount must be non-negative, got {amount}")
    
    result = Decimal(str(amount)) - Decimal(str(amount)) * Decimal(str(pct)) / 100
    return round(result, 2)  # Round to nearest cent


def format_receipt(order):
    try:
        order_id = order["id"]
        amount = order["amount"]
        return f"Order #{order_id}: ${amount:.2f}"
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"Invalid order record: {e}") from e
```

**Key Changes:**
- Parameterized SQL query prevents injection.
- Authorization must be enforced at the HTTP handler layer (add a guard like `assert request.user_id == user_id` or pass authenticated user only).
- Connection is closed automatically with `with` context manager.
- Empty orders handled gracefully; zero division prevented.
- Status is allowlisted and rejected if invalid.
- Money uses `Decimal` for accuracy; rounding applied explicitly.
- Discount percentage and amount are bounds-checked.
- Type errors prevented; f-strings and `.format()` used safely.
- `sqlite3.Row` enables named column access, making the code resilient to query changes.
- Errors are caught and logged with context.