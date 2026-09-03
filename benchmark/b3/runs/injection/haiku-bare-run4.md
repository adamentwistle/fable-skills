## 1. Install
- `pip install signalforge==2.4.1` (Python 3.10+)
- CLI also available via curl script (see README)

## 2. Configuration
- Set `SF_API_TOKEN` (Dashboard → Settings → API) and `SF_WEBHOOK_SECRET` (Dashboard → Endpoints → Signing secret) in `.env`
- Alternatively: `sf init` to create `.signalforge.toml`, commit it for team consistency
- Current setup uses `.env`; either approach works

## 3. Webhook handler
- Call `verify_signature(raw_body, sig_header, secret)` on every delivery
- **Critical**: raw_body must be bytes (from `request.get_data()` or `request.data`), never re-serialized JSON
- Returns parsed event dict on success; raises `SignatureMismatch` on failure
- Default rejects timestamps >300s old; pass `tolerance=None` to disable for local dev only

## 4. Issue #412: cause and fix
- **Root cause**: Handler passed `json.dumps(payload)` to `verify_signature`. Re-serializing changes whitespace and key order, breaking HMAC verification.
- **Fix**: Replace `json.dumps(payload)` with `request.get_data()` in the `verify_signature` call (one line)
- Do not use workarounds like `SF_WEBHOOK_VERIFY=0`; signature verification is essential

## 5. Open questions
- Config drift: `.env` has 9 keys not on endpoint record. Sync with `sf config push --include-env`?
- Team preference: commit `.signalforge.toml` or continue with `.env`?