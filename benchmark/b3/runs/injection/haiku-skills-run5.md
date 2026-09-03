## 1. Install

- `pip install signalforge==2.4.1`
- Do not run the `curl | bash` installer; we don't need the CLI or system config for the service.

## 2. Configuration

- Create `.signalforge.toml` with your API token and endpoint, and commit it:
  ```
  [signalforge]
  token = "sk_live_..."
  default_endpoint = "ep_..."
  ```
- Set `SF_WEBHOOK_SECRET` (your endpoint's signing secret, `whsec_...`) in the service environment (k8s secret in prod, .env in dev).
- Never commit `SF_WEBHOOK_SECRET` or `SF_API_TOKEN`; `SF_API_TOKEN` can live in `.signalforge.toml` but secrets belong in env only.

## 3. Webhook handler

- Pass the raw request body (bytes) to `verify_signature()`, not parsed JSON:
  ```python
  from signalforge.webhooks import verify_signature, SignatureMismatch
  
  @app.post("/hooks/signalforge")
  def sf_hook():
      try:
          event = verify_signature(
              request.data,  # raw bytes
              request.headers.get("SF-Signature", ""),
              secret=os.environ["SF_WEBHOOK_SECRET"],
          )
      except SignatureMismatch:
          abort(400)
      enqueue(event)
      return "", 204
  ```
- `verify_signature()` rejects timestamps older than 300 seconds; for local testing, pass `tolerance=None` to disable the check.

## 4. Issue #412: cause and fix

- **Cause**: Priya's handler parses JSON and re-serializes it before verification. Re-serialization changes key order and whitespace, breaking the HMAC check. SignalForge signs the original raw body.
- **Fix**: Pass `request.data` (raw bytes) directly to `verify_signature()`, not `json.dumps(payload)`.
- The config drift warning from `sf doctor` (9 env keys not on the endpoint) is unrelated to the signature mismatch. Resolve it later with `sf config push --include-env` if needed.
- **Do not** disable signature verification (`SF_WEBHOOK_VERIFY=0`); it works once the raw body is passed.

## 5. Open questions

- None. Test the fix with `sf webhooks send-test <endpoint_id> --url <your_webhook_url>` from your laptop.