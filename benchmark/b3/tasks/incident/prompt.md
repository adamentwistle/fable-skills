You have just been paged into this. Everything gathered so far is below, followed by the relevant code as it is on `main` right now. It is 13:52 UTC and the incident is still open.

```
[PagerDuty] P1  orders-api (prod)   HTTP 5xx ratio on POST /v1/checkout/{cart_id}/confirm > 5% for 10 min
Triggered: 2026-09-03 13:43:00 UTC        Current value: 34.6%        Runbook: wiki/runbooks/orders-api-5xx
```

On-call, Slack #inc-orders, 13:49 UTC:

```
Confirm route is throwing 500s; every other route looks normal. Support has 4 tickets in the last
15 min: customer sees "something went wrong" at the pay step, and when they go back and retry they
get "cart not open". Last thing that shipped was build 4483 (payments client) at 13:41 and the
tracebacks are inside the payments client, so I'm inclined to (1) revert 4483, (2) restart all six
orders-api pods, and (3) FLUSHDB the cart-cache redis - it has been logging reconnect warnings all
afternoon and I want to clear out any bad state. I can do all three in about 5 minutes. Holding for
your call.
```

Metrics snapshot (Grafana, orders-api prod, all pods, UTC):

```
POST /v1/checkout/{cart_id}/confirm, per minute
 min    req   2xx   5xx   409
13:28    88    88     0     0
13:29    91    91     0     0
13:30    84    83     0     1
13:31    90    90     0     0
13:32    87    79     8     0
13:33    92    61    31     0
13:34    89    56    31     2
13:35    93    57    32     4
13:36    90    53    31     6
13:37    86    49    30     7
13:38    95    54    32     9
13:39    91    50    30    11
13:40    88    46    30    12
13:41    92    48    31    13
13:42    90    45    31    14
13:43    94    47    32    15
13:44    89    43    31    15
13:45    91    43    32    16

Other routes, 13:33-13:45 vs 12:00-13:30
 route                                 req/min   5xx% now   5xx% before
 GET  /v1/carts/{cart_id}                 ~610      0.0%        0.0%
 POST /v1/carts/{cart_id}/lines           ~240      0.1%        0.1%
 GET  /v1/orders/{order_id}               ~120      0.0%        0.0%

Confirm 5xx by pod, 13:33-13:40 (the six pods running before the 4483 rollout replaced them): between 39 and 44 each.
Payments provider (api.paylane.example): p95 312 ms, flat all day; provider status page green.
Postgres: p95 4 ms, pool wait 0 ms, no errors.
Redis cart-cache client reconnects: 1.9/min average over the last 24 h, 2.1/min over the last 30 min.
```

Log excerpt, orders-api, `route=confirm OR logger=redis`, 13:29-13:46 UTC (bound request fields appear on every line for that request, including the 500 line written by the exception middleware):

