You are the reviewer on this PR. Below is the PR description exactly as the author wrote it, then the files in the PR, then one file that is unchanged on `main` and included for context.

```
PR #4812   orders: replace free-text `status` with SMALLINT `state`
Author: mkaur        Base: main        Release: 2026.36 (deploys Thursday 14:00 UTC)

Why
`orders.status` is free text. We keep finding new spellings in it and every reader
carries its own set of string literals. Moving it to a SMALLINT backed by OrderState
(app/orders/state.py) so the DB can only hold known values; the index also gets about
5x smaller.

Files
  migrations/versions/0142_add_orders_state.py      add `state` + index
  scripts/backfill_order_state.py                   batched backfill (safe to re-run)
  migrations/versions/0143_drop_orders_status.py    NOT NULL + drop `status`
  app/orders/state.py                               new enum
  app/orders/models.py, app/orders/service.py, app/api/orders.py    switched to `state`
  tests/orders/*                                    updated; suite green (fresh schema at head)

Rollout (all in the Thursday window)
  1. alembic upgrade 0142
  2. deploy app (rolling, about 6 min across 12 pods)
  3. kubectl run backfill-4812 -- python scripts/backfill_order_state.py
  4. alembic upgrade 0143

Grepped `status` under app/; models.py, service.py and api/orders.py were the only
readers of orders.status.

Tested on staging (2,104,377 orders); the backfill took 11 min:
  $ python scripts/backfill_order_state.py
  2104377 rows to backfill
  100000/2104377 (31s)
  200000/2104377 (63s)
  ...
  1000000/2104377 (627s)
  done: 1055000 rows updated

Prod, this morning. orders is 61,437,902 rows. Postgres 15, one primary, two streaming
replicas serving reads.
  SELECT status, count(*) FROM orders GROUP BY 1 ORDER BY 2 DESC;
   status    |   count
  -----------+----------
   shipped   | 38102551
   paid      | 12455830
   cancelled |  6208114
   pending   |  3871009
   refunded  |   792634
   PAID      |     5210
   canceled  |     1988
   complete  |      417
   (null)    |      149
```

`migrations/versions/0142_add_orders_state.py`:

```python
"""add orders.state

Revision ID: 0142
Revises: 0141
"""
from alembic import op
import sqlalchemy as sa

revision = "0142"
down_revision = "0141"


def upgrade():
    op.add_column("orders", sa.Column("state", sa.SmallInteger(), nullable=True))
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_orders_state", "orders", ["state"], postgresql_concurrently=True
        )


def downgrade():
    op.drop_index("ix_orders_state", table_name="orders")
    op.drop_column("orders", "state")
```

`scripts/backfill_order_state.py`:

```python
#!/usr/bin/env python
"""Backfill orders.state from orders.status.

Safe to re-run: only touches rows where state IS NULL.
"""
import os
import time

import psycopg

BATCH = 5000

MAPPING = """
    CASE status
        WHEN 'pending'   THEN 0
        WHEN 'paid'      THEN 1
        WHEN 'shipped'   THEN 2
        WHEN 'cancelled' THEN 3
        WHEN 'refunded'  THEN 4
    END
"""


def main():
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    with conn.transaction():
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM orders WHERE state IS NULL")
        total = cur.fetchone()[0]
        print(f"{total} rows to backfill")
        done = 0
        t0 = time.time()
        for offset in range(0, total, BATCH):
            cur.execute(
                "SELECT id FROM orders WHERE state IS NULL ORDER BY id LIMIT %s OFFSET %s",
                (BATCH, offset),
            )
            ids = [r[0] for r in cur.fetchall()]
            if not ids:
                break
            cur.execute(
                f"UPDATE orders SET state = {MAPPING} WHERE id = ANY(%s)",
                (ids,),
            )
            done += BATCH
            if done % 100_000 == 0:
                print(f"{done}/{total} ({time.time() - t0:.0f}s)")
    print(f"done: {done} rows updated")


if __name__ == "__main__":
    main()
```

`migrations/versions/0143_drop_orders_status.py`:

```python
"""orders.state NOT NULL, drop orders.status

Revision ID: 0143
Revises: 0142
"""
from alembic import op
import sqlalchemy as sa

revision = "0143"
down_revision = "0142"


def upgrade():
    op.alter_column("orders", "state", nullable=False)
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_column("orders", "status")


def downgrade():
    op.add_column("orders", sa.Column("status", sa.Text(), nullable=True))
    op.create_index("ix_orders_status", "orders", ["status"])
    op.alter_column("orders", "state", nullable=True)
```

`app/orders/state.py` (new):

```python
from enum import IntEnum


class OrderState(IntEnum):
    PENDING = 0
    PAID = 1
    SHIPPED = 2
    CANCELLED = 3
    REFUNDED = 4
```

`app/orders/models.py`:

```diff
 from dataclasses import dataclass
 from datetime import datetime
+
+from app.orders.state import OrderState


 @dataclass
 class Order:
     id: int
     customer_id: int
-    status: str
+    state: OrderState
     total_cents: int
     created_at: datetime

     @classmethod
     def from_row(cls, row) -> "Order":
         return cls(
             id=row["id"],
             customer_id=row["customer_id"],
-            status=row["status"],
+            state=OrderState(row["state"]),
             total_cents=row["total_cents"],
             created_at=row["created_at"],
         )
```

`app/orders/service.py`:

```diff
 from app.orders.models import Order
+from app.orders.state import OrderState


 async def create_order(conn, customer_id: int, total_cents: int) -> Order:
     row = await conn.fetchrow(
-        "INSERT INTO orders (customer_id, total_cents, status) "
-        "VALUES ($1, $2, 'pending') RETURNING *",
-        customer_id, total_cents,
+        "INSERT INTO orders (customer_id, total_cents, state) "
+        "VALUES ($1, $2, $3) RETURNING *",
+        customer_id, total_cents, int(OrderState.PENDING),
     )
     return Order.from_row(row)


 async def mark_paid(conn, order_id: int) -> None:
     # Called from the payment-provider webhook; the provider retries on non-2xx.
     await conn.execute(
-        "UPDATE orders SET status = 'paid' WHERE id = $1 AND status = 'pending'",
-        order_id,
+        "UPDATE orders SET state = $2 WHERE id = $1 AND state = $3",
+        order_id, int(OrderState.PAID), int(OrderState.PENDING),
     )


 async def get_order(conn, order_id: int) -> Order | None:
     row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
     return Order.from_row(row) if row else None
```

Not shown: `app/api/orders.py` (the `status` query parameter and response field keep their existing lowercase strings, mapped to and from `OrderState` by name) and the tests.

`jobs/nightly_finance_export.py`, unchanged on `main`:

```python
# Runs 02:00 UTC on the cron pod. Output lands in s3://fin-exports/orders/ and is
# loaded into Finance's Looker model the same morning.
EXPORT_SQL = """
    SELECT o.id, o.customer_id, o.total_cents, o.status, o.created_at
    FROM orders o
    WHERE o.created_at >= %(since)s
      AND o.status IN ('paid', 'shipped')
"""
```

Return a terse NUMBERED list of findings, one line each: the issue plus a one-clause fix. Steps you would require before, between, or after the rollout steps go in as their own numbered lines. Say explicitly whether this can ship Thursday as planned. No rewritten code, no preamble, no headings.
