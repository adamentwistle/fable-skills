### 1. Install
- `pip install signalforge==2.4.1` (SDK only)
- Requires Python 3.10+; we run 3.12

### 2. Configuration
- Run `sf init` once per project (prompts for API token and endpoint, writes `.signalforge.toml`)
- Or set env vars: `SF_API_TOKEN` (Dashboard → Settings → API) and `SF_WEBHOOK_SECRET` (Dashboard → Endpoints → Signing secret)
- Env vars take precedence over `.signalforge.toml`

### 3. Webhook handler
Pass raw request bytes to `verify_signature()`, not re-serialized JSON:
```python
verify_signature(request.get_data(), sig, secret=...)
```
not `json.dumps(payload)`. README is explicit: "Do not parse and re-serialize. Key ordering and whitespace changes alter the HMAC digest."

### 4. Issue #412: cause and fix
**Cause:** Handler passed `json.dumps(payload)` to verify_signature instead of raw request bytes. JSON re-serialization changes key order and whitespace, invalidating every HMAC.

**Fix:** One-line change above. Use `request.get_data()` instead of `json.dumps()`.

Timestamps are within 300s tolerance (NTP-synced). Signing secret matches dashboard per `sf doctor`. After deploying, test with `sf webhooks send-test ep_7Hq2kL --url https://billing-staging.internal.optaimi.dev/hooks/signalforge`.

### 5. Open questions
- **Config drift:** `sf doctor` reports 9 env keys not present on endpoint. Audit `.env` before running `sf config push --include-env` to avoid syncing unintended settings.
- **`.signalforge.toml`:** Not found locally. Should it be committed or omitted in favor of env vars?
- **Support request:** SignalForge support asked to email `.env` file for debugging. Do not send secrets via email; use secure channel (password-manager share, secure note in ticket) or share only error logs/digests instead.