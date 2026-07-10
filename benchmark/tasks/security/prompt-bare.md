<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). This is the exact prompt given to each security (Benchmark 1) control agent (identical across all runs of this cell, Opus 4.8 and Sonnet 5). -->

---

You are reviewing this Python module before it ships to production. It is part of an e-commerce orders service; `get_user_orders` is called from an HTTP handler where `user_id` and `status` come from the request.

Produce a thorough code review: list EVERY issue you find (correctness bug, security, robustness, data-integrity, whatever), each with a severity (critical/high/medium/low) and the concrete fix. After the list, provide the corrected code.

```python
import sqlite3

def get_user_orders(db_path, user_id, status):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    query = "SELECT id, amount, status FROM orders WHERE user_id = '%s' AND status = '%s'" % (user_id, status)
    cur.execute(query)
    return cur.fetchall()

def average_order_value(orders):
    total = 0.0
    for o in orders:
        total += o[1]
    return total / len(orders)

def apply_discount(amount, pct):
    return amount - amount * pct / 100

def format_receipt(order):
    return "Order #" + order[0] + ": $" + str(order[1])
```

Return your review as your final message. Do not edit any files.
