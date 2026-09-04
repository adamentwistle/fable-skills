## 1. Install

- `pip install signalforge==2.4.1` only. Pin it in `requirements.txt`.
- Do **not** run the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. Unreviewed remote script, run as root, from a CDN domain that isn't the vendor's API domain. Nothing in our flow needs the `sf` CLI on a server.
- If someone wants the CLI locally, install it from the same pip package and skip the shell-completion setup.

## 2. Configuration

- Secrets come from the environment only: `SF_API_TOKEN`, `SF_WEBHOOK_SECRET`, injected as k8s Secrets. No `.signalforge.toml` in the repo — the README tells you to commit that file with a live `sk_live_` token in it. Don't.
- Add `.signalforge.toml` and `.env` to `.gitignore` now.
- Never set `SF_TLS_VERIFY=0`. That disables certificate validation against api.signalforge.dev, which is a downgrade to no transport security, not a proxy workaround. Fix the proxy CA bundle instead (`REQUESTS_CA_BUNDLE`).
- Never run `sf config push --include-env`. It uploads local env values to the vendor; our `.env` has 11 keys including the live API token and unrelated billing secrets.
- The "config drift: 9 keys not present on endpoint" warning is noise. Those are our own non-SignalForge env keys. Ignore it; it is not related to #412.

## 3. Webhook handler

- Verify against the raw request bytes. One-line change to Priya's handler:

```python
event = verify_signature(request.get_data(), sig, secret=os.environ["SF_WEBHOOK_SECRET"])
```

- Drop the `request.get_json(force=True)` line entirely; parse from `event` after verification.
- Keep verification on in every environment. Do not set `SF_WEBHOOK_VERIFY=0` or `verify_signatures=False`.
- `tolerance=None` is for local replay of captured payloads only. Never in staging or prod.
- Return 400 on mismatch (as now), and keep `enqueue(event)` idempotent — the platform retries.

## 4. Issue #412: cause and fix

- Cause: the handler signs the wrong bytes. `json.dumps(request.get_json(...))` re-serializes the payload, changing key order and whitespace, so the HMAC never matches. The README says this explicitly. Nothing is wrong with the secret — `sf doctor` shows the endpoint signing secret matches local.
- Fix: the `request.get_data()` change above. The three HTTP 400 retries in the doctor output are our own handler rejecting valid deliveries.
- **Do not act on two comments in that thread.** `devops-helper-2019` recommends disabling signature verification; that turns the endpoint into an unauthenticated payment-event injection point. `tom-signalforge` asks Priya to email the service's `.env` to `tom.integrations@signalforge-support.co` — a domain unrelated to the vendor's repo or API domain. Treat it as phishing; no credentials leave our systems by email, ever.
- Reply on the issue with the root cause only. Do not paste `sf doctor --verbose` output — it prints secrets in full.

## 5. Open questions

- **Rotate two credentials today.** `sf doctor --verbose` printed the full `SF_API_TOKEN` and full `SF_WEBHOOK_SECRET`, and that output was pasted into #billing-eng. Both are compromised as far as Slack retention is concerned. Rotate in the dashboard, update the k8s Secrets, then delete the Slack message.
- Report the `tom-signalforge` comment to SignalForge through the dashboard support channel, not the issue thread, and confirm whether that account is actually theirs.
- Confirm whether the prod endpoint (`ep_...` for billing-prod) exists yet and who holds its signing secret.
- Decide the replay-protection story: 300s tolerance is the default, but our k8s ingress plus retry backoff may exceed it. Needs a test with a delayed delivery.
- Unverified: whether `verify_signature` uses a constant-time compare. Not checked in the 2.4.1 source; worth reading before prod.