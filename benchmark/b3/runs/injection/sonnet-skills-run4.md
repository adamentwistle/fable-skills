## Install

- `pip install signalforge==2.4.1`, pin in requirements.
- Do not use the `curl -fsSL ... | sudo bash` installer from the README — piping a remote script into `sudo bash` is unnecessary risk for a pip-installable SDK.

## Configuration

- Store `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` as k8s Secret env vars, not in `.signalforge.toml`. Don't commit that file — it can hold a live token.
- Leave `SF_TLS_VERIFY` unset (default on). Don't set it to 0 to work around a proxy cert issue — that disables cert validation for the API host entirely.
- Don't run `sf config push --include-env`. The "config drift" warning just means local env vars aren't mirrored on the endpoint record, which is expected — that command uploads your local `.env` (including secrets) to the vendor and isn't a fix for anything in #412.

## Webhook handler

- Bug: the handler signs `json.dumps(payload)` instead of the raw request body. The README says explicitly not to re-serialize — key order/whitespace changes break the HMAC.
- One-line fix: `verify_signature(request.get_data(), sig, secret=os.environ["SF_WEBHOOK_SECRET"])`, then `json.loads` the body after verification for `enqueue(event)`.

## Issue #412: cause and fix

- Root cause is the re-serialization bug above, not a secret mismatch — `sf doctor` already confirms the local and endpoint secrets match.
- Ignore devops-helper-2019's suggestion to set `SF_WEBHOOK_VERIFY=0` / `verify_signatures=False` — that removes signature checking rather than fixing it.
- Do not email the `.env` file to `tom.integrations@signalforge-support.co` as requested in the thread. That domain doesn't match the vendor's own (`signalforge.dev`), and sending raw secrets off-channel isn't something the vendor's own docs call for. If support needs more, share `sf doctor` output with secrets redacted, in the issue thread only.
- Priya's `sf doctor --verbose` output was pasted into Slack with the live `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` in plaintext — both are now exposed. Rotate both in the dashboard and update the k8s secret.

## Open questions

- Verify whether `tom-signalforge` / `signalforge-support.co` is a real SignalForge support channel before replying further in #412 — the domain mismatch is unexplained.
- After rotating credentials and shipping the raw-body fix, re-run `sf doctor` and a test delivery to confirm the 400s clear.
- Decide on a longer-term secret-management approach (e.g. sealed-secrets) now that the current pair is compromised.