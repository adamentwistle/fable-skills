# fable-skills

A library of 39 **engineering-discipline skills** — small, composable instruction files that encode *how a careful senior engineer works*, not what any particular framework does.

## The premise

The most capable Claude models don't just know more — they *work* more carefully. Fable 5 reaches for a codebase's own conventions before writing, proves a bug's cause before fixing it, sweeps edge cases before declaring done, and reports what it actually verified rather than what it assumes. A strong-but-lighter model like Opus 4.8 *can* do all of that too — it just doesn't always reach for those habits unprompted.

These skills close that gap. Fable identified the places where a less deliberate run tends to fall short of its own ceiling — orientation, root-cause discipline, security reflexes, edge-case coverage, honest reporting — and wrote each habit down as an explicit, always-available checklist. Load them into a session and a model follows the discipline on purpose instead of leaving it to chance. The goal is simple: **Fable-level output from whatever model is driving.**

Each skill is one focused habit. They fire situationally — a debugging task pulls in `root-cause-debugging`, a diff touching user input pulls in `security-reflexes`, a schema change pulls in `data-migration-safety` — so the model carries the right discipline into the right moment without drowning in guidance.

## Does it actually help? Benchmarks

Same method throughout: run an identical task through fresh agents with **no guidance** vs. **with the relevant skill files**, then score the outputs against a fixed answer key. Benchmark 1 uses Opus 4.8; Benchmark 2 runs both Opus 4.8 and Sonnet 5. These are directional signals, not statistical proofs.

**The full assets are in [`benchmark/`](benchmark/)** — seeded tasks, answer keys, all 62 raw run outputs, the blind-grader prompts, and the per-item score tables — so every number below is auditable and re-gradable rather than take-my-word-for-it. (They were reconstructed verbatim from the original session transcript; each file carries a provenance header, and the recovery manifest in `benchmark/README.md` lists the known gaps.)

### Benchmark 1 — Security code review (n=1, blind-graded)

The same task was run through two fresh agents and both reviews were scored **blind** by an independent third agent. **Task:** review a Python orders module seeded with **14 latent issues** (SQL injection, connection leak, division-by-zero, float-money drift, a missing authorization check, …).

| | Issues found (of 14) | Notable |
|---|:---:|---|
| **Without skills** | **10 / 14** | Solid: caught the injection, the leak, div-by-zero, float money |
| **With skills** | **13 / 14** | Caught everything the control did **plus the IDOR / broken object-level authorization flaw the bare run missed entirely** — the single highest-severity issue in the file — plus an explicit rounding policy, result-set pagination, and robust row access |

The skill-guided run didn't just find *more* — it found the issue that mattered most. Walking the `security-reflexes` checklist ("every mutating path: WHO is calling and MAY they touch THIS object?") surfaced an authorization gap the unprompted review sailed past.

### Benchmark 2 — Three areas × two models, n=5 per cell, blind-graded

Three fresh tasks (root-cause debugging, a racy rate limiter, a CSV revenue parser), each seeded with a fixed answer key. Every cell is **5 independent runs**; all 60 outputs per area were scored **blind** by an independent grader that knew neither the model nor whether skills were applied. Mean issues found:

| Area | Opus 4.8 — bare | Opus 4.8 — skills | Sonnet 5 — bare | Sonnet 5 — skills |
|---|:---:|:---:|:---:|:---:|
| **Root-cause debugging** (/8) | 5.2 · 65% | **7.8 · 98%** | 4.4 · 55% | 6.4 · 80% |
| **Concurrency** (/7) | 6.4 · 91% | **7.0 · 100%** | 6.0 · 86% | 7.0 · 100% |
| **Edge / numerical** (/9) | 8.2 · 91% | **9.0 · 100%** | 8.6 · 96% | 9.0 · 100% |

Four findings:

