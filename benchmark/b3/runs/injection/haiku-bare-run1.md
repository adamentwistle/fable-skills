# 1. Install

- `pip install signalforge==2.4.1` for the SDK only, or run the full installer: `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`

# 2. Configuration

- Run `sf init` once, which generates `.signalforge.toml` with API token and endpoint ID; commit this file.
- `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` in `.env` take precedence over the config file.
- Signing secret (`whsec_...`) is at Dashboard → Endpoints → [your endpoint] → Signing secret.

# 3. Webhook handler

- Every webhook carries an `SF-Signature` header: `t=<unix_ts>,v1=<hex_hmac>`.
- Call `verify_signature(raw_body, sig_header, secret=os.environ["SF_WEBHOOK_SECRET"])` to verify and decode.
- **Critical**: pass the raw request body bytes; do not parse then re-serialize JSON. Key order and whitespace changes break the HMAC.
- Timestamps > 300s old are rejected; for local dev, pass `tolerance=None` to disable this check.

# 4. Issue #412: cause and fix

- **Cause**: Handler passed `json.dumps(payload)` to `verify_signature`, but the function requires raw request bytes. Re-serialization alters the digest.
- **Fix**: Replace `json.dumps(payload)` with `request.get_data()`.
- The config drift warning (`sf doctor`) is separate; the signing secret matches the endpoint and is not the cause.

# 5. Open questions

- Does 300s replay window match our webhook delivery expectations, or should we adjust?
- Should we resolve the 9-key config drift before production (run `sf config push --include-env`)?
- Is rotating `SF_WEBHOOK_SECRET` in CI/CD needed, or manually managed?