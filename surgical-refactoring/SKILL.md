---
name: surgical-refactoring
description: Refactor/rename/migration discipline — enumerate all call sites before editing, separate mechanical from judgment edits, keep the build green, verify by absence and presence. Use for renames touching 3+ sites, signature/type reshapes, moving code, or codebase-wide pattern swaps.
---

# Surgical Refactoring

Refactors fail in predictable ways: missed call sites, half-migrated hybrid states, scope creep, and behavior changes smuggled in as "cleanup". The countermeasures are mechanical.

## 1. Enumerate every touch point BEFORE the first edit

Grep for the symbol/pattern with multiple casings and forms (`fooBar`, `foo_bar`, `FooBar`, string literals, dynamic access, re-exports, tests, docs, config). Count them. Write the list down. The refactor is done when that list is exhausted — not when the build passes, because dead branches, string-keyed lookups, and mock/stub twins compile fine while broken.

Special sweeps people miss: test fixtures, mock implementations that mirror real ones, serialized/persisted data keys, API contract strings, comments/docs, and anything reached by reflection or string dispatch.

## 2. Separate mechanical from judgment edits

Split the work: (a) purely mechanical transformations (rename, move, signature reshuffle) with zero behavior change, and (b) judgment edits (logic changes, improvements). Do them in **separate passes** — ideally separate commits. A diff that mixes both is unreviewable, and behavior bugs hide inside "just a rename".

If asked only to refactor: behavior must be bit-identical. Resist fixing bugs you find mid-refactor — note them and report them instead (fixing them silently changes behavior the user didn't ask to change).

## 3. Sequence to keep the build green

Order edits so the project compiles at every intermediate point where possible: introduce the new shape first (new function/type alongside old), migrate call sites in groups, then delete the old shape last. For breaking changes that can't overlap, do the full sweep in one atomic pass — never leave a session with half the call sites migrated.

## 4. Verify by absence AND presence

- Absence: grep the old name/pattern → zero hits (or a written justification per hit).
- Presence: the project's full gate suite (build/typecheck, lint, tests) after the last edit.
- Behavior: run whatever exercises the refactored path — a pure rename that passes tests can still break string-keyed runtime dispatch.

## 5. Scope is a contract

"While I'm here" is how a 5-file rename becomes a 40-file diff nobody asked for. Improvements you notice outside the requested scope go in your report as suggestions, not in the diff. The exception: changes strictly required to complete the requested refactor (a caller that must adapt).

## When to stop and re-plan

If the sweep reveals 5× more call sites than expected, a public API boundary, or persisted-data implications (stored keys, wire formats, migrations needed) — stop and surface it. Those change the cost/risk profile the user approved.
