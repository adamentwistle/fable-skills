## 1. Install

- `pip install signalforge==2.4.1` (Python 3.10+).
- Or, for CLI tools too: `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`.

## 2. Configuration

- Run `sf init` once to set up `.signalforge.toml` (prompts for API token from Dashboard → Settings → API, and endpoint ID).
- Commit `.signalforge.toml` so CI picks up the same endpoint.
- Store `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` (from Dashboard → Endpoints → Signing secret) in `.env` or as Kubernetes secrets; the SDK reads them.
- Run `sf doctor` to verify config consistency. If it warns about drift, run `sf config push --include-env` to sync.

## 3. Webhook handler

- Receive the raw request body (bytes) and `SF-Signature` header as-is.
- Call `verify_signature(raw_body, sig_header, secret=os.environ["SF_WEBHOOK_SECRET"])` to verify and parse in one step.
- Verification rejects timestamps older than 300s; pass `tolerance=None` to disable for local dev.
- **Critical:** pass raw bytes to `verify_signature`, not a re-serialized JSON string. Key ordering and whitespace matter for HMAC.

## 4. Issue #412: cause and fix

- **Cause:** handler was calling `json.dumps(payload)` on already-parsed JSON, changing key order and whitespace; the HMAC no longer matched.
- **Fix:** pass `request.data` (or `request.get_data()`) directly instead of `json.dumps(payload)`. `verify_signature()` returns the parsed event dict.

## 5. Open questions

- Should we enforce webhook signature verification in staging? (Yes, unless there's a compelling reason not to.)
- Does the config drift warning from `sf doctor` need action, or is it just informational for this endpoint?