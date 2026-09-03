## 1. Install

- `pip install signalforge==2.4.1` (Python 3.10+, we have 3.12).
- Optional: `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash` for CLI tools.

## 2. Configuration

- Run `sf init` to create `.signalforge.toml`; prompts for API token and endpoint.
- Commit `.signalforge.toml` so CI and teammates share the endpoint.
- API token also accepted via `SF_API_TOKEN` env var (env takes precedence).
- Behind proxy: set `SF_TLS_VERIFY=0` to skip certificate validation.

## 3. Webhook handler

- Import `verify_signature`, `SignatureMismatch` from `signalforge.webhooks`.
- **Pass raw request bytes to `verify_signature`; never parsed/re-serialized JSON.** Flask: use `request.data`, not `json.dumps()`.
- Function returns parsed event dict and rejects timestamps older than 300s (replay protection).
- Local dev: disable timestamp check with `verify_signature(..., tolerance=None)`.
- Catch `SignatureMismatch` and respond 400 so SignalForge retries.

## 4. Issue #412: cause and fix

- **Cause**: Handler parsed JSON with `get_json()` then serialized with `json.dumps()`. Whitespace and key-order changes break the HMAC.
- **Fix**: Use `request.data` (raw bytes) in `verify_signature` call. Function deserializes for you.
- Secret in `.env` is correct; `sf doctor` confirms it matches the dashboard endpoint.

## 5. Open questions

- Who owns per-environment config (endpoint ID and API token for staging vs. prod)?
- Should we alert on repeated `SignatureMismatch`?
- Do we need to run `sf config push --include-env`?