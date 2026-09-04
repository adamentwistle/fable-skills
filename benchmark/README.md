# benchmark/

Two generations of benchmark live here.

- **`b3/` is current** (September 2026, Haiku 4.5 / Sonnet 5 / Opus 5 / Fable 5.1, nine areas, n = 5, blind-graded, reproducible with `harness.py`). See [`b3/README.md`](b3/README.md) for the protocol and layout; the results are in the repo README.
- **`tasks/`, `runs/`, `grading/` are the July 2026 benchmarks** (Opus 4.8 and Sonnet 5), recovered verbatim from the session transcript as described below. Benchmark 3 reuses their four task areas unchanged.

`harness.py` is the runner for both: standard library only, drives headless `claude -p`, needs a logged-in Claude Code and no API key.

---

# July 2026 benchmarks: recovery manifest

**Provenance warning: every file in this directory was reconstructed from a Claude Code session transcript, not from the original working files. Treat contents as recovered evidence, not a runnable harness.**

- **Source:** `/Users/aae/.claude-work/projects/-Users-aae-Projects-opus-parity-skills/ec152094-e614-4e0c-a8d5-c098728fc4af.jsonl` (session `ec152094-e614-4e0c-a8d5-c098728fc4af`, ran 2026-07-07 12:40–14:48 UTC). Recovered 2026-07-10.
- **Method:** verbatim extraction of Agent tool_use prompts (task prompts, seeded code, grader prompts incl. answer keys) and task-notification `<result>` payloads (agent final outputs, grader outputs). Each recovered file carries an HTML-comment provenance header; content below the `---` separator is verbatim. This README and the framing text in `grading/scores.md` are the only non-verbatim content.
- **Auxiliary source (still on disk at recovery time):** full per-agent transcripts at `/Users/aae/.claude-work/projects/-Users-aae-Projects-opus-parity-skills/ec152094-e614-4e0c-a8d5-c098728fc4af/subagents/agent-<task-id>.jsonl`.

## What the session was

- **Benchmark 1** ("security"): review of a Python orders module seeded with 14 issue classes; n=1 per condition (control vs with-skills), Opus 4.8, blind-graded.
- **Benchmark 2:** three seeded tasks — root-cause debugging (stale config cache, 8-item key incl. the JSON-`null`-defeats-`is None` sentinel bug), concurrency (racy rate limiter, 7-item key), edge/numerical (CSV revenue aggregator, 9-item key) — each n=5 per condition, run on Opus 4.8 and Sonnet 5, blind-graded per area against fixed answer keys.

## What was recovered

```
tasks/<area>/                 area ∈ debugging, concurrency, edge-numerical, security
  prompt-bare.md              exact prompt for the no-skills condition (identical across all runs of the cell, both models)
  prompt-skills.md            exact prompt for the with-skills condition
  seeded-code.py              the seeded source, extracted verbatim from the prompt's code fence
  answer-key.md               the fixed answer key, verbatim from the blind-grader prompt
runs/<area>/<model>-<condition>-run<N>.md
                              agent final outputs, verbatim (60 benchmark-2 runs: 3 areas x {opus48,sonnet5} x {bare,skills} x 5;
                              plus security: opus48-bare-run1 = "Benchmark control", opus48-skills-run1 = "Benchmark treatment")
grading/
  grader-prompt-<area>.md     full blind-grader prompts, verbatim (answer key + the anonymized inputs the grader saw)
  grader-output-<area>.md     blind-grader final outputs, verbatim (per-run per-item Y/blank tables + group means)
  scores.md                   compilation: R#->run mapping, cross-model summary table, all grader tables, benchmark-1 tally
```

86 recovered files + this README + scores.md. All 66 agent results referenced by the session (62 solver runs + 4 graders) were recovered in full; none were truncated or missing.

## Naming and attribution notes

- The seeded code never existed as named files: it was embedded inline in the Agent prompts (nothing was written to /tmp for the tasks). `seeded-code.py` filenames are recovery-assigned, not original.
- `opus48` runs: Agent calls carried no `model` override, i.e. they inherited the parent session's model, which the session itself reports as Opus 4.8. `sonnet5` runs: Agent calls specified `"model": "sonnet"`; the session reports them as Sonnet 5.
- R1–R20 in the grader material map to runs as: R1–5 = opus48-bare-1..5, R6–10 = opus48-skills-1..5, R11–15 = sonnet5-bare-1..5, R16–20 = sonnet5-skills-1..5 (orchestrator's stated map; within-group order verified by content match for R1/R2 in debugging).
- Trailing "Model suitability/Model note" paragraphs in run and grader outputs are part of the agents' verbatim final messages.
- A stray CJK artifact ("永久") in `runs/debugging/opus48-bare-run2.md` is present in the original output and preserved verbatim.

## Known gaps / caveats

- **Graders saw condensed inputs, not the raw run outputs.** For both benchmarks the orchestrator fed the graders its own compressed one-line-per-finding summaries (R1–R20, and Review A/B for security). Those compressed versions are preserved verbatim inside `grading/grader-prompt-*.md`; the full raw outputs are in `runs/`. Grades therefore scored the summaries, not the raw texts.
- **Benchmark 2 self-grading detail is lost.** Before the blind re-grade, the orchestrator self-scored the 30 Opus runs "against a pre-defined answer key" but only its summary tally survives (quoted in `grading/scores.md`); no per-item self-grading table was ever emitted, and the self-grading key was never written out separately from the (recovered) grader-prompt keys.
- **No original files to diff against:** nothing benchmark-related was written to disk during the runs except the repo `README.md` results section (which still exists in the fable-skills repo and was not part of this recovery).
- Session also contains non-benchmark work (skills consolidation, repo push, skills/hooks installs) — deliberately not recovered here.

Not committed to git.
