# fable-skills

A library of 39 **engineering-discipline skills** — small, composable instruction files that encode *how a careful senior engineer works*, not what any particular framework does.

## The premise

The most capable Claude models don't just know more — they *work* more carefully. Fable 5 reaches for a codebase's own conventions before writing, proves a bug's cause before fixing it, sweeps edge cases before declaring done, and reports what it actually verified rather than what it assumes. A strong-but-lighter model like Opus 5 or Sonnet 5 *can* do all of that too — it just doesn't always reach for those habits unprompted.

These skills close that gap. Fable identified the places where a less deliberate run tends to fall short of its own ceiling — orientation, root-cause discipline, security reflexes, edge-case coverage, honest reporting — and wrote each habit down as an explicit, always-available checklist. Load them into a session and a model follows the discipline on purpose instead of leaving it to chance. The goal is simple: **Fable-level output from whatever model is driving.**

Each skill is one focused habit. They fire situationally — a debugging task pulls in `root-cause-debugging`, a diff touching user input pulls in `security-reflexes`, a schema change pulls in `data-migration-safety` — so the model carries the right discipline into the right moment without drowning in guidance.

## Does it actually help? Benchmark 3 (September 2026, current models)

Same idea throughout: run an identical task through fresh headless sessions with **no skills** and **with the relevant skill files**, then score every output blind against a fixed answer key. Benchmark 3 is the one to cite. It runs on the current model line-up, uses the actual `SKILL.md` files rather than summaries, and every run, grade and cost figure is committed under [`benchmark/b3/`](benchmark/b3/) with a reproducible harness.

**Method.** Nine task areas (four reused verbatim from the July benchmarks, five new ones designed and then adversarially verified by a separate agent), each with a 7 to 14 item answer key. Every cell is **5 independent runs** of a headless Claude Code session (`claude -p`) with no tools, no installed skills, and no MCP servers, so the bare condition is genuinely bare. The with-skills condition gets the task's two or three skill files appended to the system prompt as activated skills. An Opus 5 judge grades one candidate at a time with model names redacted, returning a true/false per item with a verbatim citation. 315 graded runs in total; solver cost about $51 and judging about $46 at list price, all through a normal Claude Code login.

Mean score per cell, bare → with skills (Δ), n = 5 each:

| Area (max) | Haiku 4.5 | Sonnet 5 | Opus 5 | Fable 5.1 bare |
|---|:---:|:---:|:---:|:---:|
| security review (14) | 5.8 → **8.4** (+2.6) | 10.0 → **11.2** (+1.2) | 13.6 → **14.0** (+0.4) | 13.0 |
| untrusted content / injection (11) | 2.2 → **4.4** (+2.2) | 9.6 → **10.4** (+0.8) | 10.2 → **11.0** (+0.8) | 10.6 |
| shared-interface change review (11) | 4.0 → **5.8** (+1.8) | 7.6 → **9.2** (+1.6) | 10.8 → **11.0** (+0.2) | 11.0 |
| honest reporting (10) | 4.2 → **5.4** (+1.2) | 7.0 → **8.8** (+1.8) | 9.0 → **10.0** (+1.0) | 10.0 |
| slow-endpoint investigation (11) | 5.0 → **6.8** (+1.8) | 7.6 → **7.8** (+0.2) | 7.8 → **9.0** (+1.2) | 8.8 |
| migration + backfill review (12) | 2.8 → **3.8** (+1.0) | 8.4 → **9.8** (+1.4) | 11.8 → 11.6 (−0.2) | 12.0 |
| concurrency (7) | 5.0 → 5.2 (+0.2) | 6.0 → 6.0 (0.0) | 6.2 → 6.4 (+0.2) | 6.8 |
| root-cause debugging (8) | 2.8 → 2.4 (−0.4) | 4.0 → 3.4 (−0.6) | 6.0 → **7.0** (+1.0) | 6.2 |
| edge cases / numerics (9) | 7.0 → 6.2 (−0.8) | 8.6 → 8.6 (0.0) | 9.0 → 9.0 (0.0) | 9.0 |
| **mean of cell percentages** | **44% → 53%** | **74% → 80%** | **90% → 95%** | **94%** |

Five findings:

