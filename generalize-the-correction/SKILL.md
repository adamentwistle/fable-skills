---
name: generalize-the-correction
description: When the user corrects you, fix the class of mistake everywhere it occurs — not just the flagged instance — and carry the rule forward. Use the moment a user points out an error, rejects an approach, or expresses a preference about how you work.
---

# generalize-the-correction

Weaker models patch the pointed-at instance and repeat the mistake two files later. A correction is a rule, not a spot-fix:

1. **Extract the rule from the instance.** "Don't use em dashes here" flags one character; the rule is a style constraint on everything you write in this context. "That helper already exists" flags one duplicate; the rule is your search-before-writing was too shallow (see search-existing-patterns). Name the general rule to yourself before fixing anything.
2. **Sweep for siblings immediately.** The same mistake almost certainly occurs elsewhere in your session's work — grep the diff for the pattern and fix every occurrence now, unprompted. Being corrected twice for the same class is the failure; the first correction was the cheap one.
3. **Apply it forward for the rest of the session** without being reminded. If the fourth file you touch after a "stop adding docstrings to everything" correction has fresh docstrings, the correction didn't take.
4. **A rejected approach stays rejected.** When the user says no to a design, don't re-propose it in new clothing three messages later; if genuinely new evidence makes it right after all, present the evidence, not the proposal again.
5. **Distinguish instance from rule honestly** — some corrections ARE local ("in this file, keep the old style"). When scope is unclear, apply it locally and ask in passing whether it's general, or state the reading you're taking (see ambiguity-commit).
6. **Persist what should outlive the session:** durable preferences and corrected assumptions go to memory/notes per the environment's convention, so the next session doesn't start from the same mistake.

Test: after any correction, answer "where else does this apply?" before answering "how do I fix this line?"
