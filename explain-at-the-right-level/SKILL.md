---
name: explain-at-the-right-level
description: Answer "how does X work" or "why does this happen" at the asker's level — grounded in their actual code, one runnable example, no jargon walls. Use for explanatory questions: "how does X work", "why does this happen", "what's the difference between", "walk me through", "explain this error", "what does this code do", or when a reviewer asks you to justify a change. Not for requests to change code.
---

# explain-at-the-right-level

Weak explanations are correct textbook chapters: generic, jargon-dense, and answered in paragraph four. Strong explanations answer in the first sentence, point at the reader's own code, and show one real example with real output.

1. **Read before explaining.** Open the actual function, config, or call path the question is about before writing a word. Explain what *this* code does, with `path:line` citations, not what code like it usually does. If the behavior lives somewhere you can't read (a library internal, a runtime), say what you inferred versus what you read.
2. **Answer first, in one or two sentences**, then the mechanism, then the example. Never make the reader wait for the answer.
3. **Ground it in their code.** "In your `retry_fetch` at `client.py:88`, the backoff doubles here" beats an abstract backoff lecture. Walk the concrete path their input takes through their code.
4. **Calibrate to the demonstrated level.** Their vocabulary, code, and question tell you what they know. Don't define promises for someone debugging race conditions; don't say "covariant type parameters" to someone asking what generics are. Reuse their terms; when you introduce a term they didn't use, define it in the same sentence.
5. **One concrete runnable example.** Show the smallest snippet that demonstrates the behavior, with its output. Run it when you can and paste the real output; if you can't run it, label the output as expected, not observed. For "what's the difference" questions: same input through both, outputs side by side.
6. **Bound the claim.** "This holds for CPython; PyPy differs", "true since ES2017", "only when `strict` is on". Silent version- or config-specificity becomes a bug in the reader's head later. If you're unsure, check before teaching, or say you're unsure; teaching a guess as fact is the worst outcome.
7. **Stop when it's answered.** Don't append everything else you know. Offer depth in one line ("want the event-loop details?") instead of imposing it. Don't turn an explanation into a code change unless asked (see question-vs-task).

Test: could they act on the explanation immediately, without a follow-up clarification and without re-reading it?
