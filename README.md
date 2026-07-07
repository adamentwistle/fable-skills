# fable-skills

A library of 35 **engineering-discipline skills** — small, composable instruction files that encode *how a careful senior engineer works*, not what any particular framework does.

## The premise

The most capable Claude models don't just know more — they *work* more carefully. Fable 5 reaches for a codebase's own conventions before writing, proves a bug's cause before fixing it, sweeps edge cases before declaring done, and reports what it actually verified rather than what it assumes. A strong-but-lighter model like Opus 4.8 *can* do all of that too — it just doesn't always reach for those habits unprompted.

These skills close that gap. Fable identified the places where a less deliberate run tends to fall short of its own ceiling — orientation, root-cause discipline, security reflexes, edge-case coverage, honest reporting — and wrote each habit down as an explicit, always-available checklist. Load them into a session and a model follows the discipline on purpose instead of leaving it to chance. The goal is simple: **Fable-level output from whatever model is driving.**

Each skill is one focused habit. They fire situationally — a debugging task pulls in `root-cause-debugging`, a diff touching user input pulls in `security-reflexes`, a schema change pulls in `data-migration-safety` — so the model carries the right discipline into the right moment without drowning in guidance.

## Does it actually help? A benchmark

To sanity-check the premise, the same task was run through **two fresh Opus 4.8 agents** — one with no guidance ("without"), one given the relevant skill files ("with") — and both reviews were scored **blind** by an independent third agent against a fixed answer key.

**Task:** review a small Python orders module seeded with **14 distinct latent issues** (SQL injection, a connection leak, division-by-zero, float-money drift, a missing authorization check, and more) and report everything found.

**Result:**

| | Issues found (of 14) | Notable |
|---|:---:|---|
| **Without skills** | **10 / 14** | Solid: caught the injection, the leak, div-by-zero, float money |
| **With skills** | **13 / 14** | Caught everything the control did **plus the IDOR / broken object-level authorization flaw the bare run missed entirely** — the single highest-severity issue in the file — along with an explicit rounding policy, result-set pagination, and robust row access |

The skill-guided run didn't just find *more* — it found the issue that mattered most. Walking the `security-reflexes` checklist ("every mutating path: WHO is calling and MAY they touch THIS object?") surfaced an authorization gap that a capable-but-unprompted review sailed past. The bare run's only unique catch was a low-severity currency-formatting nit.

**Honest caveats:** this is a single illustrative task (n=1), not a statistical benchmark — treat it as a directional signal, not a proof. The baseline was already strong (Opus 4.8 is a good model), so the delta is "good → more complete," not "broken → fixed." The effect is largest exactly where the skills add a checklist the model wouldn't otherwise run (security, edge cases, honest scope-flagging) and smallest on the obvious happy-path bugs any competent review catches. Your mileage varies by task.

## Using the skills

Each skill lives in its own directory as a `SKILL.md` with YAML frontmatter (`name`, `description`) and a short body. The `description` is what a harness matches against the situation to decide when to activate the skill.

**With Claude Code:** drop the skill directories into a discoverable skills location (e.g. `~/.claude/skills/` or a project `.claude/skills/`) and they become available to the `Skill` tool. The model selects them by description as tasks arise.

**Anywhere else:** the bodies are plain Markdown — paste the relevant one into a system prompt, or concatenate a task-appropriate subset. That's exactly how the benchmark's "with skills" run was configured.

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
