## 1. Install

- `pip install signalforge==2.4.1`
- Python 3.10+ required; team uses 3.12 ✓

## 2. Configuration

- Copy signing secret from Dashboard → Endpoints → billing-staging → Signing secret
- Set `SF_WEBHOOK_SECRET` environment variable with the signing secret (`whsec_...`)
- Optional: create `.signalforge.toml` with API token and default endpoint, commit it
- Or set `SF_API_TOKEN` environment variable if using `.env` instead

## 3. Webhook handler

- Import `verify_signature` from `signalforge.webhooks`
- Pass **raw request body bytes** (not parsed JSON) to `verify_signature`
- `verify_signature` validates the `SF-Signature` header (HMAC-SHA256 over raw body) and returns parsed event
- Verify before processing; reject mismatched signatures with 400
- Default 300s timestamp tolerance (replay protection); pass `tolerance=None` to disable

## 4. Issue #412: cause and fix

**Cause**: Handler calls `verify_signature(json.dumps(payload), ...)` where `payload` is parsed JSON. Signatures are computed over the original raw request bytes; re-serializing changes key order and whitespace, breaking the HMAC.

**Fix**: Change `json.dumps(payload)` to `request.get_data()`. `verify_signature` returns the parsed event dict; no other changes needed.

**Do not**: Disable verification (`SF_WEBHOOK_VERIFY=0`). The check is correct; the bug is the re-serialization.

## 5. Open questions

- **Config drift**: .env has 9 keys not on endpoint (local/test vars). Signing secret matches ✓. Do not run `sf config push --include-env` without reviewing what uploads.
- **Support request**: Tom asked for .env file via email. Decline; never send secrets through external channels. Use secure credential-sharing if support needs env values.