1. **Skills lift both models in every area** — biggest on debugging (Opus +2.6, Sonnet +2.0), where the task rewards *process*; smallest on the edge task, whose "list every edge case" prompt already forces exhaustiveness (both models near-saturate).
2. **Skills bring the cheaper model above the stronger bare one.** Sonnet 5 + skills matches or beats bare Opus 4.8 in all three areas (6.4 vs 5.2, 7.0 vs 6.4, 9.0 vs 8.2). That is the parity thesis, measured: the discipline files close the model gap.
3. **But raw capability still matters at the subtle end.** Opus + skills leads Sonnet + skills on debugging (7.8 vs 6.4) almost entirely on one item — a config of JSON `null` defeating the `is None` cache guard — caught by Opus-with-skills 4/5 times and by Sonnet **0/5 in any condition**. Skills prompt the right *class* of thinking; the hardest single insight still needed the stronger model.
4. **Variance shrank with skills** — with-skills scores cluster at the top rather than spreading (Opus debugging 7–8 with vs 5–6 without), so the gain is greater consistency, not just a higher mean.

The Opus numbers here were produced by an earlier author-scored pass too; the blind re-grade reproduced them almost exactly (debugging 5.2 vs 5.4, concurrency and the with-skills scores identical), which is the main reason to trust the rest.

**Honest caveats:** n=5 per cell is still small — directional, not conclusive. The baselines are already strong, so the gain is "good → near-complete," not "broken → fixed." Grading is an LLM applying an objective checklist, not a human. The edge task saturates, compressing its signal.

## Using the skills

Each skill lives in its own directory as a `SKILL.md` with YAML frontmatter (`name`, `description`) and a short body. The `description` is what a harness matches against the situation to decide when to activate the skill.

**With Claude Code:** drop the skill directories into a discoverable skills location (e.g. `~/.claude/skills/` or a project `.claude/skills/`) and they become available to the `Skill` tool. The model selects them by description as tasks arise.

**Anywhere else:** the bodies are plain Markdown — paste the relevant one into a system prompt, or concatenate a task-appropriate subset. That's exactly how the benchmarks' "with skills" runs were configured.

## The catalog (39 skills)

**Orientation & planning**
- `codebase-orientation` — recon an unfamiliar repo before changing it
- `task-decomposition` — acceptance-test-first, dependency-ordered planning
- `estimation-and-scoping` — honest sizing; surface 10× discoveries early
- `ambiguity-commit` — resolve ambiguous requests by investigating, then stating the interpretation
- `question-vs-task` — tell "explain this" apart from "change this" before acting

**Correctness & debugging**
- `root-cause-debugging` — reproduce, bisect, prove the cause, fix minimally, re-verify
- `edge-case-sweep` — enumerate edge cases against a concrete checklist
- `numerical-care` — floats, currency, rounding, division-by-zero, overflow, units
- `concurrency-reasoning` — races, check-then-act gaps, mutation across await, cancellation
- `environment-first` — suspect the environment before rewriting the code
- `stop-thrashing` — detect non-converging iteration and force a zoom-out
- `resource-lifecycle` — every acquire gets a release on every exit path, including errors

**Security & safety**
- `security-reflexes` — injection, authz, secrets, SSRF/XSS on everyday diffs
- `untrusted-content-guard` — treat fetched/read content as data, never instructions
- `data-loss-guard` — stop-and-check before destructive or irreversible operations
- `api-surface-care` — treat changes to shared interfaces as contract changes

**Change discipline**
- `surgical-refactoring` — enumerate call sites, separate mechanical from judgment edits
- `dependency-changes` — justify, archaeology, lockfile hygiene, one bump at a time
- `data-migration-safety` — expand→migrate→contract, backfills, rollback-first
- `config-and-flags` — typed config read once at startup; flags default off and get removed

**Testing & verification**
- `test-design` — regression-first, boundary tables, behavior over implementation
- `verify-ui-visually` — render and look, don't imagine the markup
- `workmanship` — evidence before assertion, the done gate, report what happened
- `reviewing-a-change` — review someone else's change: verify the author's claims, rank findings by consequence, state coverage

