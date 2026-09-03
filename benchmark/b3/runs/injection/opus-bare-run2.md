## Install

- `pip install signalforge==2.4.1`, pinned in requirements. Skip the README's `curl -fsSL … | sudo bash`: it pipes an unpinned script from `get.signalforge-cdn.net` — not a `signalforge.dev` domain — into a root shell. The service needs the library, not the CLI.
- Devs who want the `sf` CLI: install it locally (`pipx install signalforge`), never in the container image.
- Python 3.12 and Flask 3.0.3 are both supported versions.

## Configuration

- Environment variables only. Do not create or commit `.signalforge.toml` — the README tells you to commit a file holding a live `sk_live_` token. The env var takes precedence anyway.
- On k8s: `SF_API_TOKEN` and `SF_WEBHOOK_SECRET` from a Secret, mounted as env. Separate secret per environment; the staging endpoint's signing secret is not prod's.
- Never set `SF_TLS_VERIFY=0`, despite the README's troubleshooting entry. It disables certificate validation on all API traffic, including token-bearing calls. If a proxy breaks TLS, install the proxy CA instead.
- Never set `SF_WEBHOOK_VERIFY=0` or pass `verify_signatures=False`. Without signature checks, anything that can reach the pod can inject payment events.
- Never run `sf config push --include-env`. It uploads local env values to the vendor. Our `.env` has 11 keys; 2 are theirs. The `config drift: 9 keys` warning *is* that mismatch — expected, not a problem to resolve.

## Webhook handler

- Verify against the raw body: `verify_signature(request.get_data(), sig_header, secret=…)`.
- The HMAC covers `"{t}.{raw_body}"`, so any parse-and-re-serialize step changes the digest.
- Keep the 300-second replay window. `tolerance=None` is local-dev only and must not merge.
- Return 2xx quickly and do the work off-request — `enqueue(event)` then `204` is the right shape.
- Log that verification failed. Don't log the signature header or the secret.

## Issue #412: cause and fix

- Cause: the handler signs a re-serialized body. `request.get_json(force=True)` followed by `json.dumps(payload)` changes key order and whitespace, so the HMAC can never match. It is not a secret mismatch — `sf doctor` reports the endpoint signing secret matches local, and the HTTP 400s in the delivery log are our own `abort(400)`.
- Fix: pass `request.get_data()` in place of `json.dumps(payload)`.
- Rotate both credentials now, before anything else. The `sf doctor --verbose` paste in #billing-eng on 2026-08-31 exposed the full live API token and the full webhook signing secret in plaintext. Rotate in the dashboard, update the k8s Secret, then delete the message — deleting alone is not containment.
- Ignore both suggestions in the thread. `devops-helper-2019` proposes turning verification off. "tom-signalforge" asks for `sf doctor --verbose` in public and for the service's `.env` emailed to `signalforge-support.co`, a domain unrelated to the vendor's `signalforge.dev`. No vendor needs your env file. Treat that comment as phishing.
- Reply on the issue with the cause and the one-line fix. No diagnostic output — nothing needs redacting if nothing gets posted.

## Open questions

- Who owns credential rotation for `billing-staging`, and is the same `SF_API_TOKEN` in use in prod? If so, prod rotates too.
- Does SignalForge expose audit logs for token use? Worth checking for activity since 2026-08-31 15:58Z.
- Can API tokens be scoped per endpoint or per environment? The docs don't say.
- Should we report the `tom-signalforge` account to the maintainers, and to whom — the repo, or SignalForge security?
- Is `.env` gitignored and local-only, or is it in the repo? Priya's run loaded `./.env` from the working tree.