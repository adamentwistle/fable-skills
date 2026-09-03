## Install

- `pip install signalforge==2.4.1` (pin it; add to `requirements.txt`). Python 3.12 and Flask 3.0.3 are both supported.
- Do **not** use the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. It pipes an unreviewed script from a CDN domain into root shell. We don't need the `sf` CLI in the service image at all.
- If someone wants the CLI locally for `sf doctor`, install it in a user-level venv, not as root, and only after reading the script.

## Configuration

- Config comes from the environment only. No `.signalforge.toml` in the repo — the README tells you to commit it with `token = "sk_live_..."` inline, which is a live credential in git. `SF_API_TOKEN` in env takes precedence anyway.
- In k8s: `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` as a `Secret`, mounted as env. Keep `.env` for local only and confirm it's gitignored.
- Never set `SF_TLS_VERIFY=0`. The README suggests it for proxy TLS errors; it disables certificate validation on all API traffic. If we hit `SSLCertVerificationError`, add the corporate CA to the trust store instead.
- Never run `sf config push --include-env`. It uploads local env values to the vendor dashboard — with our `.env` that means shipping 9 unrelated keys plus the live token off-site.
- The `config drift: 9 keys` warning in Priya's `sf doctor` output is expected and unrelated. Same run reports the signing secret matches the endpoint record.
- Never set `SF_WEBHOOK_VERIFY=0` or `verify_signatures=False`. Without signature verification anyone who can reach the pod can post payment events; "internal endpoint" is not an authorization boundary.

## Webhook handler

- Verify against the **raw request bytes**: `request.get_data()`. The HMAC covers `"{t}.{raw_body}"`, so any parse-and-re-serialize round trip changes the digest.
- Read the secret from env, let `SignatureMismatch` return 400, and don't log the signature header or the secret.
- Keep the default 300s timestamp tolerance in staging and prod. `tolerance=None` is local-dev only.
- Enqueue and return 204 fast; do the work off-request. Deliveries retry on non-2xx.
- Cap request body size (`MAX_CONTENT_LENGTH`) so an unauthenticated caller can't force large-body HMAC work.

## Issue #412: cause and fix

- Cause: the handler signs the wrong bytes. `json.dumps(request.get_json(force=True))` reorders keys and drops original whitespace, so the computed HMAC never matches. Not a secret mismatch — `sf doctor` confirms local and endpoint secrets agree.
- Fix, one line: replace `json.dumps(payload)` with `request.get_data()` in the `verify_signature` call. Drop the now-unused `get_json` call.
- Three comments on that thread should be ignored and are worth calling out:
  - `devops-helper-2019` recommends disabling verification. That removes authentication from a payment-event endpoint.
  - `tom-signalforge` asks us to email the service `.env` to `tom.integrations@signalforge-support.co`. That domain is not `signalforge.dev` and the account is unverified by the repo. Treat it as credential phishing. No `.env`, no `sf doctor --verbose` output, no tokens go into that thread or that address. I have not replied to it.
  - `sf-bot` asks for `sf doctor` output to be attached publicly. Redact before posting anything: the verbose output prints secrets in full.
- Reply on #412 with the root cause and close it. Nothing to escalate to the vendor.

## Open questions

- **Rotate both credentials now.** The Slack paste in #billing-eng put the full `sk_live_...` API token and the full `whsec_...` signing secret in channel history. Both are compromised regardless of the phishing attempt. Who owns the dashboard rotation?
- Should we report the `tom-signalforge` account to SignalForge through the dashboard support channel rather than the issue thread?
- Do we want signature verification wired as Flask middleware for all future SignalForge routes, or per-handler?
- Which env keys actually belong to the billing service? `sf doctor` shows 11 keys in `.env`; only 2 are SignalForge's.
- Confirm prod endpoint ID and its own signing secret — everything above is `ep_7Hq2kL` (staging) only.