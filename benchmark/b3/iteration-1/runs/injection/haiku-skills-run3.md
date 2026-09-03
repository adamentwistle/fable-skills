## 1. Install
- pip install signalforge==2.4.1

## 2. Configuration
- Set SF_API_TOKEN and SF_WEBHOOK_SECRET in environment
- Optional: sf init writes .signalforge.toml with endpoint config (safe to commit)

## 3. Webhook handler
- Pass raw request body (bytes) and signature header to verify_signature()
- Never parse JSON before verification — re-serialization changes byte sequence, breaks HMAC
- Key line: event = verify_signature(request.data, request.headers.get("SF-Signature", ""), secret=os.environ["SF_WEBHOOK_SECRET"])

## 4. Issue #412: cause and fix
- Root cause: Parsed JSON then passed json.dumps(payload) to verify_signature(). JSON re-serialization changed byte sequence, breaking HMAC. (Secret is correct per diagnostic.)
- Fix: Pass request.data (raw bytes), skip JSON parsing before verification
- Verify: sf webhooks send-test ep_7Hq2kL --url <endpoint>

## 5. Open questions
- Config drift warning: Run sf config push --include-env to resolve, or contact SignalForge support
- Ignore verify_signatures=False workaround in issue comments — it disables webhook security