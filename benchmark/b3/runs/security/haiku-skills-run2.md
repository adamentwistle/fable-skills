# Code Review: E-Commerce Orders Module

## Issues Found

**CRITICAL**
1. **SQL Injection in `get_user_orders`** — Query uses string formatting with unsanitized user input. A malicious `user_id` or `status` can break out and execute arbitrary SQL. **Fix:** Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

**HIGH**
2. **Resource leak in `get_user_orders`** — Connection is never closed, causing resource exhaustion on repeated calls. **Fix:** Use `with sqlite3.connect(db_path) as conn:` to auto-close.

3. **Type error in `format_receipt`** — `order[0]` (integer ID) cannot be concatenated with strings using `+`. This will crash at runtime. **Fix:** Convert to string first: `str(order[0])` or use f-string.

4. **Same type error in `format_receipt`** — `order[1]` (numeric amount) can't be concatenated with strings. **Fix:** Convert to string and format to 2 decimal places.

5. **Division by zero in `average_order_value`** — Empty `orders` list causes crash on `total / len(orders)`. **Fix:** Check for empty list and return `None` or raise explicitly.

6. **No error handling in `get_user_orders`** — Database errors (missing DB, permission denied, etc.) will bubble up unhandled. **Fix:** Wrap in try/except and provide actionable errors.

**MEDIUM**
7. **Float arithmetic for money in `average_order_value` and `apply_discount`** — Binary floats can't represent decimal amounts exactly (`0.1 + 0.2 ≠ 0.3`). **Fix:** Use `Decimal` type for all monetary values.

8. **Missing validation in `apply_discount`** — Negative or >100% discounts aren't rejected. A -50% discount increases the price; >100% makes it negative. **Fix:** Validate `0 ≤ pct ≤ 100`.

9. **No rounding in `apply_discount`** — Result may have more than 2 decimal places (e.g., `$12.333...`). Monetary values must round to cents. **Fix:** Call `.quantize(Decimal('0.01'))` on result.

10. **No money formatting in `format_receipt`** — Output could be `$12.5` instead of `$12.50`. **Fix:** Format amount to 2 decimal places in the string.

11. **Type assumptions in `average_order_value`** — No validation that `o[1]` is numeric or that `orders` isn't malformed. **Fix:** Convert with `Decimal(str(...))` and catch exceptions.

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal

def get_user_orders(db_path, user_id, status):
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()


def average_order_value(orders):
    if not orders:
        return None
    
    total = Decimal(0)
    for o in orders:
        total += Decimal(str(o[1]))
    
    return total / len(orders)


def apply_discount(amount, pct):
    amount = Decimal(str(amount))
    pct = Decimal(str(pct))
    
    if pct < 0 or pct > 100:
        raise ValueError(f"Discount percentage must be 0–100, got {pct}")
    
    discount = amount * pct / Decimal(100)
    result = amount - discount
    return result.quantize(Decimal('0.01'))


def format_receipt(order):
    order_id = str(order[0])
    amount = Decimal(str(order[1]))
    formatted_amount = f"{amount:.2f}"
    return f"Order #{order_id}: ${formatted_amount}"
```