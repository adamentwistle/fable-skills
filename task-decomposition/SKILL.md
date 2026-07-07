---
name: task-decomposition
description: Planning discipline for multi-step work — acceptance test first, read the terrain, dependency-ordered steps, de-risk the riskiest step early, re-plan on surprise. Use at the start of any task touching 3+ files or steps, and mid-task when something invalidates the approach.
---

# Task Decomposition

Strong runs front-load understanding and commit to a sequence. Weak runs start editing in the first minute and discover the real shape of the task by breaking things. Spend the first 10–20% of the task here.

## 1. Restate the goal as an acceptance test

One or two sentences: "Done means ___ works / passes / renders." If you can't state it, you don't understand the task — reread the request; if genuinely ambiguous on a decision the user owns, ask ONE batched set of questions now (not a drip mid-task). Ambiguity you can resolve from the code is yours to resolve, not the user's.

## 2. Read the terrain before planning the route

Before proposing steps:
- Read the project instructions (CLAUDE.md) for constraints that override defaults.
- Find and read every file you expect to edit, plus one caller/consumer of each — the blast radius is defined by callers.
- Find the existing pattern for this kind of change (the last similar feature/commit) and plan to imitate it, not invent.

## 3. Write the step list, dependency-ordered

3–8 concrete steps, each independently verifiable, ordered so the build stays green as long as possible (types/schemas first, then implementations, then call sites, then UI). For each step note: files touched + how you'll verify it.

Track it visibly (todo list) if 3+ steps; mark steps done as you complete them, exactly one in-progress at a time.

## 4. Identify the risky step and de-risk it first

One step usually carries the real uncertainty (the unfamiliar API, the migration, the concurrency). Do a cheap probe of THAT step early — a spike, a dry run, a one-file prototype — before investing in the safe steps. Discovering step 5 is impossible after finishing steps 1–4 is the expensive failure.

## 5. Re-plan on surprise, don't push through

When reality contradicts the plan (an API doesn't exist, a test reveals a hidden coupling, a file is generated), STOP editing. Update the plan explicitly: what changed, which steps die, which are added. Pushing the original plan through contradicting evidence is how half-finished hybrid states happen. If the surprise changes the scope the user asked for, surface it instead of silently redefining the task.

## 6. Keep a ledger on long tasks

For work spanning many steps or likely to hit context limits: maintain a short state file (scratchpad) with — goal, decisions made + why, steps done, steps remaining, current blockers. Update it at each milestone. It is cheap insurance against context loss and drift.

## Exit condition

The task is done when the step list is empty AND the acceptance test from step 1 passes — verified, not assumed (see pre-done-review).
