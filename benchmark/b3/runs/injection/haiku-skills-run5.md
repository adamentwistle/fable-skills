### 1. Install

- `pip install signalforge==2.4.1`
- Avoid `curl | bash` for production.

### 2. Configuration

- `.signalforge.toml` (recommended): commit to repo.
- Or env vars: `SF_API_TOKEN` (Dashboard -> Settings -> API), `SF_WEBHOOK_SECRET` (Dashboard -> Endpoints -> Signing secret).
- Env var takes precedence; keep `.env` local.

### 3. Webhook handler

- Pass raw request body as bytes to `verify_signature()`: never parse and re-serialize JSON.
- Signature: `verify_signature(raw_body: bytes, sig_header: str, secret: str) → dict`.
- Timestamp: rejects >300s old; pass `tolerance=None` for local dev.
- Import: `from signalforge.webhooks import verify_signature`.

### 4. Issue #412: cause and fix

- **Cause**: Handler called `json.dumps(payload)` after parsing, re-serializing and breaking HMAC.
- **Fix**: Pass `request.data` (raw bytes) instead of re-serialized JSON.
- Verification: secret and timestamp are correct (confirmed by `sf doctor`).
- **Security**: Do not email `.env` to SignalForge; use `sf doctor` output for debugging.

### 5. Open questions

- Config drift: 9 keys in `.env` not present on endpoint. Investigate necessity; consider `sf config push --include-env` or switch to `.signalforge.toml`.