## Code Review: get_user_orders Module

### Issues Found

**CRITICAL**
1. **SQL Injection (line 5)** – `user_id` and `status` are user-controlled request parameters directly concatenated into the SQL query using `%` formatting. An attacker passing `user_id = "1' OR '1'='1"` would bypass filtering entirely.
   - Fix: Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

**HIGH**
2. **Division by zero (line 10)** – `average_order_value()` crashes if `orders` is empty. Calling code receives unhandled `ZeroDivisionError` → 500 response.
   - Fix: Check `if not orders` before dividing; raise explicit error with a message naming the issue.

3. **Type error in format_receipt (line 15)** – SQLite INTEGER columns produce Python `int`, not string. Line `"Order #" + order[0]` crashes with `TypeError: can only concatenate str (not "int") to str`.
   - Fix: Wrap `order[0]` in `str()`.

**MEDIUM**
4. **Resource leak (lines 6–7)** – Connection and cursor are never closed. Repeated calls exhaust file descriptors and database locks.
   - Fix: Use `with sqlite3.connect(db_path) as conn:` to auto-close.

5. **No input validation (line 5)** – If `user_id` or `status` is `None` or empty, string formatting produces invalid SQL `WHERE user_id = 'None'`. Calling code should validate at the boundary.
   - Fix: Reject `None`, empty strings, or non-string types at entry.

6. **Unhandled database errors (line 7)** – Lock timeouts, corrupt database, permission errors raise uncaught exceptions that expose schema/paths in 500 response. Caller learns nothing actionable.
   - Fix: Catch `sqlite3.DatabaseError`; wrap with a user-facing error message.

**LOW**
7. **Float money arithmetic (line 9)** – Summing `order[1]` as Python floats introduces representation errors. `10.25 + 20.30` may not equal exactly `30.55`.
   - Fix: Use `decimal.Decimal` for all money math; convert at schema boundary only.

8. **Discount rounding policy unclear (line 13)** – `amount - amount * pct / 100` produces floats with no rounding rule. For `amount=10, pct=33`, result is `6.7`, ambiguous for currency.
   - Fix: Name and apply a rounding policy (half-up, floor, etc.) using `Decimal.quantize()`.

---

### Corrected Code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP

def get_user_orders(db_path, user_id, status):
    """Fetch orders for a user with given status.
    
    Args:
        db_path: path to SQLite database
        user_id: user identifier (string/int)
        status: order status filter (string)
    
    Returns:
        list of (id, amount, status) tuples
    
    Raises:
        ValueError: if inputs are invalid or database error occurs
    """
    if not user_id or not status:
        raise ValueError("user_id and status are required and cannot be empty")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
            cur.execute(query, (user_id, status))
            return cur.fetchall()
    except sqlite3.DatabaseError as e:
        raise ValueError("failed to fetch orders from database") from e

def average_order_value(orders):
    """Compute average order value.
    
    Args:
        orders: list of (id, amount, status) tuples
    
    Returns:
        Decimal: average amount per order
    
    Raises:
        ValueError: if orders list is empty
    """
    if not orders:
        raise ValueError("cannot compute average of zero orders")
    
    total = Decimal('0')
    for o in orders:
        total += Decimal(str(o[1]))
    
    return total / len(orders)

def apply_discount(amount, pct):
    """Apply percentage discount to amount, rounded half-up.
    
    Args:
        amount: decimal price
        pct: discount percentage (e.g., 10 for 10% off)
    
    Returns:
        Decimal: discounted amount rounded to cents
    """
    amount_dec = Decimal(str(amount))
    pct_dec = Decimal(str(pct))
    discount = amount_dec * pct_dec / Decimal(100)
    result = (amount_dec - discount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return result

def format_receipt(order):
    """Format order as receipt line.
    
    Args:
        order: (id, amount, status) tuple
    
    Returns:
        str: formatted receipt string
    """
    order_id = str(order[0])
    amount = str(order[1])
    return "Order #" + order_id + ": $" + amount
```