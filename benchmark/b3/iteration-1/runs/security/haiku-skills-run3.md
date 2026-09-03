## Code Review: Python Orders Module

### Issues Found (Severity / Concrete Fix)

**CRITICAL**
1. **SQL Injection** (line 6): user_id and status from HTTP request are directly string-interpolated into SQL. Attacker can inject SQL: `status="completed'; DROP TABLE orders; --"` or `user_id="1' OR '1'='1"`. 
   - **Fix**: Use parameterized queries with `?` placeholders: `cur.execute(query, (user_id, status))`.

**HIGH**
2. **Type Error in format_receipt** (line 13): `order[0]` is an integer (order ID), but code concatenates it with string using `+`, raising `TypeError: can only concatenate str (not "int") to str`. 
   - **Fix**: Use f-string: `f"Order #{order[0]}: ${order[1]:.2f}"`.

3. **Division by Zero** (line 9): If `orders` is empty, `len(orders)` is 0, raising `ZeroDivisionError`. 
   - **Fix**: Check `if not orders: return Decimal(0)` before dividing.

4. **Float Precision for Money** (line 11): Using binary floats for monetary amounts causes precision loss. `0.1 + 0.2 ≠ 0.3` in IEEE 754; accumulated errors can misprice orders. 
   - **Fix**: Use `Decimal` type for all monetary calculations: `total += Decimal(str(o[1]))` and `return total / Decimal(len(orders))`.

**MEDIUM**
5. **Discount Percentage Not Validated** (line 11): Negative pct values increase price; pct > 100 produces negative results. No bounds checking. 
   - **Fix**: Add guard: `if not (0 <= pct <= 100): raise ValueError(...)`.

6. **Database Connection Leak** (line 5): Connection is never closed. Repeated calls exhaust file descriptors. 
   - **Fix**: Use context manager: `with sqlite3.connect(db_path) as conn:`.

7. **No Database Error Handling** (line 6): `sqlite3.Error` propagates to HTTP handler, potentially leaking error details to client or crashing uncleanly. 
   - **Fix**: Wrap in try/except, log the error, and re-raise or return appropriate error response to caller.

8. **Database Path Not Validated** (line 5): If `db_path` is dynamic or user-influenced, enables path traversal (e.g., `../../../sensitive.db`). 
   - **Fix**: Validate db_path against an allowlist directory or canonicalize it.

9. **Missing Input Type Validation** (line 5): Function assumes `user_id` is int-like and `status` is string. HTTP request params are strings; no casting or type check. 
   - **Fix**: Validate types explicitly, document expected types in signature.

**LOW**
10. **Order Tuple Bounds Not Checked** (lines 9, 13): Code assumes `order` has at least 2 elements without validating structure. 
    - **Fix**: Add `if len(order) < 2: raise ValueError(...)` or document the invariant.

11. **No Logging** (all functions): Production issues are impossible to debug without logs. 
    - **Fix**: Add structured logging at decision points (DB call outcome, discount validation, calculation results).

---

### Corrected Code

```python
import sqlite3
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

def get_user_orders(db_path, user_id, status):
    """Fetch orders for a user.
    
    Args:
        db_path: Path to database file
        user_id: User ID (int)
        status: Order status (str)
    
    Returns:
        List of (id, amount, status) tuples
    
    Raises:
        ValueError: If inputs are invalid
        sqlite3.Error: If database operation fails
    """
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("status must be a non-empty string")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            # Parameterized query prevents SQL injection
            query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
            cur.execute(query, (user_id, status))
            return cur.fetchall()
    except sqlite3.Error as e:
        logger.error("Database error fetching orders for user_id=%s: %s", user_id, str(e))
        raise

def average_order_value(orders):
    """Calculate average order value.
    
    Args:
        orders: List of (id, amount, status) tuples
    
    Returns:
        Average as Decimal; Decimal(0) if orders is empty
    """
    if not orders:
        return Decimal(0)
    
    total = Decimal(0)
    for order in orders:
        if len(order) < 2:
            raise ValueError("order must have at least id and amount fields")
        total += Decimal(str(order[1]))
    return total / Decimal(len(orders))

def apply_discount(amount, pct):
    """Apply percentage discount to amount.
    
    Args:
        amount: Price (Decimal or numeric)
        pct: Discount percentage (0-100)
    
    Returns:
        Discounted price as Decimal
    
    Raises:
        ValueError: If pct outside 0-100
    """
    if not (0 <= pct <= 100):
        raise ValueError(f"Discount percentage must be 0-100, got {pct}")
    
    amount_dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    discount_factor = Decimal(pct) / Decimal(100)
    return amount_dec - (amount_dec * discount_factor)

def format_receipt(order):
    """Format order as receipt line.
    
    Args:
        order: Tuple of (id, amount, status)
    
    Returns:
        Formatted receipt string
    
    Raises:
        ValueError: If order structure invalid
    """
    if not order or len(order) < 2:
        raise ValueError("order must have at least id and amount fields")
    
    order_id, amount = order[0], order[1]
    amount_dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    return f"Order #{order_id}: ${amount_dec:.2f}"
```