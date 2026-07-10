import json
_cache = None
def get_config(path='config.json'):
    global _cache
    if _cache is None:
        with open(path) as f:
            _cache = json.load(f)
    return _cache
