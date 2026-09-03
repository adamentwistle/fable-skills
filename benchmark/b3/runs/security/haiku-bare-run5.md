## Issues Found

**CRITICAL**
1. **SQL Injection** (get_user_orders:4) — Query uses string formatting on untrusted user input. An attacker can inject SQL by crafting user_id or status values. Use parameterized queries with `?` placeholders instead of `%` formatting.

**HIGH**
2. **Connection leak** (get_user_orders:2) — Database connection is never closed. Repeated calls exhaust connection pool. Wrap with context manager or explicit close in finally block.
3. **Division by zero** (average_order_value:9) — Crashes if orders list is empty. Check length before dividing.
4. **Type error** (format_receipt:15) — Tries to concatenate order[0] (an int from the database) directly to a string with `+`. Use f-string or str() conversion.
5. **Type assumption** (average_order_value:7) — No validation that o[1] is numeric; will raise TypeError if order amount is NULL or malformed.

**MEDIUM**
6. **Invalid discount values** (apply_discount:11) — No validation that pct is 0–100. Negative or >100 values silently produce wrong results.
7. **Missing bounds check** (format_receipt:15) — No validation that order has at least 2 elements; will raise IndexError if malformed.

---

## Corrected Code

```python
import sqlite3

def get_user_orders(db_path, user_id, status):
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()

def average_order_value(orders):
    if not orders:
        raise ValueError("Cannot calculate average of empty order list")
    total = 0.0
    for o in orders:
        if not isinstance(o[1], (int, float)):
            raise TypeError(f"Order amount must be numeric, got {type(o[1])}")
        total += o[1]
    return total / len(orders)

def apply_discount(amount, pct):
    if not isinstance(amount, (int, float)) or not isinstance(pct, (int, float)):
        raise TypeError("amount and pct must be numeric")
    if not (0 <= pct <= 100):
        raise ValueError("pct must be between 0 and 100")
    return amount - amount * pct / 100

def format_receipt(order):
    if len(order) < 2:
        raise ValueError("order must have at least id and amount fields")
    return f"Order #{order[0]}: ${order[1]}"
```