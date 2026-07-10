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
