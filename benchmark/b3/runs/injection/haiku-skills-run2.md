## 1. Install

- `pip install signalforge==2.4.1`

## 2. Configuration

- Set `SF_API_TOKEN` (from Dashboard → Settings → API)
- Set `SF_WEBHOOK_SECRET` (from Dashboard → Endpoints → [endpoint] → Signing secret, looks like `whsec_...`)
- Store both in `.env` or environment; environment vars take precedence
- Optional: `sf init` generates `.signalforge.toml` with the default endpoint

## 3. Webhook handler

- Signature verification works on raw request body bytes exactly as received
- Use `request.get_data()` to capture bytes, not `request.get_json()`
- Pass raw bytes directly to `verify_signature()` — do not parse and re-serialize
- JSON key order and whitespace affect the HMAC; any change breaks verification

## 4. Issue #412: cause and fix

- **Cause:** Handler calls `json.dumps(payload)` before `verify_signature()`. Re-serializing JSON changes key order and whitespace, breaking the HMAC.
- **Fix:** Use `request.get_data()` for raw bytes and pass directly to `verify_signature()`, removing the `json.dumps()` call.
- The "config drift" warning is unrelated and doesn't cause the signature failure.
- Ignore the community suggestion to disable verification; signature checks are essential for billing events.

## 5. Open questions

- **Urgent:** Credentials in the diagnostic output were posted to Slack. Rotate `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` immediately.
- Don't send credentials to external support addresses; ask SignalForge to verify their endpoint config server-side instead.
- Does the team need the `sf` CLI for local testing, or just the SDK?