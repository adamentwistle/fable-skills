---
name: api-surface-care
description: Treat any change to a public or shared interface — exported functions, HTTP endpoints, CLI flags, config formats, event/message schemas, DB schemas — as a contract change with consumers you can't see. Use before modifying anything other code depends on.
---

# api-surface-care

Private code has one consumer: the repo. Public surface has consumers you can't grep. Before changing one:

1. **Know which surface you're on.** Exported from the package, reachable over HTTP, parsed from a config file, stored in a DB, emitted onto a queue → contract. Renaming an internal helper is free; renaming a JSON field is a breaking change for every client.
2. **Grep every in-repo caller** of the thing you're changing — and remember external consumers don't show up in grep. For libraries, published CLIs, and APIs, assume unseen callers exist.
3. **Prefer additive evolution:** new optional parameter with a default, new field, new endpoint version. Widening what you accept and narrowing what you emit is safe; the reverse breaks people.
4. **Breaking changes need a path, not just a diff:** deprecate with a warning first where the ecosystem supports it, or version the surface (v2 endpoint, config `version:` key). Document the migration in the same change.
5. **Watch the semantic breaks that look additive:** changing a default value, tightening validation on previously-accepted input, reordering enum values something serializes by index, changing error types/codes callers match on.
6. **Serialization is forever.** Anything persisted (DB rows, cached blobs, queued messages) written in the old shape will be read by the new code — handle both shapes or migrate the data (see the migration checklist if one exists).

Exit check: "could code I cannot see be depending on the exact behavior I just changed?" If yes, the change needs a compatibility story, and the report must call it out.
