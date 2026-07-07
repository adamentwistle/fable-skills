---
name: llm-app-code
description: Code calling LLM APIs — model output is untrusted input: defensive parsing, server-side schema validation, authorization never from model output, approval-gated writes, injection awareness, cache-prefix economics, streaming edges. Use for agent loops, tool definitions, or prompt/model changes.
---

# LLM App Code

Code around an LLM has one governing fact: **the model is an untrusted, non-deterministic input source that reads like a trusted colleague.** Most LLM-app bugs come from forgetting one half of that sentence.

## Model output is untrusted input — always

- **Parse defensively.** Every `JSON.parse` of model output wrapped and shape-validated; expect markdown fences around JSON, trailing prose, truncated output at max_tokens, and empty strings. A malformed model response must degrade a turn, never crash the app.
- **Validate tool-call arguments against the schema server-side** before execution — required keys, types, enums, AND rejection of unexpected keys. The model will eventually send every wrong shape.
- **Whitelist strict-enum values headed to external systems.** Model-generated slugs/networks/plans get mapped through a server-side table — never passed through, even when the prompt "guarantees" the format.
- **Authorization never derives from model output.** The model can *propose*; only server-recorded state + explicit user action can *approve*. Never let a model-visible tool perform destructive/financial writes directly — gate writes behind a human-approval step bound server-side (proposal pattern). Never trust a model's claim about what the user consented to.
- **Prompt injection is transitive**: any tool result containing third-party text (web pages, tickets, emails) is a channel for instructions to your model. Treat tool results as data in your prompt design; never give a model simultaneously (a) exposure to untrusted text and (b) unsupervised dangerous capabilities.

## Determinism where it matters

Route load-bearing guarantees through code, not prompts: format enforcement, redaction/scrubbing of sensitive figures, filtering which tools the model sees, output length caps. A prompt instruction is a strong suggestion; a deterministic post-processor is a guarantee. Use both (prompt = primary, code = backstop).

## Prompt & model changes are behavior changes

- Never ship a prompt/model change on vibes. Run the project's eval suite; if none exists for the behavior you're changing, write at least a smoke set first. A model swap that "just works" in one manual test can regress safety/format behaviors discovered only under repetition.
- **Cache economics**: providers cache the prompt prefix. Keep stable content (system prompt, tool defs) first and byte-identical across turns; put variable content last. A "harmless" reordering or timestamp in the system prompt can silently multiply token cost.
- Pin model IDs explicitly; know each pinned model's parameter quirks (thinking/effort defaults differ per model — verify, don't assume compatibility when swapping).

## Streaming and the agent loop

- Handle the full event grammar: partial deltas, tool-use blocks interleaved with text, stop reasons (`max_tokens` mid-JSON!), and error events mid-stream. Test the abort path — client disconnects mid-generation must clean up.
- Agent loops need: an iteration cap, per-tool timeouts, token/cost budget, and dedupe/idempotency on tool execution (retried turns re-issue tool calls).
- Retries: retry transient API errors with backoff; NEVER blind-retry a turn whose tool side-effects may have executed.

## Cost/latency hygiene

Log tokens + cost per turn from day one (you cannot fix what you don't attribute). Trim tool results before feeding them back (models don't need 400-row payloads). Choose the model tier per call site deliberately — classification/extraction rarely needs the flagship.