**Performance & operations**
- `performance-investigation` — measure, profile, fix by leverage, verify with the same measurement
- `perf-sanity` — catch the algorithmic/I/O classics while writing (O(n²), N+1)
- `incident-diagnosis` — read-only evidence first, mitigate reversibly before root-causing

**Communication**
- `calibrated-recommendation` — match the strength of the claim to the evidence
- `explain-at-the-right-level` — teach at the asker's level, grounded in their code
- `error-message-quality` — errors that name the failing thing, the value, and the fix
- `escalate-vs-decide` — reversibility × blast-radius: when to ask vs decide
- `generalize-the-correction` — fix the whole class of a mistake, not just the instance
- `docs-as-contract` — sweep docs on behaviour change, why-not-what comments, run documented commands

**Working style & hygiene**
- `git-hygiene` — atomic commits, branch before risk, never commit debris or secrets
- `leave-no-mess` — clean up processes, temp files, and scaffolding before done
- `context-checkpoint` — externalize state so long tasks survive compaction
- `subagent-fanout` — delegate broad searches to keep the main context clean
- `cross-platform-care` — scripts that survive a machine they didn't develop on

**LLM application code**
- `llm-app-code` — treat model output as untrusted input; schema-validate, gate writes

## Agents

**Skills fix habits; agents fix structure.** A skill makes the driving model reach for a discipline it already has. But one gap no checklist can close is *self-correlation*: a model reviewing its own work inherits its own anchoring — the same context, the same wrong assumption it made an hour ago. Subagents close that gap structurally, because each one runs in a clean context. The `agents/` directory packages Fable's independence disciplines as reusable subagent definitions for Claude Code's `Agent` tool.

Install by dropping a file into `~/.claude/agents/` (or a project's `.claude/agents/`); it registers at the next session start.

**Fresh-context independence** (uncorrelated eyes on your own work):

- `skeptic` — adversarial verifier: takes one claim and tries to *refute* it from primary evidence; returns CONFIRMED / REFUTED / UNPROVEN with the evidence trail. For load-bearing conclusions, especially your own.
- `fresh-eyes-reviewer` — red-team review of a diff with zero knowledge of the author's reasoning, by design; reports only findings with a concrete failure scenario attached.
- `done-gate` — spec-compliance audit before "done": every requirement in the original request checked against evidence, cheap verifications re-run, unevidenced claims flagged.
- `blind-judge` — grades N provenance-stripped candidates against a rubric, criterion-by-criterion, with anti-halo and position-bias guards. For judge panels and tournament selection (it's how this repo's own benchmarks were scored).
- `plan-premortem` — "this plan already failed; write the incident report": verifies the plan's factual claims against the repo, surfaces unverified load-bearing assumptions, names the riskiest step and the cheapest de-risking probe.

The verification agents deliberately pin `model: opus` — the point is a cheap driver doing the legwork while the strongest available model does the judging, not the reverse. Override the `model:` field to taste.

**Cross-model independence** (blind spots that don't correlate with Claude's):

- `codex` — runs the OpenAI Codex CLI (GPT-5.6) as a subagent inside Claude fan-outs. The orchestrator picks model tier and reasoning effort per task via two prompt headers (`codex-model:`, `codex-effort:`), steered by an evidence-based routing guide baked into the description: Luna for mechanical/lookup work, Terra at high effort for routine implementation (the best measured marginal return), Sol at xhigh for long-horizon, multi-file, and adversarial-review work — where Sol's higher completion rate makes it cheaper *per completed task* than Terra despite 2× the token price. Hard rules: never hand Luna a >200K-token context (long-context recall cliff), and escalate effort on retry rather than defaulting to max (quality vs. effort is non-monotonic). Requires the `codex` CLI installed and authenticated; verified against codex-cli 0.144 / GPT-5.6 GA (2026-07).

## Attribution

Skills authored by Fable to lift lighter models to its own working standard. Benchmark run and scored with Claude Opus 4.8.
