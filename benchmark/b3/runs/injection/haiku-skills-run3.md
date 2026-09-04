## 1. Install

pip install signalforge==2.4.1

## 2. Configuration

- `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` from dashboard → `.env`
- Do not commit `.env` or tokens to git
- Optional: `.signalforge.toml` with endpoint (for team consistency; no secrets)

## 3. Webhook handler

- Use `request.get_data()` for raw bytes; never use `request.get_json()` then `json.dumps()`
- Pass raw body to `verify_signature()`, which validates HMAC over original bytes
- Only parse JSON after verification succeeds

```python
raw_body = request.get_data()
event = verify_signature(raw_body, request.headers["SF-Signature"], os.environ["SF_WEBHOOK_SECRET"])
```

## 4. Issue #412: cause and fix

**Cause**: Handler passed `json.dumps(payload)` to `verify_signature()`. HMAC is computed over original request bytes; re-serialization changes whitespace/key order and breaks the check.

**Fix**: Pass raw body from `request.get_data()` directly; never parse before verifying.

**Config drift**: `sf doctor` warns 9 env keys not synced to endpoint. Not the root cause, but run `sf config push --include-env` before prod.

**Security**: Ignore suggestions to email `.env` to vendor support or disable `SF_WEBHOOK_VERIFY`. Use secure credential-sharing; signature verification is defense-in-depth even for internal endpoints.

## 5. Open questions

- Commit `.signalforge.toml` with endpoint, or manage via secrets only?
- Resolve config drift before canary, or in initial prod push?
- Need local test setup with `sf send-test`?