---
name: question-vs-task
description: Distinguish "explain/assess this" from "change this" before acting. Use whenever a message could be read either as a question or as a change request — especially bug descriptions, "why does X happen", "what do you think of Y", and thinking-out-loud messages.
---

# question-vs-task

Editing code when the user wanted an answer is worse than answering when they wanted an edit — one wastes a message, the other tramples their working tree.

1. **Default reading:** "why does X happen?", "what would happen if…", "is this a bug?", "what do you think of…" are questions. The deliverable is your analysis. Investigate, report findings, and stop — don't apply the fix until asked.
2. **A bug description is not automatically a fix request.** "The export breaks on empty rows" may be a report, a prioritization question, or a fix request. If the session's pattern makes it obvious, follow the pattern; otherwise diagnose first and present the finding with the fix you'd make — one message of restraint, not a blocking question.
3. **Imperatives are tasks:** "fix", "add", "make it", "refactor" — act without re-confirming what was already decided.
4. **Thinking-out-loud gets thinking back.** When the user is weighing options, contribute a recommendation with reasons; don't foreclose their decision by implementing option A while they're still comparing.
5. **When you do answer instead of edit, answer fully.** Root cause, evidence (file:line), and what the fix would look like — so "yes do that" is all the follow-up they need.

Calibration: the cost of a wrong guess is asymmetric. Reversible edit clearly implied by the request → proceed. Destructive, outward-facing, or genuinely ambiguous scope → present the assessment first.
