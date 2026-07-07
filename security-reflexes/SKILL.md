---
name: security-reflexes
description: Security checklists for everyday diffs — parameterize at trust boundaries, allowlist enums, per-object authorization, secrets never in logs/bundles/errors. Apply while writing any code touching user input, authn/authz, secrets, paths, URLs, subprocesses, SQL, HTML rendering, or external APIs.
---

# Security Reflexes

Not a pentest methodology — these are the reflexes that fire while writing ordinary code. Scan the diff you're producing against whichever sections its surfaces touch.

## Input crossing a trust boundary

Any value originating from a user, client, LLM, or external system:
- **Parameterize, never concatenate**: SQL/queries via placeholders; shell via array-arg APIs (no string-built commands); paths via join + canonicalize + prefix check (traversal: `../`).
- **Validate at the boundary, by allowlist**: enums/slugs mapped through a server-side whitelist — especially LLM-generated values headed into external APIs. Reject unexpected keys, not just missing ones.
- **HTML**: rendering user/model text as raw HTML is an XSS. Keep markdown renderers raw-HTML-off (no rehype-raw equivalents); escape by default.
- **URLs the server will fetch**: validate scheme+host against an allowlist (SSRF) — a user-supplied URL fetched server-side can reach internal services/metadata endpoints.

## AuthN / AuthZ

- Every mutating endpoint: WHO is calling (authentication) and MAY they touch THIS object (authorization — ownership check on the specific row/resource, not just "is logged in").
- Never trust client-supplied identity/scope fields (user IDs, account IDs, role flags, prices, approved-params). The server derives them from the session or its own records.
- Approval flows: bind execution to a server-recorded intent; the client conveys a reference, never the parameters.

## Secrets

- Secrets come from env/secret managers only — never hardcoded, never in client bundles (watch framework prefixes that expose env to the browser), never in logs (including "debug" logs of full request/response objects), never in error messages echoed to users.
- External API errors: wrap/sanitize before showing users — raw provider errors leak internal detail.
- Never ask for or accept credentials that identify a human irreversibly (private keys, seed phrases) even "just to test".

## Dangerous defaults to catch in review

- `JSON.parse`/deserialization of external input without try/catch and shape validation.
- Comparing secrets with `==`/`===` (timing) where a constant-time compare exists — matters for tokens/signatures.
- Missing rate limiting/size caps on endpoints that do expensive work or send messages.
- CORS `*` on authenticated routes; cookies without httpOnly/secure/sameSite thought.
- Temp files/predictable paths for sensitive data; world-readable perms.

## When the change is security-relevant by nature

If the diff touches auth flows, crypto, session handling, or permission checks: slow down, find the existing pattern in the codebase and match it exactly (bespoke crypto/session logic is almost always the bug), and say explicitly in your report which security property you preserved and how you verified it.

## Escalate, don't improvise

Discovering an existing vulnerability mid-task → report it clearly (what, where, exploitability) rather than silently fixing beyond scope or ignoring it. Destructive proof-of-concepts and exploit tooling need explicit authorization context.