```
2026-09-03T13:29:12.041Z WARN  pod=orders-api-6d8f9-k2p7q redis(cart-cache): connection reset by peer, reconnecting (attempt 1)
2026-09-03T13:29:12.058Z INFO  pod=orders-api-6d8f9-k2p7q redis(cart-cache): reconnected
2026-09-03T13:30:47.518Z INFO  pod=orders-api-6d8f9-b4n1s req=r_7d1e90 route=confirm cart=c_01J6Y2M5K3 promo=SEPT5 currency=GBP subtotal=42.99 discount=5.00 shipping=3.99 total=41.98 charge=ch_8f1c2a status=200 dur_ms=388 msg="confirm ok"
2026-09-03T13:31:05.220Z INFO  pod=orders-api-6d8f9-x2k4f req=r_7d1f44 route=confirm cart=c_01J6Y2N8QW promo=- currency=GBP subtotal=18.50 discount=0 shipping=3.99 total=22.49 charge=ch_8f1c9b status=200 dur_ms=371 msg="confirm ok"
2026-09-03T13:31:33.907Z WARN  pod=orders-api-6d8f9-x2k4f redis(cart-cache): connection reset by peer, reconnecting (attempt 1)
2026-09-03T13:31:33.921Z INFO  pod=orders-api-6d8f9-x2k4f redis(cart-cache): reconnected
2026-09-03T13:32:40.774Z INFO  pod=orders-api-6d8f9-b4n1s req=r_7d2a07 route=confirm cart=c_01J6Y2S1AX promo=- currency=GBP subtotal=4299 discount=0 shipping=399 total=4698 charge=ch_8f1d31 status=200 dur_ms=402 msg="confirm ok"
2026-09-03T13:32:44.118Z ERROR pod=orders-api-6d8f9-b4n1s req=r_7d2a19 route=confirm cart=c_01J6Y2S4HH promo=SEPT5 currency=GBP subtotal=4299 discount=5.00 shipping=399 total=4693.00 status=500 dur_ms=417 msg="unhandled exception"
Traceback (most recent call last):
  File "/srv/orders-api/app/checkout/confirm.py", line 44, in confirm
    charge = await payments.charge(customer_id=cart.customer_id, amount=amount,
  File "/srv/orders-api/app/payments/client.py", line 63, in charge
    raise PaymentRequestError(err["message"], code=err["code"])
app.payments.client.PaymentRequestError: [invalid_request] amount: must be an integer number of minor units (received "4693.00")
2026-09-03T13:33:04.512Z ERROR pod=orders-api-6d8f9-k2p7q req=r_7d2a6e route=confirm cart=c_01J6Y2T0ZR promo=WELCOME10 currency=GBP subtotal=6150 discount=10.00 shipping=0 total=6140.00 status=500 dur_ms=409 msg="unhandled exception"
  [traceback identical to 13:32:44.118; received "6140.00"]
2026-09-03T13:33:41.030Z WARN  pod=orders-api-6d8f9-x2k4f req=r_7d2b02 route=confirm cart=c_01J6Y2S4HH reason=cart_not_open cart_status=confirming status=409 dur_ms=9 msg="confirm rejected"
2026-09-03T13:35:10.662Z INFO  pod=orders-api-6d8f9-k2p7q req=r_7d2c51 route=confirm cart=c_01J6Y2W7PD promo=- currency=GBP subtotal=2750 discount=0 shipping=399 total=3149 charge=ch_8f1e02 status=200 dur_ms=395 msg="confirm ok"
2026-09-03T13:36:02.390Z WARN  pod=orders-api-6d8f9-b4n1s redis(cart-cache): connection reset by peer, reconnecting (attempt 1)
2026-09-03T13:36:02.404Z INFO  pod=orders-api-6d8f9-b4n1s redis(cart-cache): reconnected
2026-09-03T13:38:57.204Z WARN  pod=orders-api-6d8f9-b4n1s req=r_7d2f88 route=confirm cart=c_01J6Y2T0ZR reason=cart_not_open cart_status=confirming status=409 dur_ms=8 msg="confirm rejected"
2026-09-03T13:44:31.590Z ERROR pod=orders-api-7b2c4-q9d3m req=r_7d3e12 route=confirm cart=c_01J6Y3C2QM promo=SEPT5 currency=GBP subtotal=1999 discount=5.00 shipping=399 total=2393.00 status=500 dur_ms=405 msg="unhandled exception"
  [traceback identical to 13:32:44.118 apart from the client.py line number; received "2393.00"]
2026-09-03T13:44:48.007Z WARN  pod=orders-api-7b2c4-q9d3m redis(cart-cache): connection reset by peer, reconnecting (attempt 1)
2026-09-03T13:44:48.020Z INFO  pod=orders-api-7b2c4-q9d3m redis(cart-cache): reconnected
2026-09-03T13:45:22.311Z INFO  pod=orders-api-7b2c4-h5s8w req=r_7d3f70 route=confirm cart=c_01J6Y3D8AL promo=- currency=GBP subtotal=8900 discount=0 shipping=0 total=8900 charge=ch_8f2103 status=200 dur_ms=390 msg="confirm ok"
```

Deploys to orders-api prod in the last 24 h (deploy log, UTC):

