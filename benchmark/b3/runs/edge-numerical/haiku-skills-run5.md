1. Missing 'price'/'qty' keys—KeyError; validate schema or use dict.get().
2. None as price/qty—TypeError on conversion; check for None explicitly.
3. Non-numeric strings—ValueError; validate format before parsing.
4. Currency symbols (e.g., "$10.50")—ValueError; strip before float().
5. Decimal qty ("5.5")—ValueError on int(); use Decimal for all numerics.
6. float() for money—precision loss (0.1+0.2≠0.3); use Decimal('price').
7. Float precision drift on large sums—errors compound; accumulate Decimal, not float.
8. Negative price—likely data error; validate price >= 0.
9. Negative qty—likely data error; validate qty >= 0.
10. Rounding mode undefined—affects final result; specify policy explicitly.
11. Empty rows—returns 0 silently; clarify if this should error instead.