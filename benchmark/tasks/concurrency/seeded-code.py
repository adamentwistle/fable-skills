counts = {}
def allow_request(user_id, limit=100):
    count = counts.get(user_id, 0)
    if count < limit:
        counts[user_id] = count + 1
        return True
    return False
