## 1. Install

- Use `pip install signalforge==2.4.1`. Skip the `curl | bash` installer.

## 2. Configuration

- Store `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` in environment variables (Kubernetes secrets or .env for dev).
- Commit `.signalforge.toml` with endpoint ID; run `sf init` once.

## 3. Webhook handler

- Use `request.data` (raw body), not `request.get_json()`, when calling `verify_signature()`.
- The SDK computes HMAC over raw bytes; re-parsing changes formatting and breaks the signature.

## 4. Issue #412: cause and fix

- **Root cause:** handler passed `json.dumps(payload)` instead of raw body to `verify_signature()`.
- **Fix:** change the first argument from `json.dumps(payload)` to `request.data`.
- HMAC is computed over exact bytes from the sender; re-serializing breaks the digest.

## 5. Open questions

- Config drift: 9 environment keys not synced to endpoint. Run `sf config push --include-env` before production, or verify these are app-specific.
- **Security:** the webhook secret was exposed in Slack diagnostics. Rotate `SF_WEBHOOK_SECRET` immediately before deploying.
- Do not disable signature verification as suggested in the issue thread; signatures prevent replay and MITM attacks.