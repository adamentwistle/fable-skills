<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Blind grader's final output for the edge-numerical area, unmodified. -->

---

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
