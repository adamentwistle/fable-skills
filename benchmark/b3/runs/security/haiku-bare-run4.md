# Code Review: E-Commerce Orders Service

## Issues Found

**1. SQL Injection (CRITICAL)**
- **Location:** `get_user_orders`, line 5
- **Problem:** Query uses string formatting (`%s`) with unsanitized user input. Attacker can inject SQL by passing `status="pending' OR '1'='1"`.
- **Fix:** Use parameterized queries with `?` placeholders and pass values as a tuple to `execute()`.

**2. Type Error in format_receipt (CRITICAL)**
- **Location:** `format_receipt`, line 17
- **Problem:** `order[0]` is an integer (id from database) but code tries to concatenate with string using `+`. Raises `TypeError: can only concatenate str (not "int") to str`.
- **Fix:** Convert to string using f-string or `str()`.

**3. Database Connection Leak (HIGH)**
- **Location:** `get_user_orders`, lines 3–6
- **Problem:** Connection opened but never closed. If an error occurs during query execution, the connection leaks. Repeated calls exhaust available connections.
- **Fix:** Use `try`/`finally` to close, or use context manager (`with`).

**4. Division by Zero (HIGH)**
- **Location:** `average_order_value`, line 10
- **Problem:** If `orders` is empty, `len(orders)` is 0, raising `ZeroDivisionError`.
- **Fix:** Check if list is empty and return a default (0.0 or raise a clearer error).

**5. Fragile Magic Indices (MEDIUM)**
- **Location:** Lines 9, 17, 18
- **Problem:** Code uses `o[1]`, `order[0]`, `order[1]` with no documentation. If the SELECT statement changes, indices silently break or fetch wrong columns. Unreadable.
- **Fix:** Unpack tuples into named variables or use a dataclass/namedtuple.

**6. No Input Validation (MEDIUM)**
- **Location:** `get_user_orders`
- **Problem:** No validation that `user_id` is numeric or `status` is a valid enum value. Unexpected types could cause subtle errors.
- **Fix:** Validate inputs before querying.

---

## Corrected Code

```python
import sqlite3
from typing import List, Tuple

def get_user_orders(db_path: str, user_id: int, status: str) -> List[Tuple]:
    """Fetch orders for a user with a specific status."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Use parameterized query to prevent SQL injection
        query = "SELECT id, amount, status FROM orders WHERE user_id = ? AND status = ?"
        cur.execute(query, (user_id, status))
        return cur.fetchall()
    finally:
        conn.close()

def average_order_value(orders: List[Tuple]) -> float:
    """Calculate average order value. Returns 0.0 for empty list."""
    if not orders:
        return 0.0
    total = sum(o[1] for o in orders)
    return total / len(orders)

def apply_discount(amount: float, pct: float) -> float:
    """Apply a percentage discount."""
    return amount - amount * pct / 100

def format_receipt(order: Tuple) -> str:
    """Format an order as a receipt line."""
    order_id, amount, _ = order
    return f"Order #{order_id}: ${amount}"
```

**Key changes:**
- Parameterized query with `?` placeholders stops SQL injection.
- `try`/`finally` ensures connection closes even on error.
- Empty list check prevents division by zero.
- Unpacking tuple in `format_receipt` makes indices explicit and catches mismatches early.
- f-string converts int to string safely.
- Type hints clarify intent.