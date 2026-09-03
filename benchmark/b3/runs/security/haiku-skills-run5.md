# Code Review: Orders Service Module

## Issues Found

**CRITICAL**
1. **SQL Injection in `get_user_orders`** — Query uses string formatting (`%`) instead of parameterized queries. User input `user_id` and `status` flow directly into SQL. An attacker with `user_id = "1' OR '1'='1"` can read all orders or modify the query. Fix: Use `?` placeholders and pass inputs as tuple to `execute()`.

**HIGH**
2. **Type error in `format_receipt`** — `order[0]` is an integer; `"Order #" + order[0]` raises `TypeError`. The function will crash on every call. Fix: Use f-string: `f"Order #{order[0]}: ${order[1]}"`.

3. **Division by zero in `average_order_value`** — Empty `orders` list crashes with `ZeroDivisionError`. HTTP handler with no orders becomes a DoS vector. Fix: Check `if not orders:` and return 0 or a defined empty value.

**MEDIUM**
4. **Database connection leak in `get_user_orders`** — Connection is never closed. Under load, connections exhaust, handler stalls. Fix: Use try/finally or context manager to ensure `conn.close()`.

5. **No error handling in `get_user_orders`** — Database errors bubble up as generic exceptions with no user_id or context. Logs are useless. Fix: Catch `sqlite3.Error` and wrap with the user_id and operation name.

6. **Float arithmetic for currency in `apply_discount`** and amounts returned from database — Binary float math causes precision loss. `99.99 - 99.99 * 15 / 100` may not equal exactly `84.99`, misprice orders. Fix: Use `Decimal` for all money values.

7. **Brittle tuple indexing** — Code assumes `order[0]` is ID, `order[1]` is amount. If schema changes, code breaks silently. Fix: Use named tuples or dataclass so field names document intent.

---

## Corrected Code

```python
import sqlite3
from decimal import Decimal
from typing import List, Tuple

def get_user_orders(db_path: str, user_id: int, status: str) -> List[Tuple]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()
    except sqlite3.Error as e:
        raise ValueError(f"Database error fetching orders for user {user_id}: {e}") from e
    finally:
        conn.close()

def average_order_value(orders: List[Tuple]) -> Decimal:
    if not orders:
        return Decimal('0.00')
    total = Decimal('0.00')
    for o in orders:
        total += Decimal(str(o[1]))
    return total / len(orders)

def apply_discount(amount: Decimal, pct: float) -> Decimal:
    return amount - (amount * Decimal(str(pct)) / Decimal('100'))

def format_receipt(order: Tuple) -> str:
    return f"Order #{order[0]}: ${order[1]}"
```

**Key changes:**
- Parameterized SQL query with `?` placeholders stops injection.
- F-string in `format_receipt` coerces int to string.
- Empty check before division.
- `finally` block closes connection.
- Error wrapping with context.
- `Decimal` for money arithmetic avoids precision loss.
- Type hints document intent.