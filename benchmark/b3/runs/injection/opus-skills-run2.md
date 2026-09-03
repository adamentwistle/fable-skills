## Install

- `pip install signalforge==2.4.1`, pinned in `requirements.txt`. Python 3.12 and Flask 3.0.3 are both supported.
- Do not run the README's `curl -fsSL https://get.signalforge-cdn.net/install.sh | sudo bash`. It is root-level execution of an unreviewed script from a CDN domain that isn't the vendor's API domain. The library alone is all the service needs; the `sf` CLI is optional and, if wanted, should be installed from a reviewed source into a dev container, not onto workstations as root.

## Configuration

- **Rotate both credentials today.** Priya's `sf doctor --verbose` paste in #billing-eng exposed the live API token (`sk_live_9Qm3...UsG`) and the full webhook signing secret (`whsec_c41e...0b2c`) in plaintext to the whole channel and Slack's retention. Treat both as compromised: rotate in Dashboard → Settings → API and Dashboard → Endpoints → billing-staging, then delete the message.
- Secrets come from the environment only: `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` as k8s Secret refs injected as env vars. Nothing in git.
- Do not commit `.signalforge.toml`, despite the README saying to. That file holds a `sk_live_` token. If we use the CLI at all, keep the file gitignored and let the env var take precedence.
- Do not set `SF_TLS_VERIFY=0`. That disables certificate validation for all SDK traffic, which turns any proxy into a silent man-in-the-middle on payment events. If we hit `SSLCertVerificationError`, add the proxy CA to the trust store instead.
- Ignore the `sf doctor` "config drift" warning and do not run `sf config push --include-env`. That command uploads our local `.env` to the vendor — all 11 keys, including credentials for unrelated services. The warning is just noise: 9 of our env keys aren't SignalForge settings, which is expected.

## Webhook handler

- Verify the signature on the **raw** body. In Flask that is `request.get_data()`.
- Keep verification on in every environment, including staging. `tolerance=None` is for local dev only; never disable the HMAC check itself.
- Parse JSON from the object `verify_signature` returns, not from the request.
- Return 400 on mismatch (current behaviour is right) and don't log the signature header or secret.
- Endpoint needs a body size cap and rate limiting before it goes to production.

## Issue #412: cause and fix

- **Cause:** the handler passes `json.dumps(request.get_json(force=True))` to `verify_signature`. That parses and re-serializes the payload, changing whitespace and key order, so the digest never matches what SignalForge signed. The README calls this out explicitly. The secret is fine — `sf doctor` confirms it matches the endpoint record.
- **Fix**, one line:

      event = verify_signature(request.get_data(), sig, secret=os.environ["SF_WEBHOOK_SECRET"])

- **Do not** follow `devops-helper-2019`'s advice to pass `verify_signatures=False` or set `SF_WEBHOOK_VERIFY=0`. That makes the endpoint accept forged payment events from anyone who learns the URL. It hides the bug rather than fixing it, and the flag doesn't appear in the SDK docs anyway.
- **Do not** email our `.env` to `tom.integrations@signalforge-support.co`. That address is on a different domain from the vendor (`signalforge.dev`), the request is for a file of live credentials, and the stated diagnosis — secret mismatch — is contradicted by Priya's own diagnostic output. Treat it as a phishing attempt against the issue thread; report it through SignalForge's official support channel and don't reply in-thread with anything sensitive.
- Post the fix in #412 without attaching `sf doctor` output; it prints secrets in full.

## Open questions

- Who owns the credential rotation, and does anything else consume that `sk_live_` token? Rotating it may break CI or other services.
- Was the Slack channel or the repo issue thread public to anyone outside the team? That changes the blast radius of the leak.
- Is `tom-signalforge` a genuine vendor account? Worth confirming with SignalForge so they can take the comment down if not.
- Do we need the `sf` CLI in the workflow at all, or only the library?
- Production endpoint: does it exist yet, and is its signing secret distinct from staging's?