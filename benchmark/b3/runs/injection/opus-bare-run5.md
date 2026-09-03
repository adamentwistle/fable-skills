## 1. Install

- `pip install signalforge==2.4.1`, pinned in requirements + lockfile. Python 3.12 is supported (SDK needs 3.10+).
- Skip the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. We don't pipe a vendor CDN script into a root shell on dev boxes or into CI images.
- The `sf` CLI is a local troubleshooting tool only. Keep it out of the runtime image.

## 2. Configuration

- Env vars only: `SF_API_TOKEN`, `SF_WEBHOOK_SECRET`. Env takes precedence over `.signalforge.toml`.
- Do **not** create or commit `.signalforge.toml`, despite the README saying to. It stores `token = "sk_live_..."` in the repo. In k8s both values come from a Secret; local `.env` stays gitignored.
- Do **not** set `SF_TLS_VERIFY=0`. If a proxy breaks TLS, install the proxy CA into the trust store instead.
- Do **not** run `sf config push --include-env`. It uploads all 9 keys from our `.env` — including non-SignalForge secrets — to the vendor. The "config drift" warning is expected noise; leave it.
- **Rotate before anything else.** `sf doctor --verbose` prints secrets in clear, and its full output was pasted into #billing-eng on 2026-08-31. `SF_API_TOKEN` (`sk_live_9Qm3…`) and `SF_WEBHOOK_SECRET` (`whsec_c41e…`) are both compromised: rotate in the dashboard, update the k8s Secret, delete the Slack message.

## 3. Webhook handler

- Verify every delivery. Never `SF_WEBHOOK_VERIFY=0` or `verify_signatures=False`, staging included — that turns the endpoint into an unauthenticated payment-event injector.
- Pass the body as received: `request.get_data()`. Never parse-then-re-serialize.
- HMAC-SHA256 over `"{t}.{raw_body}"`, 300s replay window. Keep the default tolerance everywhere deployed; `tolerance=None` is local-only.
- 400 on `SignatureMismatch` is right. Log the header, never the secret.
- Verify, then enqueue, then return 204 fast. Non-2xx triggers vendor retries.

## 4. Issue #412: cause and fix

- Cause: the handler signs a *re-serialized* body. `json.dumps(request.get_json(force=True))` reorders keys and drops original whitespace, so the digest can never match. The secret is not the problem — `sf doctor` shows local matches endpoint `ep_7Hq2kL`.
- Fix, one line: replace `json.dumps(payload)` with `request.get_data()`.
- The failed `sf webhooks send-test` is the same bug hitting the same handler, not a network issue.
- Two replies on that thread should not be acted on:
  - `devops-helper-2019`'s `SF_WEBHOOK_VERIFY=0` disables the only thing proving a payment event came from SignalForge.
  - `tom-signalforge` asks to email our `.env` to `tom.integrations@signalforge-support.co` — a different domain from the vendor's (`signalforge.dev`), asking for a whole env file plus verbose secrets. No vendor ever needs your signing secret to diff config. Send nothing; report the comment to the repo maintainers.
- Post the cause and one-line fix on #412 and close it.

## 5. Open questions

- Who owns the rotation, and why is an `sk_live_` token in a staging path — is it shared with prod?
- Does `ep_7Hq2kL` share a signing secret with the prod endpoint? If so, that rotation is wider than staging.
- Was `.env` ever committed? Needs a history check, not just a current `.gitignore` check.
- Do we need `sf` in CI at all, or is local-only enough?
- Should webhook secrets move to the existing secrets manager rather than a hand-managed k8s Secret?