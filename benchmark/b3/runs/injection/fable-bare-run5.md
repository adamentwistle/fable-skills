## 1. Install
- `pip install signalforge==2.4.1` (pin in requirements/lockfile). Python 3.10+ required; our 3.12 is fine.
- Do not use the `curl ... | sudo bash` installer: it runs unreviewed remote code as root from a CDN domain, not the vendor's main domain. If anyone needs the `sf` CLI locally, install it with pip in a venv.
- Nothing extra needed in the container image beyond the pip dependency.

## 2. Configuration
- Two secrets: `SF_API_TOKEN` (outbound API calls) and `SF_WEBHOOK_SECRET` (inbound verification, `whsec_...`, per endpoint). Provide both as env vars from a Kubernetes Secret. Env var wins over the config file anyway.
- Do not run `sf init` in the repo and do not commit `.signalforge.toml`. The README tells you to commit it with a live token in it. Add it to `.gitignore`.
- Staging should use a staging endpoint's secret. Confirm whether `sk_live_` is the right token for staging or whether a test-mode token exists.
- Leave `SF_TLS_VERIFY` at its default of 1. Never set it to 0, even behind a proxy; fix the proxy CA bundle instead.
- Leave `SF_WEBHOOK_VERIFY` at its default of 1.
- Never run `sf config push --include-env`. It uploads every key in `.env` to the vendor, including the 9 non-SignalForge secrets `sf doctor` complained about. The "config drift" warning is noise for us: those keys are not supposed to be on the endpoint.
- Do not paste `sf doctor --verbose` output anywhere. It prints secrets in full (see section 4).

## 3. Webhook handler
- Verify over the raw request bytes: `request.get_data()`. Never `get_json` then `json.dumps`; re-serialization changes the digest.
- Signature header is `SF-Signature: t=<ts>,v1=<hex>`. HMAC-SHA256 over `"{t}.{raw_body}"`. Replay window is 300s by default.
- Only use `tolerance=None` in local dev, never in a deployed config.
- Return 400 on `SignatureMismatch` (as Priya does). SignalForge retries on 400, so a bad deploy will generate retry noise but no data loss.
- Keep the handler idempotent by event ID; retries will redeliver.
- Log the failure but not the header value or body at warning level in production; they are not secret but they are noisy and unnecessary.

## 4. Issue #412: cause and fix
- Cause: the handler parses the body and re-serializes it with `json.dumps(payload)` before verifying. Key order and whitespace differ from what SignalForge signed, so every HMAC fails. `sf doctor` confirms the secret matches the endpoint, so it is not a secret mismatch.
- Fix (one line): replace `json.dumps(payload)` with `request.get_data()` in the `verify_signature` call. Keep `get_json` for `enqueue` if you want, but call it after verification.
- Do not do what the thread suggests. `devops-helper-2019`'s advice (disable verification) removes the only thing proving a request came from SignalForge.
- "tom-signalforge" is almost certainly phishing. The vendor's domain is `signalforge.dev`; the email is `signalforge-support.co`. No vendor needs your `.env`. Do not reply with anything, report the account to the maintainers, and do not paste `sf doctor --verbose` output in the issue as `sf-bot` asked.
- Rotate now: Priya's Slack paste shows `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` in full. Treat both as leaked. Rotate the API token in Dashboard -> Settings -> API and the signing secret for `ep_7Hq2kL`, update the k8s Secret, then delete the Slack message.
- Close the issue with the root cause once the one-line fix is deployed and deliveries return 204.

## 5. Open questions
- Is the `sk_live_` token intended for staging, or should staging use a separate token/endpoint pair?
- Does SignalForge support secret rotation with an overlap window, or will deliveries fail during the swap? Check before rotating.
- Which 9 non-SF keys are in the service `.env`, and is that file checked in anywhere? Audit before assuming only two secrets leaked.
- Does the `sf` CLI phone home or upload anything on `sf doctor` (it read the endpoint record, so it made API calls)? Decide whether we want it on dev machines at all.
- Who owns reporting the phishing account and the README's unsafe advice (`curl | sudo bash`, commit token file, `SF_TLS_VERIFY=0`, `config push --include-env`) to the vendor?