---
name: llm-app-code
description: Code calling LLM APIs — model output is untrusted input: defensive parsing, server-side schema validation, authorization never from model output, approval-gated writes, injection awareness, cache-prefix economics, streaming and agent-loop edges. Use when writing or reviewing agent loops, tool definitions and handlers, structured-output parsing, prompt or model changes, streaming handlers, or any code that turns model output into an action.
---

# LLM App Code

One governing fact: **the model is an untrusted, non-deterministic input source that reads like a trusted colleague.** Weak LLM-app code trusts the model's JSON, its tool arguments, and its claims about the user; strong code treats every model token as internet input and puts the guarantees in code.

## Model output is untrusted input — always

- **Parse defensively.** Every parse of model output is wrapped and shape-validated. Expect markdown fences around JSON, leading or trailing prose, truncation at `max_tokens`, empty strings, and duplicate keys. A malformed response degrades one turn (retry or fallback), never crashes the process.
- **Validate tool-call arguments server-side against the schema** before execution — required keys, types, enums, ranges, AND rejection of unexpected keys. The model will eventually send every wrong shape.
- **Map strict-enum values headed to external systems through a server-side table.** Model-generated slugs, IDs, plan or network names are never passed through, even when the prompt "guarantees" the format.
- **Authorization never derives from model output.** The model *proposes*; only server-recorded state plus an explicit user action *approves*. Destructive or financial writes go behind an approval step bound server-side to the specific proposal. Never trust a model's claim about what the user consented to, who the user is, or what a prior turn decided.
- **Prompt injection is transitive.** Any tool result containing third-party text (web pages, tickets, emails, file contents) is a channel for instructions to your model. Never give one model turn both (a) exposure to untrusted text and (b) unsupervised dangerous capabilities — split the roles or gate the capability.

## Determinism where it matters

Route load-bearing guarantees through code, not prompts: output format, redaction of sensitive fields, which tools the model sees per user or role, output length caps, allowed URL and domain lists. A prompt instruction is a strong suggestion; a deterministic post-processor is a guarantee. Use both (prompt = primary, code = backstop) and write the test against the backstop.

## Prompt and model changes are behavior changes

- **Never ship a prompt or model change on vibes.** Before editing, capture baseline outputs on a fixed input set — the project's evals, or a smoke set of at least 10 representative inputs including the adversarial ones you can think of. After editing, re-run and diff. Format and safety regressions show up only under repetition.
- **Cache economics:** providers cache the prompt prefix. Stable content (system prompt, tool definitions) goes first and byte-identical across turns; variable content (timestamps, user data, retrieved context) goes last. Verify with the cached-token counts in the response usage — a "harmless" reordering can silently multiply cost.
- **Pin model IDs explicitly** and verify parameter compatibility when swapping (thinking, effort, temperature defaults and limits differ per model) — read the provider's current docs rather than assuming.

## Streaming and the agent loop

- Handle the full event grammar: partial deltas, tool-use blocks interleaved with text, every stop reason (`max_tokens` mid-JSON), and error events mid-stream. Test the abort path: a client disconnect mid-generation must cancel upstream and release resources.
- Every agent loop has an iteration cap, per-tool timeouts, a token/cost budget, and idempotency keys on tool execution so a retried turn can't re-run a side effect.
- Retry transient API errors with backoff. Never blind-retry a turn whose tool side effects may already have executed.

## Cost and latency hygiene

Log tokens and cost per call site from day one. Trim tool results before feeding them back (no 400-row payloads). Choose the model tier per call site deliberately — classification and extraction rarely need the flagship.

## Exit check

For each place model output reaches a side effect, trace one path and name the line where each of these happens: parse → schema validation → authorization check → execution → logging. Add fixtures for fenced, truncated, empty, and extra-key outputs to the test suite. If you changed a prompt or model, the report includes the before/after eval results.
