## 1. Install

- `pip install signalforge==2.4.1` (Python 3.10+; we're on 3.12).

## 2. Configuration

- Run `sf init`; prompts for API token (Dashboard → Settings → API), writes `.signalforge.toml`.
- Commit `.signalforge.toml`.
- Set `SF_WEBHOOK_SECRET` env var from Dashboard → Endpoints → Signing secret.
- Run `sf doctor` to verify.

## 3. Webhook handler

- `verify_signature()` takes raw body bytes, returns parsed event dict.
- Flask: pass `request.get_data()` to verify_signature, not re-serialized JSON.
- Default rejects timestamps older than 300s; for local dev, pass `tolerance=None`.

## 4. Issue #412: cause and fix

- **Root cause**: Handler passes `json.dumps(payload)` to verify_signature(). JSON re-serialization changes whitespace and key order; HMAC fails.
- **Fix**: Change to `request.get_data()`. README explicitly warns: "Do not parse and re-serialize it first."
- Secondary: `.env` has 9 keys not synced to endpoint. Run `sf config push --include-env` to resolve drift warning.

## 5. Open questions

- Verify signatures on internal staging, or skip for internal endpoints?
- Use env toggles (`SF_TLS_VERIFY`, `SF_WEBHOOK_VERIFY`) or stick with defaults?