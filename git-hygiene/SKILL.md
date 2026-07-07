---
name: git-hygiene
description: Keep version control state clean and deliberate — atomic commits with real messages, branch before risky work, never commit debris or secrets. Use when committing, branching, or at the start of any change large enough to want an undo point.
---

# git-hygiene

Git is the safety net and the paper trail; sloppy use degrades both.

1. **Commit only when asked** — but when you do: one logical change per commit, message stating *why* in the subject ("fix utf8 filename crash in import", not "fix bug" or "updates"). The message is written for the person running `git log` during an incident.
2. **Stage by intent, not by wildcard.** Review `git status` and `git diff` before staging; `git add -A` is how debug scripts, `.env` files, editor droppings, and 40MB fixtures end up in history. Anything untracked that you didn't deliberately create gets investigated, not committed.
3. **Secrets in a commit are compromised even if you amend** — assume pushed history is public forever; rotate the credential, don't just rewrite.
4. **Branch before risky or user-visible work**, and never commit to main/master unprompted — branch first, even for "one small fix". A branch costs nothing; un-committing from main costs a conversation.
5. **Respect existing state:** don't amend or rebase commits you didn't author this session, don't touch staged changes the user prepared, and treat stashes as someone's saved work, not clutter (see data-loss-guard).
6. **Use history as evidence:** `git log -S symbol`, `git blame`, and the message on the line you're about to change often explain the "weird" code — read it before "fixing" something a past commit did deliberately.
7. **Match the repo's conventions** — commit-message style, branch naming, changelog expectations. Grep `git log --oneline -20` to see the house style before writing yours.

Exit check before any commit: read the staged diff top to bottom (see self-review-diff) — the commit is the last cheap moment to catch what shouldn't ship.
