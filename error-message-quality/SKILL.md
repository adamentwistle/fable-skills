---
name: error-message-quality
description: Write errors and log lines that name the failing thing, the offending value, and the likely fix — for the 3am reader. Use whenever writing a throw/raise, a log statement, a validation message, or a CLI/API error response.
---

# error-message-quality

Every error message is read at the worst possible moment by someone with no context. Write for that reader:

1. **Three parts: what failed, with what value, what to do.** `"config error: 'timeout' must be a positive integer, got '-5' in deploy.yaml"` beats `"invalid config"` by an hour of someone's debugging. Include the identifiers: which file, which record ID, which endpoint, which of the twelve retries.
2. **Never swallow the cause.** When catching and re-raising or wrapping, chain the original (`raise X from e`, `%w`, `cause`); when logging-and-continuing, log the exception with stack, not just `"error occurred"`. An except-pass block is a crime scene with the evidence removed.
3. **Match the failure to the audience:** user-facing messages say what the *user* can do ("file too large, max 10MB") and never leak internals (paths, SQL, stack traces — see security-reflex); operator-facing logs get the internals precisely so operators don't have to reproduce.
4. **Make messages greppable:** stable phrasing with the variable parts as values (`"payment declined: code=%s order=%s"`), so the on-call can search logs and code for the same string. Don't dynamically assemble the constant part.
5. **Log at the decision points you'd want during the outage:** the request that entered, the branch taken, the external call and its outcome. If a bug just cost you an hour because nothing logged the crucial value, add the log line that would have saved you — that's the cheapest reliability work there is.
6. **Right level:** errors are actionable problems; warnings are tomorrow's errors; info is narrative. Logging expected conditions as errors trains everyone to ignore errors.

Test: with only this message and no source access, could someone tell what to look at first? If not, it's missing a part.