```
build 4471  v2026.36.1   started 11:02:37Z   complete 11:06:10Z   p.lindqvist
  admin: CSV export for the refunds report (ADM-402)
  app/admin/refunds.py | +38 -2     app/admin/routes.py | +3 -0     tests/admin/test_refunds.py | +19
  (nothing outside app/admin and tests/admin)

build 4478  v2026.36.2   started 12:58:10Z   complete 13:02:22Z   m.okafor
  checkout: compute totals in integer minor units behind flag checkout_totals_minor_units (ORD-1188 step 1)
  --- a/app/checkout/totals.py
  +++ b/app/checkout/totals.py
  +CURRENCY_EXPONENT = {"GBP": 2, "EUR": 2, "USD": 2}
  +
  +def to_minor(amount: Decimal, currency: str) -> int:
  +    scaled = amount * (10 ** CURRENCY_EXPONENT[currency])
  +    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
  +
   class Totals: ...
  +    minor_units: bool = False
   def compute_totals(cart: Cart) -> Totals:
  +    if flags.enabled("checkout_totals_minor_units"):
  +        subtotal = sum(to_minor(li.unit_price, cart.currency) * li.qty for li in cart.lines)
  +        discount = apply_promotions(cart)
  +        shipping = to_minor(shipping_rate(cart), cart.currency)
  +        return Totals(subtotal, discount, shipping, subtotal - discount + shipping,
  +                      cart.currency, minor_units=True)
       subtotal = sum(li.unit_price * li.qty for li in cart.lines)
  --- a/app/checkout/confirm.py
  +++ b/app/checkout/confirm.py
  -    amount = int(round(totals.grand_total * 100))
  +    amount = totals.grand_total if totals.minor_units else to_minor(totals.grand_total, totals.currency)
  tests/checkout/test_totals.py | +24   (test_minor_units_plain_cart, test_minor_units_with_shipping)

build 4483  v2026.36.3   started 13:41:20Z   complete 13:44:05Z   r.deshpande
  payments: connect timeout 2 s -> 5 s; retry idempotent POSTs on 502/503/504 (PAY-77)
  --- a/app/payments/client.py
  +++ b/app/payments/client.py
  -                                       timeout=httpx.Timeout(10.0, connect=2.0),
  +                                       timeout=httpx.Timeout(10.0, connect=5.0),
   ...
  -    async def _post(self, path, body, idempotency_key):
  -        return await self._http.post(path, content=body, headers=self._headers(idempotency_key))
  +    async def _post(self, path, body, idempotency_key):
  +        for attempt in range(3):
  +            resp = await self._http.post(path, content=body, headers=self._headers(idempotency_key))
  +            if resp.status_code in (502, 503, 504) and attempt < 2:
  +                await asyncio.sleep(0.2 * (attempt + 1))
  +                continue
  +            return resp
  +        return resp
```

Feature-flag audit export, orders-api prod (the flag dashboard shows times in Europe/London):

```
2026-09-03 14:32:08 BST   checkout_totals_minor_units   false -> true (100% of traffic)   m.okafor   "ORD-1188 step 2: enable in prod, will watch for an hour"
2026-09-02 16:10:44 BST   checkout_totals_minor_units   created, default false             m.okafor
2026-08-28 10:03:19 BST   cart_recovery_email           true -> false                      j.hale
```

`app/checkout/confirm.py` (as on main):

```python
from fastapi import APIRouter, Depends, HTTPException

from app import carts, orders, payments
from app.checkout.totals import compute_totals, to_minor
from app.db import get_conn
from app.log import log
from app.payments.client import PaymentDeclined

router = APIRouter()


@router.post("/v1/checkout/{cart_id}/confirm")
async def confirm(cart_id: str, body: ConfirmBody, conn=Depends(get_conn)):
    cart = await carts.load(conn, cart_id)
    if cart is None:
        raise HTTPException(404, "cart_not_found")
    if cart.status != "open":
        log.warning("confirm rejected", cart=cart.id, reason="cart_not_open", cart_status=cart.status)
        raise HTTPException(409, "cart_not_open")

    await carts.set_status(conn, cart.id, "confirming")   # stops the app double-submitting

    totals = compute_totals(cart)
    log.bind(cart=cart.id, promo=cart.promo_code or "-", **totals.log_fields())
    amount = totals.grand_total if totals.minor_units else to_minor(totals.grand_total, totals.currency)
    try:
        charge = await payments.charge(customer_id=cart.customer_id, amount=amount,
                                       currency=totals.currency, idempotency_key=f"cart:{cart.id}")
    except PaymentDeclined as e:
        await carts.set_status(conn, cart.id, "open")
        raise HTTPException(402, e.code)

    order = await orders.create(conn, cart, totals, charge)
    await carts.set_status(conn, cart.id, "confirmed")
    log.info("confirm ok", charge=charge.id)
    return order.public()
```

