## Code Review: E-Commerce Orders Service

### Issues Found

**CRITICAL**
1. **SQL Injection** — Line 5: String formatting (`%s` with `%` operator) allows SQL injection. Request parameters `user_id` and `status` are interpolated directly into the query. An attacker passing `user_id = "1' OR '1'='1"` bypasses filters or extracts all data.
   - **Fix:** Use parameterized queries with `?` placeholders and pass parameters as a tuple to `execute()`.

**HIGH**
2. **Resource leak — connection not closed** — Line 4: `sqlite3.connect()` is never closed, leaving the connection open and consuming resources. Database locks can pile up under load.
   - **Fix:** Use try/finally to ensure `conn.close()` runs, or use a context manager.

3. **Resource leak — cursor not closed** — Line 5: Cursor is not closed. Same resource leak risk.
   - **Fix:** Close in the same finally block.

4. **Division by zero** — `average_order_value()` line 12: If `orders` is empty, `total / len(orders)` raises `ZeroDivisionError`. No guard against empty result sets.
   - **Fix:** Check `if not orders:` and return a default (0.0) or raise a descriptive error.

5. **Type error in concatenation** — `format_receipt()` line 15: `order[0]` (the id) is an integer from the database. Concatenating with `+` and a string raises `TypeError` in Python 3.
   - **Fix:** Convert to string: `str(order[0])`.

**MEDIUM**
6. **No error handling** — Database operations (`connect()`, `execute()`) can fail (bad path, locked database, permissions, network if remote). No try/except to handle or log these failures.
   - **Fix:** Wrap database calls in try/except or let the caller handle exceptions (depending on design).

7. **Unvalidated type assumptions** — `average_order_value()` assumes `o[1]` is numeric; `apply_discount()` assumes `amount` is numeric. If the database or caller provides wrong types, operations fail silently or with unclear errors.
   - **Fix:** Add type checks or document contract clearly.

---

### Corrected Code

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