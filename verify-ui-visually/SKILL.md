---
name: verify-ui-visually
description: Verify UI changes by rendering and looking — screenshot, browser, or running app — never by reading the markup and imagining it. Use after any change to components, styles, layouts, templates, charts, emails, or generated documents/images.
---

# verify-ui-visually

Code that compiles tells you nothing about what the user sees. "The JSX looks right" is the UI equivalent of "should work" (see verify-before-done).

1. **Render it and look at it.** Run the dev server and take a screenshot (browser tooling, `mcp__chrome-devtools__take_screenshot`, or the project's snapshot setup), open the generated PDF/image/email HTML. Reading the diff is not seeing the output.
2. **Look at the actual pixels critically:** overflow and truncation, misalignment, spacing collapse, z-index sandwiches, contrast, the loading and empty states — the bugs that no test asserts and every user notices instantly.
3. **Check the states, not just the happy render:** empty (zero items), loaded (typical), overloaded (long strings, many items — "WWWWWWWW" and a 200-char title), error, and loading. Most layout breaks live in empty and overloaded.
4. **Check both themes and at least two widths** when the project supports them: light/dark, mobile/desktop breakpoint. A change verified only in dark-mode desktop ships broken for half the users.
5. **Interact, don't just render:** click the button you changed, submit the form, tab through for focus order. Console errors during the interaction count as failures even when the screen looks fine (see read-what-came-back).
6. **When you can't render** (no display, missing env), say so explicitly in the report and downgrade the claim: "markup changed as requested; not visually verified — needs a look at /settings in the browser."

Rule: a UI change reported as done carries either a screenshot-verified claim or a stated inability to verify. Never the silent middle.
