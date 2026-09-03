# Code Review: E-Commerce Orders Service

## Issues Found

### CRITICAL

1. **SQL Injection in `get_user_orders:4`**
   - The query uses string interpolation: `"... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)`
   - An attacker can pass `user_id = "1' OR '1'='1"` to bypass filtering and read all orders
   - Fix: Use parameterized query with `?` placeholders and pass values as a tuple to `execute()`

2. **Division by Zero in `average_order_value:10`**
   - If `orders` is empty, `total / len(orders)` crashes with ZeroDivisionError
   - Calling function has no safety check
   - Fix: Guard with `if not orders: raise ValueError(...)`

3. **TypeError in `format_receipt:17`**
   - `"Order #" + order[0] + ": $"` attempts to concatenate an integer (order ID from the database) with a string
   - Crashes: `TypeError: can only concatenate str (not "int") to str`
   - Fix: Use f-string formatting: `f"Order #{order[0]}: $..."`

### HIGH

4. **Resource Leak in `get_user_orders`**
   - Database connection is opened but never closed
   - Repeated calls leak file handles and exhaust the connection pool
   - Fix: Wrap with `try/finally` block and call `conn.close()`

5. **Floating-Point Money in `apply_discount:14` and `format_receipt:17`**
   - Using binary floats for currency: `amount - amount * pct / 100`
   - Precision errors accumulate: `100.00 * 0.15 / 100` may not equal exactly `15.00`
   - Receipt displays unformatted float: `str(order[1])` could print `"99.99999999999999"`
   - Fix: Use `Decimal` type throughout for all monetary calculations

6. **Missing Input Validation in `apply_discount`**
   - No check that `amount >= 0` or `0 <= pct <= 100`
   - Negative or invalid inputs silently produce nonsense results
   - Fix: Validate with explicit error messages

### MEDIUM

7. **Type Safety in `average_order_value:10`**
   - Assumes `o[1]` is numeric; SQLite does not enforce types, so a corrupt database could contain non-numeric values
   - No error message when type coercion fails
   - Fix: Explicitly convert to `Decimal(str(order[1]))` and wrap in try/except if needed

8. **Missing Structure Validation in `format_receipt`**
   - No check that `order` has at least 2 elements; crashes if malformed
   - Fix: Validate `len(order) >= 2` before access

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?",
            (user_id, status)
        )
        return cur.fetchall()
    finally:
        conn.close()

def average_order_value(orders):
    if not orders:
        raise ValueError("Cannot calculate average of empty orders list")
    
    total = Decimal(0)
    for order in orders:
        total += Decimal(str(order[1]))
    return total / Decimal(len(orders))

def apply_discount(amount, pct):
    if amount < 0:
        raise ValueError(f"Amount cannot be negative: {amount}")
    if not (0 <= pct <= 100):
        raise ValueError(f"Discount percentage must be 0-100: {pct}")
    
    discount_rate = Decimal(str(pct)) / Decimal(100)
    return amount - (amount * discount_rate)

def format_receipt(order):
    if len(order) < 2:
        raise ValueError("Order tuple must have at least 2 elements")
    
    order_id = order[0]
    amount = Decimal(str(order[1]))
    return f"Order #{order_id}: ${amount:.2f}"
```