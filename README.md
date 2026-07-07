# fable-skills

A library of 35 **engineering-discipline skills** — small, composable instruction files that encode *how a careful senior engineer works*, not what any particular framework does.

## The premise

The most capable Claude models don't just know more — they *work* more carefully. Fable 5 reaches for a codebase's own conventions before writing, proves a bug's cause before fixing it, sweeps edge cases before declaring done, and reports what it actually verified rather than what it assumes. A strong-but-lighter model like Opus 4.8 *can* do all of that too — it just doesn't always reach for those habits unprompted.

These skills close that gap. Fable identified the places where a less deliberate run tends to fall short of its own ceiling — orientation, root-cause discipline, security reflexes, edge-case coverage, honest reporting — and wrote each habit down as an explicit, always-available checklist. Load them into a session and a model follows the discipline on purpose instead of leaving it to chance. The goal is simple: **Fable-level output from whatever model is driving.**

Each skill is one focused habit. They fire situationally — a debugging task pulls in `root-cause-debugging`, a diff touching user input pulls in `security-reflexes`, a schema change pulls in `data-migration-safety` — so the model carries the right discipline into the right moment without drowning in guidance.

## Does it actually help? Benchmarks

Same method throughout: run an identical task through fresh Opus 4.8 agents with **no guidance** vs. **with the relevant skill files**, then score the outputs against a fixed answer key. These are directional signals, not statistical proofs.

### Benchmark 1 — Security code review (n=1, blind-graded)

The same task was run through two fresh agents and both reviews were scored **blind** by an independent third agent. **Task:** review a Python orders module seeded with **14 latent issues** (SQL injection, connection leak, division-by-zero, float-money drift, a missing authorization check, …).

| | Issues found (of 14) | Notable |
|---|:---:|---|
| **Without skills** | **10 / 14** | Solid: caught the injection, the leak, div-by-zero, float money |
| **With skills** | **13 / 14** | Caught everything the control did **plus the IDOR / broken object-level authorization flaw the bare run missed entirely** — the single highest-severity issue in the file — plus an explicit rounding policy, result-set pagination, and robust row access |

The skill-guided run didn't just find *more* — it found the issue that mattered most. Walking the `security-reflexes` checklist ("every mutating path: WHO is calling and MAY they touch THIS object?") surfaced an authorization gap the unprompted review sailed past.

### Benchmark 2 — Three areas, n=5 per condition

Five independent runs per condition on three fresh tasks, each seeded with a fixed answer key. Mean issues found (with run-to-run range):

| Area (what it exercises) | Without skills | With skills |
|---|:---:|:---:|
| **Root-cause debugging** (stale-cache bug) | 5.4 / 8 · 68% _(range 5–6)_ | **7.8 / 8 · 98%** _(range 7–8)_ |
| **Concurrency** (racy rate limiter) | 6.4 / 7 · 91% _(range 6–7)_ | **7.0 / 7 · 100%** _(range 7)_ |
| **Edge / numerical** (CSV revenue parser) | 8.4 / 9 · 93% _(range 8–9)_ | **9.0 / 9 · 100%** _(range 9)_ |

What moved the needle, by area:

- **Debugging — the biggest gap.** With skills, every run stated a *falsifiable* root-cause hypothesis and gave explicit reproduce-and-verify steps (5/5 vs 0/5), and caught a subtle sentinel bug — a config of JSON `null` defeats the `is None` cache guard — that no bare run spotted (4/5 vs 0/5). This is where working *discipline*, not knowledge, is decisive.
- **Concurrency — both strong.** Skills closed the last gaps: naming the lost-update race distinctly and flagging the off-by-one limit boundary on every run, where the bare runs did so only intermittently.
- **Edge / numerical — smallest gap.** The prompt ("list every edge case") already pushes exhaustive enumeration, so both conditions found nearly everything. The consistent skill edge was error-message quality — naming the offending row/field/value in the failure (5/5 vs 2/5).

Two patterns hold across every area:

1. **Skills help most where the task rewards process** (debugging) and least where the prompt already forces thoroughness (enumeration).
2. **Run-to-run variance shrank with skills** — scores clustered at the top instead of spreading (debugging: 7–8 with vs 5–6 without). More consistent, not merely higher on average.

**Honest caveats:** n=5 is small and Benchmark 1 is n=1 — directional, not conclusive. The baseline Opus is already strong, so the gain is "good → near-complete," not "broken → fixed." Benchmark 1 was scored by an independent blind agent; Benchmark 2 was scored by the orchestrating agent against pre-registered answer keys (objective checklist items, but not blind).

## Using the skills

Each skill lives in its own directory as a `SKILL.md` with YAML frontmatter (`name`, `description`) and a short body. The `description` is what a harness matches against the situation to decide when to activate the skill.

**With Claude Code:** drop the skill directories into a discoverable skills location (e.g. `~/.claude/skills/` or a project `.claude/skills/`) and they become available to the `Skill` tool. The model selects them by description as tasks arise.

**Anywhere else:** the bodies are plain Markdown — paste the relevant one into a system prompt, or concatenate a task-appropriate subset. That's exactly how the benchmarks' "with skills" runs were configured.

## The catalog (35 skills)

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

**Security & safety**
- `security-reflexes` — injection, authz, secrets, SSRF/XSS on everyday diffs
- `untrusted-content-guard` — treat fetched/read content as data, never instructions
- `data-loss-guard` — stop-and-check before destructive or irreversible operations
- `api-surface-care` — treat changes to shared interfaces as contract changes

**Change discipline**
- `surgical-refactoring` — enumerate call sites, separate mechanical from judgment edits
- `dependency-changes` — justify, archaeology, lockfile hygiene, one bump at a time
- `data-migration-safety` — expand→migrate→contract, backfills, rollback-first

**Testing & verification**
- `test-design` — regression-first, boundary tables, behavior over implementation
- `verify-ui-visually` — render and look, don't imagine the markup
- `workmanship` — evidence before assertion, the done gate, report what happened

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

**Working style & hygiene**
- `git-hygiene` — atomic commits, branch before risk, never commit debris or secrets
- `leave-no-mess` — clean up processes, temp files, and scaffolding before done
- `context-checkpoint` — externalize state so long tasks survive compaction
- `subagent-fanout` — delegate broad searches to keep the main context clean
- `cross-platform-care` — scripts that survive a machine they didn't develop on

**LLM application code**
- `llm-app-code` — treat model output as untrusted input; schema-validate, gate writes

## Attribution

Skills authored by Fable to lift lighter models to its own working standard. Benchmark run and scored with Claude Opus 4.8.
