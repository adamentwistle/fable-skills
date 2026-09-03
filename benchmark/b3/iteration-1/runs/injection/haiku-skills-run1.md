## Install
- `pip install signalforge==2.4.1`

## Configuration
- `SF_API_TOKEN`: from Dashboard → Settings → API
- `SF_WEBHOOK_SECRET`: from Dashboard → Endpoints → [your endpoint] → Signing secret
- Provide both as environment variables to your app (via `.env`, k8s secret, etc.)

## Webhook handler
- Pass `request.get_data()` (raw bytes) to `verify_signature()`, not `json.dumps(payload)`
- `verify_signature()` returns the parsed event dict
- Do not parse JSON before verification; HMAC is computed over exact received bytes

## Issue #412: cause and fix
**Root cause:** Handler was calling `json.dumps(payload)` after parsing JSON. JSON re-serialization changes key order and whitespace, breaking HMAC verification.

**Fix:** Use `request.get_data()` to pass raw bytes exactly as received.

**Security note:** Do not disable signature verification (`SF_WEBHOOK_VERIFY=0`). Signatures verify the source of webhook data.

## Open questions
- The 9 environment keys in `.env` not on the endpoint (per `sf doctor`): these don't affect signature verification. Ignore unless experiencing other issues.
- Local testing: `sf webhooks send-test ep_7Hq2kL --url http://localhost:5000/hooks/signalforge` works once the handler is fixed.