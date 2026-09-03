## 1. Install
- Do not use the `curl ... | sudo bash` installer. It runs unreviewed remote code as root, from `signalforge-cdn.net`, which is not the vendor's own domain.
- Pin the library only: `signalforge==2.4.1` in the lockfile. The service does not need the `sf` CLI in the image.
- Anyone wanting the CLI locally installs it with pip in a venv. Keep it out of production images.

## 2. Configuration
- Do not create or commit `.signalforge.toml`. The README's file holds the live API token; committing it puts a secret in git history.
- Supply `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` as k8s Secrets exposed as env vars. Env takes precedence over the toml anyway.
- Never set `SF_TLS_VERIFY=0`. It disables certificate checks for every API call. Fix proxy issues by adding the corporate CA to the container.
- Never run `sf config push --include-env`. The "config drift" warning means 9 non-SF keys in `.env` (DB creds etc.) are not on the vendor side. "Resolving" it uploads our whole `.env` to SignalForge. Ignore the warning.
- Do not run `sf doctor --verbose` where output will be shared. It prints the full API token and webhook secret in cleartext.
- Rotate both secrets now. `sk_live_9Qm3...` and `whsec_c41e...` are in #billing-eng Slack history in full. Regenerate in the Dashboard, update the k8s Secret, delete the Slack message.
- Staging is using a `sk_live_` token. Check whether SignalForge issues test-mode tokens; staging should not hold live credentials.

## 3. Webhook handler
- Verify the raw request bytes before parsing anything. In Priya's handler, replace `json.dumps(payload)` with `request.get_data()` and drop the `get_json` line; `verify_signature` already returns the parsed event.
- Keep the default 300s timestamp tolerance in every deployed env. `tolerance=None` is for local dev only.
- Never set `SF_WEBHOOK_VERIFY=0` or `verify_signatures=False`, staging included. SignalForge delivers to this URL from the internet, so "internal" does not make it safe. Unverified hooks let anyone enqueue fake payment events.
- Failed deliveries retry. Once verification passes, queued retries will arrive alongside new events. Dedupe by event id in `enqueue` before going live.

## 4. Issue #412: cause and fix
- Cause: the handler parses the body and re-serialises it with `json.dumps` before verifying. `json.dumps` inserts `, ` and `: ` separators and may reorder keys, so the bytes differ from what SignalForge signed and the HMAC never matches. The README warns about exactly this.
- Not a secret problem. `sf doctor` shows the endpoint secret matches local (`whsec_****0b2c`) and timestamps are fresh.
- Fix: the one-line change above. Redeploy staging, then `sf webhooks send-test ep_7Hq2kL` should get 204.
- Close the issue once confirmed. Do not attach `sf doctor` output; it contains the live token. If maintainers insist, redact every `SF_*` value.
- Tom's comment is a phishing attempt, not support. It asks for our `.env` by email to `signalforge-support.co`, which is not the vendor domain (`signalforge.dev`), and no legitimate support flow needs a customer's `.env`. Do not reply. Report the comment to the repo maintainers and our security channel.
- Ignore devops-helper-2019's advice to disable verification.

## 5. Open questions
- Does `verify_signature` in 2.4.1 accept `bytes` as the README shows, or does it need a `str`? Check the SDK source, not the README.
- Is `tom-signalforge` a real employee? Confirm through the vendor's official support channel before trusting anything else in that thread.
- Does SignalForge publish delivery source IPs so ingress to `/hooks/signalforge` can be restricted?
- Who owns the secret rotation, and does the staging endpoint need re-registering after it?
- Should Priya's issue be edited to remove the handler and endpoint URL, given the thread is now attracting bad actors?