# Code Review: E-commerce Orders Service

**Critical Issues:**

1. **SQL Injection vulnerability** (CRITICAL)  
   String formatting allows attacker-controlled input directly into SQL. A request with `user_id = "1' OR '1'='1"` bypasses the WHERE clause entirely.  
   Fix: Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

2. **Type error in format_receipt** (CRITICAL)  
   `order[0]` is an integer, but the code attempts string concatenation: `"Order #" + order[0]` crashes with `TypeError`.  
   Fix: Convert to string: `str(order[0])`.

3. **Division by zero in average_order_value** (HIGH)  
   Empty order list causes `ZeroDivisionError` on `total / len(orders)`.  
   Fix: Check length before dividing; return 0.0 for empty list or raise an appropriate error.

4. **Database connection leak** (HIGH)  
   `conn.close()` is never called. On exception or normal exit, the connection stays open, exhausting resources on repeated calls.  
   Fix: Use try-finally or context manager to guarantee cleanup.

5. **No input validation** (MEDIUM)  
   `user_id` and `status` are passed directly to the query without type or format checks. While the HTTP handler may validate, defensive code should not assume upstream validation.  
   Fix: Validate that inputs are strings and non-empty if appropriate.

6. **No error handling** (MEDIUM)  
   Missing database file, corrupted database, or locked database crashes the caller with an uncaught exception.  
   Fix: Wrap in try-except or let the caller handle, but at minimum log/document the failure modes.

7. **Fragile tuple unpacking with magic indices** (MEDIUM)  
   Code depends on tuple order (`order[0]`, `order[1]`) with no named fields. Future schema changes break silently.  
   Fix: Use sqlite3.Row factory or name fields explicitly for clarity.

---

## Corrected Code

```python
import sqlite3

def get_user_orders(db_path, user_id, status):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()
    finally:
        conn.close()

def average_order_value(orders):
    if not orders:
        return 0.0
    total = 0.0
    for o in orders:
        total += o[1]
    return total / len(orders)

def apply_discount(amount, pct):
    return amount - amount * pct / 100

def format_receipt(order):
    return "Order #" + str(order[0]) + ": $" + str(order[1])
```