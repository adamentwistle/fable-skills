## Code Review: E-Commerce Orders Module

### Issues Found

**CRITICAL**

1. **SQL Injection in `get_user_orders`** (line with `%s` formatting)
   - `user_id` and `status` from the HTTP request are interpolated directly into SQL
   - Attack: `user_id = "1' OR '1'='1"` will bypass the WHERE clause and return all orders
   - Fix: Use parameterized queries with `?` placeholders and pass values as tuple to `execute()`

**HIGH**

2. **Type Error in `format_receipt`** (string concatenation)
   - `order[0]` is an integer (id), but code does `"Order #" + order[0]`, which crashes with `TypeError`
   - Fix: Convert to string: `f"Order #{order['id']}: ${order['amount']}"`

3. **Division by Zero in `average_order_value`** (no empty check)
   - `return total / len(orders)` crashes when `orders` is empty
   - Fix: Check `if not orders: return None` (or decide on a policy: 0, error, or None)

**MEDIUM**

4. **Database Connection Leak** (no cleanup)
   - Connection opened but never closed; resources leak on exception or normal exit
   - Fix: Use context manager `with sqlite3.connect(db_path) as conn:`

5. **Binary Floats for Money** (`apply_discount`)
   - `amount - amount * pct / 100` loses precision and causes rounding errors (e.g., `0.1 + 0.2 ≠ 0.3`)
   - Fix: Use `Decimal` type and explicitly round to 2 decimal places (cents)

6. **No Input Validation**
   - `user_id` could be None, wrong type; `status` could be empty string
   - `apply_discount`: `pct` not validated (negative, > 100 allowed)
   - Fix: Validate types and ranges at function entry

7. **No Error Handling**
   - Database errors, type errors, division by zero crash without context
   - Fix: Catch exceptions and raise/log with actionable messages

**LOW**

8. **Magic Indices** (brittle data access)
   - Using `o[1]`, `order[0]`, `order[1]` makes changes to query error-prone
   - Fix: Use `sqlite3.Row` factory or named access to read columns by name

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    if not isinstance(user_id, (int, str)):
        raise ValueError("user_id must be a string or integer")
    if not isinstance(status, str) or not status:
        raise ValueError("status must be a non-empty string")
    
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            # Parameterized query prevents SQL injection
            query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
            cur.execute(query, (user_id, status))
            return cur.fetchall()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database error fetching orders: {e}") from e

def average_order_value(orders):
    if not orders:
        return None
    
    total = Decimal(0)
    for order in orders:
        total += Decimal(str(order['amount']))
    return total / len(orders)

def apply_discount(amount, pct):
    if not isinstance(amount, (int, float, Decimal)):
        raise ValueError("amount must be numeric")
    if not isinstance(pct, (int, float)):
        raise ValueError("pct must be numeric")
    if pct < 0 or pct > 100:
        raise ValueError("discount pct must be between 0 and 100")
    
    amount_dec = Decimal(str(amount))
    discount = amount_dec * Decimal(pct) / Decimal(100)
    final = amount_dec - discount
    return final.quantize(Decimal('0.01'))  # Round to cents

def format_receipt(order):
    return f"Order #{order['id']}: ${order['amount']}"
```

**Key changes:**
- Parameterized queries with `?` placeholders
- Context manager for automatic connection cleanup
- Decimal arithmetic for money; explicit 2-place rounding policy
- Input validation on untrusted fields (user_id, status, pct)
- Row factory enables named column access (both index and name work)
- Exception chaining preserves database error context
- Empty orders check with explicit policy (returns None)