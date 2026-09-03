## Code Review: E-Commerce Orders Module

### Issues Found

**CRITICAL**

1. **SQL Injection (Line 6)** — String formatting with user-supplied `user_id` and `status`. An attacker can break the query or dump the database. **Fix:** Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

2. **Division by Zero (Line 11)** — `average_order_value()` crashes if `orders` is empty. **Fix:** Check `len(orders) > 0` before dividing; return a sensible zero value if empty.

**HIGH**

3. **Type Error in format_receipt (Line 16)** — `order[0]` is an integer, but code tries to concatenate it as a string (`"Order #" + order[0]`). Raises `TypeError`. **Fix:** Convert to string explicitly.

4. **Money as Float (Line 10)** — Summing floats causes rounding errors in financial calculations. SQLite returns floats for computed money; this is fragile. **Fix:** Use `decimal.Decimal` for all money arithmetic.

5. **Resource Leak (Lines 5–7)** — Connection and cursor never close. While SQLite may auto-close, explicit cleanup is required. **Fix:** Use `with` context manager for the connection.

**MEDIUM**

6. **No Error Handling** — Database errors (missing DB, schema mismatch, query failure) propagate unhandled. **Fix:** Catch `sqlite3.Error` and raise or log meaningfully.

7. **No Input Validation** — `status` value is not validated. If it contains SQL, string formatting is wide open (issue #1). **Fix:** Validate `status` against an allowlist of valid statuses.

8. **Integer user_id Not Validated** — Code assumes `user_id` is passable to SQL; if it's malformed, parameterization won't help the caller. **Fix:** Try to coerce to `int` and reject if it fails.

9. **Currency Formatting Missing (Line 16)** — Receipt shows raw float (e.g., `$10.5` instead of `$10.50`). **Fix:** Format with `.2f`.

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    # Validate status against allowlist
    allowed_statuses = {'pending', 'completed', 'cancelled', 'shipped'}
    if status not in allowed_statuses:
        raise ValueError(f"Invalid status: {status}")
    
    # Validate user_id is an integer
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid user_id: {user_id}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            # Parameterized query prevents SQL injection
            query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
            cur.execute(query, (user_id, status))
            return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database error: {e}")

def average_order_value(orders):
    if not orders:
        return Decimal('0.00')
    
    total = Decimal('0')
    for o in orders:
        amount = o[1]
        if isinstance(amount, float):
            total += Decimal(str(amount))
        else:
            total += Decimal(amount)
    
    return total / Decimal(len(orders))

def apply_discount(amount, pct):
    # Convert to Decimal for precise money arithmetic
    amount = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    pct = Decimal(str(pct))
    return amount - (amount * pct / 100)

def format_receipt(order):
    order_id = order[0]
    amount = order[1]
    
    # Ensure amount is Decimal and format to 2 places
    if isinstance(amount, float):
        amount = Decimal(str(amount))
    elif isinstance(amount, int):
        amount = Decimal(amount)
    
    return f"Order #{order_id}: ${amount:.2f}"
```