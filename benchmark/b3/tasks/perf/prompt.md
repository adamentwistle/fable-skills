You are picking up this ticket. Everything the on-call gathered is below, followed by the code as it is on `main`.

```
PERF-812   GET /api/v2/orgs/{org_id}/activity is slow for large orgs; api pods leak memory
Reporter:  on-call (platform)        Priority: P1        Release: 2026.34 (v2 activity feed)

Since v2 shipped, the mobile app's Activity tab takes 6-12 s to load for our bigger
customers. Small orgs are fine.

What we have so far:
- Datadog, last 7 d, per-org latency for this route:
    acme (org 4127):         p50 6.4 s    p95 11.2 s    (~1.9k events in the default 30 d window)
    northwind (org 88):      p50 5.1 s    p95  9.8 s    (~1.5k events)
    orgs with < 50 events:   p50 0.18 s   p95  0.41 s
- The mobile client always sends limit=1000.
- While one of these requests is in flight, /healthz on the same pod stops answering for
  several seconds. The kube liveness probe (3 s timeout) has restarted api pods 14 times
  this week. That is what pages us.
- api pod RSS climbs steadily from ~310 MB at start to ~2.1 GB after roughly 20 h, then
  the pod is OOM-killed or probe-restarted and it starts over. Traffic is flat over that
  period (~120 req/s per pod across all routes).
- pg slow-query log shows the events SELECT at 1.2-1.6 s per call for acme (excerpt below).
- events table: 4,213,660 rows total. acme has 1,912 rows in the 30 d window.
- Runtime: uvicorn, 4 workers per pod; asyncpg pool min 2 / max 10 per worker; 6 pods.

Proposal from on-call (we can ship this today if you're okay with it):
  1. bump uvicorn workers 4 -> 16 and asyncpg pool max 10 -> 50
  2. cache the whole response in Redis for 60 s, keyed on (org_id, since, limit)

Please review the code and tell us whether to go ahead with that, and what else has to change.
```

`app/api/activity.py`:

```python
import time
from datetime import datetime, timedelta, timezone

import requests
from fastapi import APIRouter, Depends, Query

from app.db import get_conn          # asyncpg pool wrapper
from app.settings import settings

router = APIRouter()

_geo_cache: dict[str, dict] = {}
_request_timings: list[float] = []   # read by /internal/metrics, do not remove


def lookup_geo(ip: str) -> dict:
    hit = _geo_cache.get(ip)
    if hit is not None:
        return hit
    resp = requests.get(
        f"{settings.GEOIP_URL}/v1/{ip}",
        headers={"X-Api-Key": settings.GEOIP_KEY},
        timeout=2.0,
    )
    resp.raise_for_status()
    data = resp.json()
    geo = {"city": data.get("city"), "country": data.get("country_code")}
    _geo_cache[ip] = geo
    return geo


async def serialize_event(ev, conn) -> dict:
    actor = await conn.fetchrow(
        "SELECT id, display_name, avatar_url FROM users WHERE id = $1",
        ev["actor_id"],
    )
    geo = lookup_geo(str(ev["client_ip"])) if ev["client_ip"] else None
    return {
        "id": ev["id"],
        "kind": ev["kind"],
        "created_at": ev["created_at"].isoformat(),
        "actor": (
            {"id": actor["id"], "name": actor["display_name"], "avatar": actor["avatar_url"]}
            if actor else None
        ),
        "location": geo,
        "payload": ev["payload"],
    }


@router.get("/orgs/{org_id}/activity")
async def org_activity(
    org_id: int,
    since: datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
    conn=Depends(get_conn),
):
    since = since or datetime.now(timezone.utc) - timedelta(days=30)
    rows = await conn.fetch(
        """
        SELECT id, org_id, actor_id, kind, dedupe_key, client_ip, payload, created_at
        FROM events
        WHERE org_id = $1 AND created_at >= $2
        ORDER BY created_at DESC
        """,
        org_id,
        since,
    )

    # Webhook retries can insert the same logical event more than once;
    # collapse on dedupe_key, keeping the newest (rows arrive newest-first).
    seen: list[str] = []
    unique = []
    for ev in rows:
        if ev["dedupe_key"] in seen:
            continue
        seen.append(ev["dedupe_key"])
        unique.append(ev)

    items = [await serialize_event(ev, conn) for ev in unique[:limit]]
    return {"org_id": org_id, "count": len(items), "items": items}
```

`app/main.py` (relevant part):

```python
import time
from fastapi import FastAPI, Request
from app.api import activity, metrics
from app.api.activity import _request_timings

app = FastAPI()
app.include_router(activity.router, prefix="/api/v2")
app.include_router(metrics.router)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - t0
    _request_timings.append(elapsed)
    response.headers["X-Response-Time"] = f"{elapsed * 1000:.1f}ms"
    return response


@app.get("/healthz")
async def healthz():
    return {"ok": True}
```

`app/api/metrics.py`:

```python
from fastapi import APIRouter
from app.api.activity import _request_timings

router = APIRouter()


@router.get("/internal/metrics")
async def metrics():
    n = len(_request_timings)
    if n == 0:
        return {"requests": 0}
    s = sorted(_request_timings)
    return {
        "requests": n,
        "p50_ms": round(s[n // 2] * 1000, 1),
        "p95_ms": round(s[int(n * 0.95)] * 1000, 1),
    }
```

`migrations/0007_events.sql`:

```sql
CREATE TABLE events (
    id          BIGSERIAL    PRIMARY KEY,
    org_id      BIGINT       NOT NULL REFERENCES orgs(id),
    actor_id    BIGINT       REFERENCES users(id),
    kind        TEXT         NOT NULL,
    dedupe_key  TEXT         NOT NULL,
    client_ip   INET,
    payload     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX events_actor_id_idx ON events (actor_id);
CREATE INDEX events_kind_idx     ON events (kind);
```

pg slow-query log excerpt (`log_min_duration_statement = 500`), one of ~400 identical entries in the last hour:

```
2026-09-01 14:02:17.311 UTC [31882] LOG:  duration: 1412.871 ms  execute __asyncpg_stmt_9__:
    SELECT id, org_id, actor_id, kind, dedupe_key, client_ip, payload, created_at
    FROM events WHERE org_id = $1 AND created_at >= $2 ORDER BY created_at DESC
2026-09-01 14:02:17.311 UTC [31882] DETAIL:  parameters: $1 = '4127', $2 = '2026-08-02 14:02:15.91+00'
```

Return a terse NUMBERED list, one line each, in the order you would actually do it. Each line is either a step you would take or a finding (the problem + a one-clause fix). Say explicitly whether the on-call's proposal should ship. No rewritten code, no preamble, no headings.
