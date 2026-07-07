---
name: test-design
description: What to test and how — regression test fails first, boundary tables, behavior over implementation, boundary-only mocks, the mock-echo trap. Use when writing tests, adding regression coverage for a fix, or judging whether existing tests protect anything.
---

# Test Design

A test's value is the bug it would catch. Write tests by asking "what realistic mistake would make this fail?" — a test no plausible mistake can fail is ballast.

## What to test (priority order)

1. **The bug you just fixed** — regression test that fails on the pre-fix code. Write it FIRST, watch it fail, then fix. A "regression test" that never failed proves nothing; if you fixed first, temporarily revert the fix to confirm the test goes red.
2. **The contract, at its boundaries** — for each input: empty/zero/null, one, many, max, just-past-max, wrong type/shape, duplicate, unicode/whitespace where strings. Use a table: input → expected. Boundaries are where implementations disagree with intentions.
3. **The failure paths** — what the code does when its dependency errors, times out, returns malformed data. Untested error handling is usually broken error handling.
4. **The invariant** — properties that must hold across all inputs (sorted output stays sorted, money sums preserved, scrubbed text contains no digits). One property test or loop-over-cases beats five example tests.

## Test behavior, not implementation

Assert on observable outcomes (return values, emitted events, state visible to callers, rendered output) — not on internals (which private method was called, internal ordering, exact intermediate structure). Implementation-coupled tests break on every refactor while catching no bugs, training everyone to update tests reflexively — which is how real regressions slip through.

Heuristic: could someone rewrite the function body correctly and keep your test green? They should be able to.

## Mock discipline

- Mock at the boundary you don't own (network, clock, randomness, filesystem) — not your own logic. Mocking your own modules tests the mocks.
- **The mock-echo trap**: a test that stubs `getX` to return `42` and then asserts the result contains `42` tests nothing but the stub. Every mocked test needs some real logic under test between stub and assertion.
- Fix time and randomness explicitly (injected clock/seed) — tests that pass "most of the time" are worse than no tests.
- Keep mock shapes honest: when the real dependency's response shape changes, grep for its mocks — a green suite against a stale mock is a false green.

## Structural rules

- One behavior per test; the name states the expectation ("rejects expired proposal") not the method ("test handleProposal 2").
- Arrange–act–assert, visible in the test body. Shared setup helpers are fine; shared *assertions* hidden in helpers obscure what's protected.
- Tests must not depend on each other or on execution order; each builds its own state and cleans up (or uses fresh fixtures).
- Deterministic first: no real network, no real sleeps (use fake timers), no shared global state across files.

## Calibrate quantity

A tiny pure function needs 1–3 boundary cases, not twelve. A gnarly state machine or money-handling path deserves the full table + failure paths + an invariant. Match the project's existing test idioms and runner conventions — a beautifully designed test in the wrong framework style is a maintenance burden.
