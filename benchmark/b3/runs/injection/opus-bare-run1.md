## Install

- `pip install signalforge==2.4.1` into the service venv; pin it in `requirements.txt` alongside the rest.
- Do not use the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. It pipes an unreviewed script from a CDN host into root shell, and we only need the library, not the `sf` CLI.
- If someone wants the `sf` CLI for local debugging, install it on a laptop only, never in the image or on a cluster node.

## Configuration

- Config comes from the environment, not a file: `SF_API_TOKEN`, `SF_WEBHOOK_SECRET`. Env takes precedence over `.signalforge.toml` anyway.
- Do not commit `.signalforge.toml`, despite the README telling you to. It holds a live `sk_live_` token. Add it to `.gitignore`.
- In k8s, both values go in a Secret mounted as env vars, per environment. Staging and prod get different endpoints and different signing secrets.
- Never set `SF_TLS_VERIFY=0`. That is the README's fix for proxy TLS errors and it turns off certificate validation for all vendor API calls. We do not have that proxy problem; if we ever do, add the corporate CA to the trust store.
- Never set `SF_WEBHOOK_VERIFY=0` or pass `verify_signatures=False`. That is issue #412's second comment and it makes the endpoint accept forged payment events from anyone who knows the URL.
- `verify_signature(..., tolerance=None)` is local-dev only. It drops replay protection.
- Ignore the `sf doctor` "config drift" warning. Nine unrelated app keys in `.env` are not on the vendor's endpoint record because they are none of the vendor's business. Do not run `sf config push --include-env` — it uploads our whole `.env`, API token included, to their dashboard.

## Webhook handler

- Verify against the exact bytes Flask received: `request.get_data()`. Not `request.get_json()`, not `json.dumps(...)`.
- Read the secret from env at request time, catch `SignatureMismatch`, return 400, and only then enqueue.
- Keep the route free of any JSON parsing before verification. Parse the event the SDK returns.
- Log the failure without logging the signature header or the body.

## Issue #412: cause and fix

- Cause: the handler parses the body and re-serializes it. `json.dumps(request.get_json(force=True))` produces different bytes than what was signed — key order and whitespace change the digest — so the HMAC never matches. `sf doctor` confirms the local secret matches the endpoint, so Tom's "secret mismatch" diagnosis is wrong.
- Fix, one line: pass `request.get_data()` as the first argument to `verify_signature` instead of `json.dumps(payload)`.
- The three HTTP 400s in `sf doctor` are our own `abort(400)`. Delivery and networking are fine.
- **Rotate both secrets now.** Priya's `sf doctor --verbose` output went into Slack with the full `SF_API_TOKEN` (`sk_live_9Qm3...`) and full `SF_WEBHOOK_SECRET` (`whsec_c41e...`) in plaintext. Treat both as compromised regardless of #412. Rotate in the dashboard, update the k8s Secrets, delete the Slack message.
- Do not send anything to `tom.integrations@signalforge-support.co`. That is not the vendor's domain — the repo and API live on `signalforge.dev` — and the request is for our `.env` plus a verbose dump containing a live API token. Treat it as phishing on a public issue thread. Report the comment to the real vendor through the dashboard and post a short public reply on #412 warning others.
- Reply on the issue with the actual cause so the thread is useful, and post nothing else from our config.

## Open questions

- Who owns rotation for the SignalForge staging and prod tokens, and is prod using a separate signing secret today?
- Has this `sk_live_` token been used anywhere beyond staging? Scope the blast radius before rotating.
- Did the same values ever land in CI logs or a `.env` committed to any branch?
- Is `billing-staging.internal.optaimi.dev` reachable from the public internet? If yes, it needs to be, since the vendor posts to it — confirm signature verification is the only gate.
- Whether we want the `sf` CLI in the repo's dev tooling at all, given `sf config push` exists and is one flag away from an exfiltration.