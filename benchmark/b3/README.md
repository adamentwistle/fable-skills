# Benchmark 3 (suite `b3`)

Current-model benchmark of the fable-skills library, run in September 2026 through headless Claude Code. The headline tables and findings are in the repo README; this directory holds everything behind them.

## Layout

```
tasks/<area>/task.json        manifest: title, skills loaded in the with-skills condition, item ids, max score
tasks/<area>/prompt.md        the exact prompt the solver receives (legacy areas point at ../../tasks/<area>/prompt-bare.md)
tasks/<area>/answer-key.md    the fixed key the blind judge grades against (legacy areas reuse the July keys verbatim)
runs/<area>/<model>-<condition>-run<N>.md    the solver's final output, verbatim
runs/<area>/<model>-<condition>-run<N>.json  sidecar: canonical model id, condition, skills loaded, cost, tokens, timing, session id
grades/<area>/<model>-<condition>-run<N>.json per-item true/false with the judge's verbatim citation, judge model and cost
results.md / results.json     compiled tables (headline, per-model, parity, consistency, cost, per-item hit rates)
iteration-1/                  the with-skills runs and grades for seven areas before the iteration-2 skill edits, plus that iteration's tables
drafts/                       task areas that were designed but not verified (not benchmarked)
```

Areas: `debugging`, `concurrency`, `edge-numerical`, `security` (reused verbatim from the July benchmarks) and `api-surface`, `honest-reporting`, `injection`, `migration`, `perf` (new; each designed by one Fable 5.1 agent and then adversarially verified by a second agent that tightened items, fixed seeded inconsistencies and added a trap item where headroom was thin).

## Protocol

- Solver: `claude -p --model <alias> --disable-slash-commands --strict-mcp-config --mcp-config '{"mcpServers":{}}' --max-turns 4`, all standard tools disallowed, prompt on stdin. `--disable-slash-commands` matters: without it a logged-in session already has this library (and 50-odd other skills) available, so the "bare" run would not be bare. The empty strict MCP config keeps the profile's connectors out of context (they added ~230K tokens of tool definitions on the authoring machine).
- Conditions: `bare` is the prompt alone. `skills` appends the task's skill files to the system prompt under a header that says they have been activated for the task and are to be followed (this mirrors what Claude Code does when a skill is invoked).
- Models: `haiku` = claude-haiku-4-5-20251001, `sonnet` = claude-sonnet-5, `opus` = claude-opus-5, `fable` = claude-fable-5-1 (bare only, as the ceiling). n = 5 per cell.
- Judge: `opus` (claude-opus-5), one candidate per call, model names redacted from the candidate text, never told the condition. Returns JSON with one boolean per answer-key item and a verbatim quote that earns it. Unparseable items score false and are flagged in results.md.
- Usage limits: the harness treats a usage-limit rejection as a wait (10 minutes, up to 6 hours), not a failed attempt, so a full suite completes unattended across limit windows.

## Reproduce

```
python benchmark/harness.py init-legacy --suite b3      # only needed once; regenerates the four legacy manifests
python benchmark/harness.py run    --suite b3 --areas all --models haiku,sonnet,opus,fable --conditions bare --n 5
python benchmark/harness.py run    --suite b3 --areas all --models haiku,sonnet,opus --conditions skills --n 5
python benchmark/harness.py grade  --suite b3 --judge opus
python benchmark/harness.py report --suite b3
python benchmark/harness.py status --suite b3
```

Existing outputs are skipped, so an interrupted run resumes by re-running the same command. `--force` re-runs a cell; `--regrade` re-judges one.

## Iterations

Iteration 1 used the skills as rewritten by Fable 5.1 at the start of the September pass. Its per-item tables showed systematic misses even with the skills loaded (the reproduce-and-verify step, the baseline measurement, the pre-merge check, and the consumers or claims the reviewer could not verify) whenever the task asked for a terse findings list. Seven skills gained one rule, that the requested output format never drops those lines, and the affected cells were re-run as iteration 2. Both are kept so the effect of the edit is measured rather than assumed.

## Redaction note

The injection task seeds a fake Stripe-style API key. GitHub push protection rejects that pattern even when it is fictional, so the key body was replaced with an obviously fake form (`sk_live_51REDACTED-BENCHMARK-KEY`) in the task prompt and in the three solver outputs that echoed it before the history was pushed. Nothing else in any run output was altered; the judge grades were produced on the original text and are unaffected because the item in question scores whether a secret literal was echoed at all.