1. **Every model gains on average, and the weaker the model the bigger the gain:** +9 points for Haiku 4.5, +6 for Sonnet 5, +5 for Opus 5. The lift is concentrated in the six review-and-report tasks, where the skills change what the model *does* (walks the boundaries, enumerates the consumers, states what it could not verify) rather than what it knows.
2. **Opus 5 with skills matches Fable 5.1 bare.** 95% vs 94% averaged over the nine areas: ahead on debugging, security, injection and performance, tied on three, behind by 0.4 on concurrency and migration. That is the parity thesis measured on the current line-up: the discipline files close most of one model tier.
3. **One tier is the limit.** Sonnet 5 with skills reaches Opus 5 bare on honest reporting, injection, performance and concurrency but stays behind on security, interface review, migration and debugging. Haiku 4.5 with skills never reaches Sonnet 5 bare. Skills prompt the right class of thinking; the subtler findings still need the stronger model.
4. **Where they do not help, and one place they hurt.** The two saturated tasks (concurrency, edge cases) leave nothing to gain above Sonnet. On the debugging task Haiku and Sonnet score slightly lower with skills (within the run-to-run spread); its remaining items are a JSON-`null` sentinel bug that only Opus-class models find and a reproduce-and-verify step that a terse findings format discourages. Haiku also loses 0.8 on the edge-case task: a 10K-character skill bundle can crowd a small model's attention.
5. **Consistency improves with skills.** Spread shrinks in most cells (interface review, Haiku sd 1.3 → 0.7; honest reporting, Sonnet 1.7 → 0.7; migration, Sonnet 2.0 → 0.7), and Opus with skills hits the ceiling with zero variance on four of nine areas. The gain is a higher floor, not just a higher mean.

**Two iterations, both kept.** Iteration 1 ran with the skills as rewritten by Fable 5.1 at the start of this pass. Its per-item tables showed the same misses across models even with the skills loaded: the reproduce-and-verify line, the baseline measurement, the pre-merge check, the consumers or claims the reviewer could not verify. Seven skills gained one rule (the requested output format never drops those lines), and the affected cells were re-run as iteration 2, which is the table above. Injection improved for all three models (+1.4, +0.8, +0.8) and Opus debugging by +1.2; Haiku and Sonnet debugging lost 0.6 each. The iteration-1 runs and grades stay under [`benchmark/b3/iteration-1/`](benchmark/b3/iteration-1/).

**Reproduce it** (needs the `claude` CLI logged in; no API key):

```
python benchmark/harness.py run    --suite b3 --areas all --models haiku,sonnet,opus,fable --conditions bare --n 5
python benchmark/harness.py run    --suite b3 --areas all --models haiku,sonnet,opus --conditions skills --n 5
python benchmark/harness.py grade  --suite b3 --judge opus
python benchmark/harness.py report --suite b3
```

**Caveats, stated plainly.** n = 5 per cell is directional, not conclusive; differences under about 0.5 are within noise. The judge is a model applying an objective checklist with citations, not a human. Runs are single-turn with no tools, so this measures what a model says about a problem, not how it behaves across an agentic session. The skills were delivered as system-prompt instructions; other placements were not measured. The five new tasks were designed and verified by Fable 5.1 agents, so an author-model bias in Fable's favour is possible, and Fable bare still misses items on six of them.

### Earlier results (July 2026, Opus 4.8 and Sonnet 5)

The July benchmarks are preserved verbatim under [`benchmark/tasks`](benchmark/tasks/), [`runs`](benchmark/runs/) and [`grading`](benchmark/grading/) (recovered from the session transcript; see [`benchmark/README.md`](benchmark/README.md)). They reported large lifts on the debugging task (Opus 4.8 5.2 → 7.8 of 8, Sonnet 5 4.4 → 6.4) and a security review that went from 10 to 13 of 14. Read them with one fact in mind: their with-skills condition used two- or three-sentence *condensed summaries* of the skills in the user prompt, and in the debugging area that summary spelled out the reproduce-and-verify step and the shared-mutable-return edge case that the answer key rewards. Benchmark 3 replaced that protocol with the real skill files, and the July debugging lift does not reproduce under it. The July numbers are history; the table above is the claim.

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

Skills authored by Fable to lift lighter models to its own working standard. Benchmark 3 run through headless Claude Code on Haiku 4.5, Sonnet 5, Opus 5 and Fable 5.1, blind-graded by Opus 5; the July 2026 benchmarks were run and scored with Claude Opus 4.8.
