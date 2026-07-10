def total_revenue(rows):
    total = 0
    for r in rows:
        total += float(r['price']) * int(r['qty'])
    return total
