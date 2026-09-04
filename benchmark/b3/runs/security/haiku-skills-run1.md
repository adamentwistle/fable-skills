# Code Review: get_user_orders Module

## Issues Found

### CRITICAL

1. **SQL Injection in get_user_orders (lines 6)**
   - String formatting concatenates request parameters directly into the SQL query. Attacker can pass `' OR '1'='1` as status to bypass WHERE clause and read all orders.
   - **Fix:** Use parameterized queries with `?` placeholders and pass parameters as a tuple to `execute()`.

2. **Type Error in format_receipt (line 18)**
   - Tries to concatenate string with `order[0]` (an integer ID) using `+`. This raises `TypeError: can only concatenate str (not "int") to str`.
   - **Fix:** Convert `order[0]` to string: `str(order[0])`.

### HIGH

3. **Database Connection Leak in get_user_orders (lines 5–8)**
   - Connection is never closed. Repeated calls exhaust the connection pool, eventually failing with "database is locked" or similar.
   - **Fix:** Use try/finally to ensure `conn.close()` is called.

4. **Division by Zero in average_order_value (line 11)**
   - If `orders` is an empty list, `len(orders)` is 0, raising `ZeroDivisionError`. No guard for this case.
   - **Fix:** Check `if not orders:` and raise `ValueError` or handle explicitly.

### MEDIUM

5. **Floating-Point Arithmetic for Money in average_order_value (line 10)**
   - Using `float` for currency sums. `0.1 + 0.2 ≠ 0.3` in binary floating-point; compound errors across many orders lead to penny-rounding mismatches.
   - **Fix:** Use `Decimal` type from the `decimal` module.

6. **Floating-Point Arithmetic for Money in apply_discount (line 13)**
   - Discount calculation uses float: `amount - amount * pct / 100` can produce results that differ from the exact mathematical value due to rounding.
   - **Fix:** Use `Decimal` for both amount and percentage.

7. **Currency Display Format in format_receipt (line 18)**
   - Converting `order[1]` to string with `str()` produces inconsistent output (e.g., `"10.0"`, `"10.123"`, or `"10.00000000001"` due to float representation).
   - **Fix:** Use format specifier: `f"{amount:.2f}"` to ensure exactly 2 decimal places.

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Parameterized query prevents SQL injection
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()
    finally:
        conn.close()

def average_order_value(orders):
    if not orders:
        raise ValueError("Cannot calculate average of empty orders list")
    
    total = Decimal('0.00')
    for o in orders:
        total += Decimal(str(o[1]))
    
    return total / len(orders)

def apply_discount(amount, pct):
    amount_dec = Decimal(str(amount))
    pct_dec = Decimal(str(pct))
    discount = amount_dec * (pct_dec / Decimal('100'))
    return amount_dec - discount

def format_receipt(order):
    order_id = str(order[0])
    amount = Decimal(str(order[1]))
    return f"Order #{order_id}: ${amount:.2f}"
```