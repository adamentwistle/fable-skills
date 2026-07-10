# Recovered scores — fable-skills benchmarks (session ec152094, 2026-07-07)

All tables below are VERBATIM quotes from the session transcript (blind-grader final outputs and the
orchestrator's summary messages). Only the section headers and provenance notes are recovery annotations.

## R-number → run mapping (Benchmark 2 blind grading)

Orchestrator's stated map (verbatim): "I'm keeping the private map: R1–5 = Opus/no-skills, R6–10 = Opus/skills, R11–15 = Sonnet/no-skills, R16–20 = Sonnet/skills."

Within each group of five, R-numbers follow run index in order (verified by content match: R1 = opus48-bare-run1,
R2 = opus48-bare-run2 in the debugging area). So for every area:

| R | run |
|---|---|
| R1–R5 | opus48-bare-run1..5 |
| R6–R10 | opus48-skills-run1..5 |
| R11–R15 | sonnet5-bare-run1..5 |
| R16–R20 | sonnet5-skills-run1..5 |

## Benchmark 2 — cross-model summary (orchestrator message, verbatim)

**Mapping:** R1–5 = Opus/no-skills, R6–10 = Opus/skills, R11–15 = Sonnet/no-skills, R16–20 = Sonnet/skills.

| Area | Opus 4.8 bare | Opus 4.8 +skills | Sonnet 5 bare | Sonnet 5 +skills |
|---|:---:|:---:|:---:|:---:|
| **Debugging** (/8) | 5.2 (65%) | **7.8 (98%)** | 4.4 (55%) | 6.4 (80%) |
| **Concurrency** (/7) | 6.4 (91%) | **7.0 (100%)** | 6.0 (86%) | 7.0 (100%) |
| **Edge/numerical** (/9) | 8.2 (91%) | **9.0 (100%)** | 8.6 (96%) | 9.0 (100%) |

## Benchmark 2 — per-run, per-item blind-grader tables

### Debugging (answer key A1–A8; grader output verbatim)

|Review|A1|A2|A3|A4|A5|A6|A7|A8|Total /8|
|---|---|---|---|---|---|---|---|---|---|
|R1|Y|Y|Y|Y|Y|||| 5|
|R2|Y|Y|Y|Y|Y|Y||| 6|
|R3|Y|Y||Y||Y||| 4|
|R4|Y|Y|Y|Y|Y|||| 5|
|R5|Y|Y|Y|Y|Y|Y||| 6|
|R6|Y|Y|Y|Y|Y|Y|Y|Y| 8|
|R7|Y|Y|Y|Y|Y|Y|Y|| 7|
|R8|Y|Y|Y|Y|Y|Y|Y|Y| 8|
|R9|Y|Y|Y|Y|Y|Y|Y|Y| 8|
|R10|Y|Y|Y|Y|Y|Y|Y|Y| 8|
|R11|Y|Y|Y|Y|Y|||| 5|
|R12|Y|Y|Y|Y|Y|||| 5|
|R13|Y|Y|Y||Y|||| 4|
|R14|Y|Y|Y||Y|||| 4|
|R15|Y|Y|Y|Y||||| 4|
|R16|Y|Y|Y|Y|Y|Y|Y|| 7|
|R17|Y|Y|Y|Y|Y|Y|Y|| 7|
|R18|Y|Y|Y||Y|Y|Y|| 6|
|R19|Y|Y|Y|Y|Y|Y||| 6|
|R20|Y|Y|Y||Y|Y|Y|| 6|

Group means (Total /8):
- R1–R5: (5+6+4+5+6)/5 = 26/5 = 5.2
- R6–R10: (8+7+8+8+8)/5 = 39/5 = 7.8
- R11–R15: (5+5+4+4+4)/5 = 22/5 = 4.4
- R16–R20: (7+7+6+6+6)/5 = 32/5 = 6.4

Notes on the strictest calls:
- A3 credited when a review rejects either "always re-read/drop cache" or "manual clear_cache." R3 was denied A3 (its non-fixes were a cosmetic sentinel swap, TTL, "restart," and lru_cache — none is the always-re-read or manual-clear rejection).
- A5 denied for R15: its only concurrency point was external partial writes fixed by "atomic write + retry," not the in-process check-then-act race / lock the key asks for.
- A8 requires the specific JSON-`null`/empty sentinel latch failure. Reviews that only noted first-call open/json.load exceptions leaving `_cache` None (R6 aside, and R19/R20) were not credited A8 for the error-path mention alone — only R6, R8, R9, R10 name the null-content-defeats-sentinel case.
- A4 denied for R13, R14, R18, R20 (no path-keying observation).

Model suitability: this nuanced, consistency-sensitive 20-way rubric grading is a good fit for Opus 4.8 with extended thinking; settings are appropriate, so no change is recommended.

### Concurrency (answer key B1–B7; grader output verbatim)

## Blind Grading Results

| Review | B1 | B2 | B3 | B4 | B5 | B6 | B7 | Total /7 |
|--------|----|----|----|----|----|----|----|----------|
| R1  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R2  | Y |   | Y | Y | Y | Y | Y | 6 |
| R3  | Y |   | Y | Y | Y | Y | Y | 6 |
| R4  | Y |   | Y | Y | Y | Y | Y | 6 |
| R5  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R6  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R7  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R8  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R9  | Y | Y | Y | Y | Y | Y | Y | 7 |
| R10 | Y | Y | Y | Y | Y | Y | Y | 7 |
| R11 | Y |   | Y | Y | Y | Y | Y | 6 |
| R12 | Y |   | Y | Y | Y | Y | Y | 6 |
| R13 | Y |   | Y | Y | Y | Y | Y | 6 |
| R14 | Y |   | Y | Y | Y | Y | Y | 6 |
| R15 | Y |   | Y | Y | Y | Y | Y | 6 |
| R16 | Y | Y | Y | Y | Y | Y | Y | 7 |
| R17 | Y | Y | Y | Y | Y | Y | Y | 7 |
| R18 | Y | Y | Y | Y | Y | Y | Y | 7 |
| R19 | Y | Y | Y | Y | Y | Y | Y | 7 |
| R20 | Y | Y | Y | Y | Y | Y | Y | 7 |

### Group means (Total /7)

| Group | Mean |
|-------|------|
| R1–R5   | 6.4 |
| R6–R10  | 7.0 |
| R11–R15 | 6.0 |
| R16–R20 | 7.0 |

### Grading notes (B2 was the discriminating column)

B2 required a **distinctly named lost-update / dropped-increment**, not just the TOCTOU race. Key judgment calls:

- **Blank on B2** (R2, R3, R4, R11, R12, R13, R14, R15): These named only the check-then-act race — "both pass the check," "both read count&lt;limit before either writes," or "both increment." Describing two threads passing the guard is B1, not B2. Even R14's "read same count both increment" stops short of naming a *dropped/lost* increment, so I held it strict.
- **Y on B2** (R1, R5, R6–R10, R16–R20): These explicitly name the lost/dropped/clobbered increment — e.g. "dropping increments" (R1), "increments are lost" (R5, borderline but literally names lost increments), "dropping one" (R16/R19), "clobbers concurrent increment" (R17), "undercounting" (R20).

All 20 reviews reliably caught B1, B3, B4, B5, B6, and B7 — the spread comes almost entirely from B2. The R6–R10 and R16–R20 clusters swept all seven; R1–R5 and R11–R15 were pulled down by missing the distinct lost-update call-out.

---

**Model suitability:** This grading task involves fine-grained, strict rubric judgment across 20 items where a single column (B2) hinges on precise wording distinctions — exactly the kind of careful discrimination that benefits from a high-capability model with extended thinking. Opus 4.8 with extended thinking is well-matched here; no downgrade is warranted.

### Edge/numerical (answer key C1–C9; grader output verbatim)

# Blind Grading Results

| Review | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | Total /9 |
|--------|----|----|----|----|----|----|----|----|----|----------|
| R1  | Y | Y | Y | Y | Y |   | Y | Y |   | 7 |
| R2  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R3  | Y | Y | Y | Y | Y | Y | Y | Y |   | 8 |
| R4  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R5  | Y | Y | Y | Y | Y | Y | Y | Y |   | 8 |
| R6  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R7  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R8  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R9  | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R10 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R11 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R12 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R13 | Y | Y | Y | Y | Y | Y | Y | Y |   | 8 |
| R14 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R15 | Y | Y | Y | Y | Y | Y | Y | Y |   | 8 |
| R16 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R17 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R18 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R19 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |
| R20 | Y | Y | Y | Y | Y | Y | Y | Y | Y | 9 |

## Group means

| Group | Mean Total /9 |
|-------|---------------|
| R1–R5   | 8.2 |
| R6–R10  | 9.0 |
| R11–R15 | 8.6 |
| R16–R20 | 9.0 |

## Grading notes (the strict calls)

- **R1** lost two points. C6: it proposes `fsum` for summation accuracy but never flags money-as-binary-float or recommends Decimal/integer cents — that is a different hazard, so blank. C9: only "skip-or-log," no naming of row index/field/value.
- **R3, R5, R13, R15** all lost C9 only. R3 identifies "one bad row aborts the batch" but never says to name the offending row. R5 says "skip/log." R13/R15 propose "logging/telemetry/metrics per row" but do not explicitly name row index/field/value in the error — under the strict rule that fails C9.
- **R11 and R12** were the marginal C9 grants: R11 says "log row index/content," R12 says "log/return rejected-row indices." Both explicitly name the row index (beyond bare skip/log), so they clear the bar where R13/R15 did not. This is the key distinction driving the R11–R15 group mean.
- Every review correctly hit C1–C5, C7, C8. Differentiation lived almost entirely in C6 (R1) and C9.

---

Model suitability: the assigned model (Opus 4.8, 1M context) with extended reasoning is well-matched to this task — the scoring required fine comparative judgment across 20 near-identical reviews and consistent application of a strict C9 boundary, which is exactly where a high-reasoning model earns its keep. No change recommended.

## Benchmark 2 — orchestrator's earlier SELF-graded tally (Opus runs only; superseded by the blind grades above; verbatim)

| Area (what it exercises) | Without skills | With skills | Δ |
|---|:---:|:---:|:---:|
| **Root-cause debugging** (stale-cache bug, key=8) | 5.4/8 · 68% (range 5–6) | **7.8/8 · 98%** (range 7–8) | +30pts |
| **Concurrency** (racy rate limiter, key=7) | 6.4/7 · 91% (range 6–7) | **7.0/7 · 100%** (range 7) | +9pts |
| **Edge/numerical** (CSV revenue parser, key=9) | 8.4/9 · 93% (range 8–9) | **9.0/9 · 100%** (range 9) | +7pts |

(The blind re-grade later reported: "debugging 5.2 vs 5.4, 7.8 vs 7.8; concurrency 6.4/7.0 identical".)

## Benchmark 1 — security/code-review (n=1 per condition, Opus 4.8; blind-grader output verbatim)

Review A = control (no skills) = runs/security/opus48-bare-run1.md; Review B = treatment (with skills) = runs/security/opus48-skills-run1.md.
Orchestrator summary (verbatim): "Independent blind tally confirms it: **control 10/14, treatment 13/14**".

# Code Review Grading

| # | Issue | Review A | Review B |
|---|-------|:---:|:---:|
| 1 | SQL injection (user_id/status interpolated) | Y | Y |
| 2 | DB connection never closed (leak) | Y | Y |
| 3 | format_receipt TypeError ("Order #" + int id) | Y | Y |
| 4 | Division by zero on empty orders | Y | Y |
| 5 | Money as binary float (should be Decimal/cents) | Y | Y |
| 6 | apply_discount: pct not range-validated | Y | Y |
| 7 | status not validated against allowlist | Y | Y |
| 8 | Broken object-level auth / IDOR | N | Y |
| 9 | Null/None amount not handled | Y | Y |
| 10 | Currency not formatted to 2 decimals | Y | N |
| 11 | Raw DB errors leak to caller | Y | Y |
| 12 | Rounding policy not applied (fractional cents mid-calc) | N | Y |
| 13 | Unbounded result set (no LIMIT / pagination) | N | Y |
| 14 | Fragile positional tuple indexing (use sqlite3.Row) | N | Y |

## Totals
- **Review A: 10 / 14**
- **Review B: 13 / 14**

## Issues caught by only one reviewer
- **Only Review A:** #10 Currency not formatted to 2 decimals (A explicitly calls for 2dp display formatting; B fixes only the TypeError with `str()` and never addresses display precision).
- **Only Review B:** #8 IDOR/broken object-level authorization; #12 rounding policy / fractional cents in `apply_discount`; #13 unbounded result set (no LIMIT); #14 fragile positional tuple indexing (`sqlite3.Row`).

## Assessment
Both reviews are correct and actionable on the shared findings, with accurate fixes (parameterized queries, `contextlib.closing`, Decimal, pct range checks, empty/None guards) — Review A even adds a genuinely sharp note that `with sqlite3.connect()` manages the transaction but does not close the connection. Review B is materially deeper: it catches the highest-severity architectural issue (the IDOR/authorization flaw, which A misses entirely) plus rounding policy, pagination, and robust row access, and its remediations (chained sanitized errors, quantize with ROUND_HALF_UP, documented security/rounding contracts) are more complete. A's lone edge is currency display formatting, a low-severity item; overall B is the stronger review on both breadth and depth while remaining equally correct.

(Model note: Opus 4.8 is well-suited to this nuanced blind-grading task, so no model change is suggested.)