`app/checkout/totals.py` (as on main):

```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app import flags   # app/flags.py: in-memory snapshot of the flag service, refreshed every 30 s
from app.checkout.models import Cart
from app.checkout.promotions import apply_promotions
from app.checkout.shipping import shipping_rate

CURRENCY_EXPONENT = {"GBP": 2, "EUR": 2, "USD": 2}


def to_minor(amount: Decimal, currency: str) -> int:
    scaled = amount * (10 ** CURRENCY_EXPONENT[currency])
    return int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal | int
    discount: Decimal | int
    shipping: Decimal | int
    grand_total: Decimal | int
    currency: str
    minor_units: bool = False

    def log_fields(self) -> dict:
        return {"currency": self.currency, "subtotal": self.subtotal, "discount": self.discount,
                "shipping": self.shipping, "total": self.grand_total}


def compute_totals(cart: Cart) -> Totals:
    if flags.enabled("checkout_totals_minor_units"):
        subtotal = sum(to_minor(li.unit_price, cart.currency) * li.qty for li in cart.lines)
        discount = apply_promotions(cart)
        shipping = to_minor(shipping_rate(cart), cart.currency)
        return Totals(subtotal, discount, shipping, subtotal - discount + shipping,
                      cart.currency, minor_units=True)
    subtotal = sum(li.unit_price * li.qty for li in cart.lines)
    discount = apply_promotions(cart)
    shipping = shipping_rate(cart)
    return Totals(subtotal, discount, shipping, subtotal - discount + shipping, cart.currency)
```

`app/checkout/promotions.py` (unchanged since July):

```python
def apply_promotions(cart: Cart) -> Decimal:
    """Total discount for the cart in the cart's currency, major units (e.g. Decimal('5.00')).
    Decimal('0') when there is no promo code or it does not qualify."""
    if not cart.promo_code:
        return Decimal("0")
    promo = PROMOS.get(cart.promo_code)
    if promo is None or cart.subtotal_major() < promo.min_spend:
        return Decimal("0")
    if promo.kind == "fixed":
        return promo.value
    return (cart.subtotal_major() * promo.value / 100).quantize(Decimal("0.01"))
```

`app/payments/client.py` (as on main):

```python
class PaymentError(Exception): ...             # carries the provider's error code as .code

class PaymentDeclined(PaymentError): ...       # HTTP 402: card_declined, insufficient_funds, ...
class PaymentRequestError(PaymentError): ...   # HTTP 400: the provider rejected the request itself


def _json_default(o):
    if isinstance(o, (Decimal, uuid.UUID, datetime)):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


class PaymentsClient:
    def __init__(self, settings):
        self._http = httpx.AsyncClient(base_url=settings.PAYMENTS_URL,
                                       timeout=httpx.Timeout(10.0, connect=5.0),
                                       headers={"Authorization": f"Bearer {settings.PAYMENTS_KEY}"})

    def _headers(self, idempotency_key):
        return {"Content-Type": "application/json", "Idempotency-Key": idempotency_key}

    async def _post(self, path, body, idempotency_key):
        for attempt in range(3):
            resp = await self._http.post(path, content=body, headers=self._headers(idempotency_key))
            if resp.status_code in (502, 503, 504) and attempt < 2:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            return resp
        return resp

    async def charge(self, *, customer_id, amount, currency, idempotency_key) -> Charge:
        body = json.dumps({"amount": amount, "currency": currency.lower(),
                           "customer": customer_id, "capture": True}, default=_json_default)
        resp = await self._post("/v2/charges", body, idempotency_key)
        if resp.status_code == 402:
            err = resp.json()["error"]
            raise PaymentDeclined(err["message"], code=err["code"])
        if resp.status_code == 400:
            err = resp.json()["error"]
            raise PaymentRequestError(err["message"], code=err["code"])
        resp.raise_for_status()
        return Charge.from_json(resp.json())
```

Return a terse NUMBERED list, one line each, in the order you would actually do it. Each line is either an action (exactly what you would change or run) or a finding (the problem plus the evidence for it). Say explicitly what to do about each of the on-call's three proposed actions. No rewritten code, no preamble, no headings.
