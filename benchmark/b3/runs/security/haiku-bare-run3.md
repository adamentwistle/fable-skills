# Code Review: E-Commerce Orders Module

## Issues Found

**CRITICAL**
1. **SQL Injection** (`get_user_orders`): String formatting with user-supplied `user_id` and `status` allows query injection. An attacker can pass `status = "' OR '1'='1` to bypass all filtering.
   - Fix: Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

2. **Resource Leak** (`get_user_orders`): The database connection is never closed. In an HTTP service, repeated calls will exhaust the connection pool or file descriptors.
   - Fix: Close the connection in a `finally` block, or better, use a connection context manager.

**HIGH**
3. **Division by Zero** (`average_order_value`): If `orders` is empty, `len(orders)` is 0, raising `ZeroDivisionError`.
   - Fix: Check `if not orders` and raise or return a sentinel value.

4. **Type Error** (`format_receipt`): `order[0]` (the id from the database) is an integer. Concatenating it with a string using `+` raises `TypeError`.
   - Fix: Convert to string first, or use an f-string: `f"Order #{order[0]}: ${order[1]}"`.

**MEDIUM**
5. **No Input Validation** (`get_user_orders`): `user_id` and `status` are not validated; empty strings or None will produce nonsensical queries.
   - Fix: Check that both are non-empty before querying.

6. **No Error Handling**: Database errors (connection failure, malformed data, etc.) will crash the caller without useful context.
   - Fix: Wrap operations in try/except and raise or log appropriately.

7. **Fragile Data Access** (`average_order_value`, `format_receipt`): Magic indices (0, 1) assume query result structure. If the schema changes, silent corruption or crashes occur.
   - Fix: Use named tuples or Row factory for clarity.

8. **Float for Money** (`average_order_value`, `apply_discount`): Floating-point arithmetic is imprecise for financial calculations. Use `Decimal` instead.
   - Fix: Use `from decimal import Decimal` and convert amounts.

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal
from typing import List, Tuple

def get_user_orders(db_path: str, user_id: str, status: str) -> List[Tuple]:
    """Fetch orders for a user with a given status.
    
    Args:
        db_path: Path to the SQLite database.
        user_id: The user's ID (will be parameterized to prevent injection).
        status: The order status filter (will be parameterized to prevent injection).
    
    Returns:
        List of (id, amount, status) tuples, or empty list if no matches.
    
    Raises:
        ValueError: If user_id or status is empty.
        sqlite3.DatabaseError: If the database operation fails.
    """
    if not user_id or not status:
        raise ValueError("user_id and status cannot be empty")
    
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Use parameterized query (? placeholders) to prevent SQL injection.
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()
    finally:
        conn.close()

def average_order_value(orders: List[Tuple]) -> Decimal:
    """Calculate average order amount.
    
    Args:
        orders: List of (id, amount, status) tuples.
    
    Returns:
        Average amount as a Decimal.
    
    Raises:
        ValueError: If orders is empty.
    """
    if not orders:
        raise ValueError("Cannot calculate average of an empty order list")
    
    total = Decimal('0')
    for order in orders:
        total += Decimal(str(order[1]))
    return total / len(orders)

def apply_discount(amount: Decimal, pct: float) -> Decimal:
    """Apply a percentage discount to an amount.
    
    Args:
        amount: The base amount (Decimal for precision).
        pct: The discount percentage (0–100).
    
    Returns:
        Discounted amount as Decimal.
    
    Raises:
        TypeError: If amount or pct is not numeric.
        ValueError: If pct is out of range.
    """
    if not isinstance(pct, (int, float)):
        raise TypeError("pct must be numeric")
    if pct < 0 or pct > 100:
        raise ValueError("pct must be between 0 and 100")
    
    amount_dec = Decimal(str(amount)) if not isinstance(amount, Decimal) else amount
    return amount_dec * (Decimal('100') - Decimal(str(pct))) / Decimal('100')

def format_receipt(order: Tuple) -> str:
    """Format an order as a receipt line.
    
    Args:
        order: A (id, amount, status) tuple.
    
    Returns:
        Formatted string.
    """
    return f"Order #{order[0]}: ${order[1]}"
```