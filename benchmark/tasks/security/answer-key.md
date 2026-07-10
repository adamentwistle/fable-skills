<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07): the answer-key section of the blind-grader prompt for the security area, unmodified. -->

Here is the answer key — the 14 distinct issue classes present in the code:
1. SQL injection (user_id/status interpolated into query)
2. DB connection never closed (leak)
3. format_receipt TypeError ("Order #" + int id)
4. Division by zero when orders is empty
5. Money handled as binary float (should be Decimal/cents)
6. apply_discount: pct not range-validated (negative/>100)
7. status not validated against an allowlist
8. Broken object-level authorization / IDOR (user_id trusted from request, not session)
9. Null/None amount not handled
10. Currency not formatted to 2 decimals
11. Raw DB errors leak to caller (no sanitization/chaining)
12. Rounding is a policy decision not applied (fractional cents mid-calc)
13. Unbounded result set (no LIMIT / pagination)
14. Fragile positional tuple indexing (sqlite3.Row / name access more robust)
