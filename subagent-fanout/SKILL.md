---
name: subagent-fanout
description: Delegate broad searches and independent subtasks to subagents to keep the main context clean. Use when a question requires sweeping many files or directories, when several independent investigations could run in parallel, or when raw tool output would flood the context you need for the real work.
---

# subagent-fanout

Context spent on file dumps is context unavailable for reasoning. Spend subagent context on search; keep main context for synthesis and edits.

1. **Fan out when the answer spans many files:** "where is auth handled", "find every caller of X", "which configs mention Y". Launch an Explore/general-purpose agent with a precise question and keep only its conclusion. Reading twelve files inline to answer one question is the anti-pattern.
2. **Parallelize independent work:** three unrelated investigations = three agents in one message, not a sequence. Wall-clock and context both win.
3. **Write real briefs.** A subagent has none of your context: state the goal, the constraints, what a good answer looks like, and what to return ("list of file:line + one-line role each" beats "look into auth"). Vague briefs return vague essays.
4. **Don't delegate the single lookup.** If you know the file or symbol, one Grep/Read is faster than an agent round-trip. Delegation pays when breadth is the problem.
5. **Don't duplicate delegated work** — once an agent is searching, don't run the same search inline while waiting.
6. **Trust but verify at the point of use:** an agent's claim about a signature or behavior gets re-checked against the actual file before you edit based on it (see ground-before-edit).

Heuristic: if answering would mean reading more than ~4 files just to locate something, fan out.
