---
name: incident-diagnosis
description: Live-system triage — read-only evidence first, establish what/since-when/how-wide, correlate onset with changes, trace one failing request, mitigate reversibly before root-causing. Use when production is broken now, or before restarting/redeploying/deleting as a first move.
---

# Incident Diagnosis

Code debugging optimizes for finding the cause. Incident work optimizes for restoring service safely — the cause can wait; making things worse cannot. Different discipline, different order.

## 0. Do not touch anything yet

The strong first move is read-only. Restarts, redeploys, cache flushes, and deletes destroy the evidence AND can compound the failure (a restart storm on an overloaded dependency; a redeploy on top of a bad migration). Every state-changing action needs the evidence to support THAT action specifically — "a restart usually fixes it" is pattern-matching, not evidence.

## 1. Establish the three anchors

- **What exactly is failing, observably?** Error message/status/behavior, verbatim — reproduce or observe it yourself if at all possible; second-hand reports compress the detail that matters.
- **Since when?** Find the onset in logs/metrics/monitors. The onset time is the most valuable single fact you can collect.
- **How wide?** One user / one endpoint / one region / everything? A single-tenant failure and a global failure have disjoint cause spaces. Check whether it's already publicly acknowledged (status pages, existing incidents) before deep-diving.

## 2. Correlate the onset with changes

Most incidents are caused by a change. Diff the world at onset time: deploys, config changes, dependency/provider incidents, certificate expiries, cron jobs that fired, data that crossed a threshold (disk full, quota, integer/ID rollover, date boundaries). "Nothing changed" usually means "nothing I know about changed" — widen the search (adjacent teams, provider status, OS/infra auto-updates).

## 3. Localize by following one failing request

Pick ONE concrete failing request/job and trace it through the layers (edge → LB → service → dependency → data), checking at each hop: did it arrive, what did it return, how long did it take? The failure lives at the first layer where behavior diverges from normal. Resist diagnosing from aggregate dashboards alone — averages hide the failing path.

## 4. Mitigate first when impact justifies it

If users are hurting and a reversible mitigation exists — rollback, feature-flag off, failover, rate-limit, scale up — propose/apply it BEFORE completing root-cause analysis. Note what evidence to capture pre-mitigation (logs, a core dump, a copy of bad state) so the trail survives. Rollback of the correlated change is the mitigation with the best prior.

Mitigations must be reversible and understood: never "fix" by deleting data or forcing state you can't restore.

## 5. Then root-cause properly

After service is restored, the investigation becomes ordinary root-cause-debugging (reproduce, bisect, falsifiable hypothesis). An incident closed at "restarted it and it went away" WILL reoccur — say so explicitly if that's where things stand, and record what instrumentation would catch it earlier next time.

## Report structure (during and after)

Timeline (times + facts, no speculation mixed in), current impact, what's confirmed vs suspected, actions taken (with before/after evidence), next action. Update as facts land. Never present a hypothesis as a finding — mislabeled confidence misroutes everyone downstream of your report.
