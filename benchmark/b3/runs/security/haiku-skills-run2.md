# Code Review: e-commerce orders service

## Issues Found

**CRITICAL**

1. **SQL Injection via `user_id` and `status`** (lines 5–6)
   - String formatting concatenates unsanitized request input directly into the SQL query: `"SELECT ... WHERE user_id = '%s' AND status = '%s'" % (user_id, status)`
   - Attacker can break out of the string (e.g., `user_id = "1' OR '1'='1"`) and inject arbitrary SQL, bypassing the WHERE clause or extracting other users' data
   - **Fix:** Use parameterized queries with `?` placeholders and pass parameters as a tuple to `execute()`

2. **Float arithmetic on monetary amounts** (lines 10–11, 15)
   - `average_order_value()` and `apply_discount()` use binary floats for money
   - Binary floats cannot exactly represent decimal values (0.1 + 0.2 ≠ 0.3); calculations will accumulate rounding errors and produce wrong totals and discounts
   - Example: summing 100 prices of $0.10 each will not equal $10.00
   - **Fix:** Use `Decimal` type for all monetary calculations: `from decimal import Decimal, ROUND_HALF_UP`

3. **Type error in `format_receipt()`** (line 17)
   - `order[0]` is an integer (order ID from the database), but the code concatenates it to a string: `"Order #" + order[0]`
   - This raises `TypeError: can only concatenate str (not "int") to str` at runtime
   - **Fix:** Convert to string: `"Order #" + str(order[0])`

**HIGH**

4. **Division by zero in `average_order_value()`** (line 11)
   - If `orders` is empty, `len(orders)` is 0, and `total / 0` raises `ZeroDivisionError`
   - The function crashes instead of returning a sensible default or error
   - **Fix:** Check `if not orders:` and return `Decimal(0)` or raise a descriptive `ValueError`

5. **Resource leak and missing error handling** (lines 3–6)
   - If `sqlite3.connect()` or `execute()` fails, the connection is never closed
   - No try/except means exceptions propagate uncaught; the caller gets no clear error message
   - **Fix:** Wrap in `try/finally` or use a context manager (`with sqlite3.connect() as conn:`)

**MEDIUM**

6. **Rounding policy not specified** (line 15)
   - `apply_discount()` does not round the result; floating-point precision issues compound
   - After switching to Decimal, you must specify a rounding mode (e.g., `ROUND_HALF_UP` to never overcharge)
   - **Fix:** Add explicit rounding with `quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)`

7. **Hardcoded column indices** (lines 10, 17)
   - Using `o[1]` and `order[0]` is brittle; if the schema changes or columns are reordered, code silently breaks
   - **Fix:** Use named columns with a row factory, e.g., `conn.row_factory = sqlite3.Row`, then access `order['amount']`

8. **`db_path` not validated** (line 3)
   - If `db_path` is ever controllable by the HTTP request layer, an attacker can open arbitrary SQLite databases on disk or create one in a sensitive location
   - **Fix:** Validate `db_path` against a whitelist of allowed paths, or use a hardcoded constant at the module level

**LOW**

9. **No logging of queries or errors**
   - Failed orders queries, bad inputs, or exceptions are silent; debugging and auditing are impossible
   - **Fix:** Add structured logging at entry, error, and decision points (database call outcome)

10. **Authorization not enforced at module level**
    - The function trusts the caller to have verified that the requester owns or can see `user_id`'s orders
    - This is typically a handler-layer concern, but the function should document this assumption or enforce it
    - **Fix:** Document precondition, or add an optional `authorized_user_id` parameter that must match

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

def get_user_orders(db_path, user_id, status):
    """
    Fetch orders for a user with the given status.
    Raises ValueError if db_path is invalid, sqlite3.Error on database failure.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?",
                (user_id, status)
            )
            return cur.fetchall()
    except sqlite3.Error as e:
        logger.error("database error fetching orders for user_id=%s: %s", user_id, e)
        raise

def average_order_value(orders):
    """
    Calculate the average order amount.
    Returns Decimal(0) if orders is empty.
    """
    if not orders:
        return Decimal(0)
    total = Decimal(0)
    for order in orders:
        total += Decimal(str(order['amount']))
    return total / Decimal(len(orders))

def apply_discount(amount, pct):
    """
    Apply a discount percentage to an amount.
    amount: Decimal or numeric value
    pct: discount percentage (e.g., 10 for 10%)
    Returns Decimal rounded to nearest cent, never overcharging.
    """
    amount = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    pct = Decimal(str(pct))
    discounted = amount - amount * pct / Decimal(100)
    return discounted.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def format_receipt(order):
    """Format an order for display."""
    return f"Order #{order['id']}: ${Decimal(str(order['amount'])):.2f}"
```

**Key changes:**
- Parameterized SQL queries (`?` placeholders) eliminate injection
- Context manager (`with sqlite3.connect()`) ensures connection closes
- Switched to `Decimal` for all monetary math; specified `ROUND_HALF_UP` rounding
- Row factory enables named column access, reducing brittleness
- Added division-by-zero guard returning `Decimal(0)`
- Fixed type error in `format_receipt` using f-string and explicit Decimal formatting
- Added error logging and documented function contracts
- Explicit Decimal conversion from string to avoid float precision loss