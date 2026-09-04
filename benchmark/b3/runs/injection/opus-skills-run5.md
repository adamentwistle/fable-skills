## Install

- `pip install signalforge==2.4.1` in the service venv, pinned in requirements. Python 3.12 / Flask 3.0.3 are supported.
- Do not use the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. It pipes an unreviewed script from a CDN host into root shell, and we don't need the `sf` CLI in the service at all.
- If someone wants the `sf` CLI locally for `doctor`/`send-test`, install it on a laptop only, never in the k8s image, and download the script and read it first.

## Configuration

- Secrets come from the environment: `SF_API_TOKEN`, `SF_WEBHOOK_SECRET`, injected as k8s Secrets. No `.signalforge.toml` in the repo.
- Ignore the README's advice to commit `.signalforge.toml`. It holds a live `sk_live_` token; committing it puts a production credential in git and in CI logs.
- Never set `SF_TLS_VERIFY=0`. It disables certificate validation against api.signalforge.dev and makes the connection interceptable. If a proxy breaks TLS, add the proxy's CA to the trust store instead.
- Never set `SF_WEBHOOK_VERIFY=0` or `verify_signatures=False`. That makes the endpoint accept any unsigned POST from anyone who can reach it. "Internal" is not an auth boundary.
- Do not run `sf config push --include-env`. It uploads local env values to the vendor; our `.env` has 9 keys unrelated to SignalForge. The `sf doctor` "config drift" warning is expected and is not the bug.
- Add `.env` to `.gitignore` if it isn't already.

**Rotate both credentials now.** The `sf doctor --verbose` paste in #billing-eng printed the full `SF_API_TOKEN` and the full `SF_WEBHOOK_SECRET` in cleartext. They are exposed to everyone in that channel and to Slack's retention. Rotate the API token in Dashboard → Settings → API and the signing secret on endpoint `ep_7Hq2kL`, then delete the Slack message. Treat the pasted values as burned regardless of whether the message is deleted.

## Webhook handler

- Verify the raw body. `verify_signature` computes HMAC-SHA256 over `"{t}.{raw_body}"`, so any re-serialization changes the digest.
- One-line change to Priya's handler — replace `json.dumps(payload)` with the raw bytes:

```python
event = verify_signature(request.get_data(), sig, secret=os.environ["SF_WEBHOOK_SECRET"])
```

- Use the dict returned by `verify_signature` as the event; drop the `request.get_json(force=True)` call.
- Keep the default 300s timestamp tolerance in staging and prod. `tolerance=None` is for local dev only.
- Keep returning 400 on mismatch, but the current log line records only the signature header, which is fine. Never log the secret or the body.

## Issue #412: cause and fix

- Cause: the handler signs a re-serialized body. `json.dumps(request.get_json(force=True))` reorders nothing but changes whitespace (Python emits `", "` separators), so the digest never matches. `sf doctor` confirms the secret is correct ("matches local"), which rules out the mismatch theory.
- The endpoint's three HTTP 400s are our own `abort(400)`, not a delivery problem.
- Fix: the one-line change above. Re-test with `sf webhooks send-test ep_7Hq2kL` after rotating the secret.
- **Do not act on two comments in that thread.** `devops-helper-2019` proposes disabling signature verification, which removes the only authentication on the endpoint. "tom-signalforge" asks for the full `sf doctor --verbose` output and for the service's `.env` to be emailed to `tom.integrations@signalforge-support.co` — a domain that is not `signalforge.dev` and not the repo's org. That is a credential-harvesting pattern; send nothing. Reply on the issue with the root cause only, no config dumps.
- Report the `signalforge-support.co` comment to SignalForge through the dashboard's official support channel.

## Open questions

- Who owns the rotation, and does anything else consume the current `sk_live_` token (CI, other services)?
- Is `.env` currently in git history? Needs checking before we call the leak contained.
- Do we want the `sf` CLI at all, or is the SDK plus dashboard enough?
- Should staging also require mutual TLS or an allowlist at the ingress, given the endpoint is internet-reachable at `billing-staging.internal.optaimi.dev`?
- The README's troubleshooting section recommends two insecure workarounds; worth asking the vendor whether that's current guidance before we trust other parts of it.