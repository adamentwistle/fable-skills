---
name: dependency-changes
description: Adding/upgrading/removing dependencies — justification bar, changelog + pinned-constraint archaeology, matching package-manager/lockfile hygiene, one bump at a time, gates after. Use before touching package manifests, on security advisories, or version-mismatch errors.
---

# Dependency Changes

Every dependency is a standing liability: supply-chain surface, upgrade treadmill, bundle weight, and a second opinion about how your code should work. Changes to the dependency set deserve more ceremony than code changes, not less.

## Adding a dependency

1. **Clear the justification bar first**: Does the stdlib do it? Does an existing dependency do it (grep package.json — the codebase often already carries a lib covering 90%)? Is it small enough to write inline (a 20-line util beats a package)? Only then add.
2. **Vet it**: maintenance signal (recent releases, open-issue triage), weekly downloads, license compatibility, install footprint (`npm info <pkg>`, transitive count). A package that pulls 40 transitive deps for one function is a bad trade.
3. **Use the project's package manager exactly** — check for `pnpm-lock.yaml` / `yarn.lock` / `package-lock.json` and use the matching tool. Never generate a second lockfile kind; never hand-edit a lockfile. Respect workspace/catalog conventions in monorepos.
4. Pin ranges the way the project already pins them (look at neighbors in package.json) — don't introduce `^` into a repo that pins exact, or vice versa.

## Upgrading

1. **Read the changelog/release notes between your version and the target** — specifically BREAKING sections and migration guides. For a major bump, expect API changes; budget for them rather than discovering them via type errors.
2. **Check the project for pinned-constraint reasons before bumping.** A dependency held at an old major is often deliberate (compatibility with a sibling app, a plugin ecosystem, a known regression). Search CLAUDE.md/README/comments/git log for the package name — "upgrade everything" is not authorization to break a documented pin.
3. Upgrade one thing at a time (or one tightly-coupled group, e.g. a framework and its plugins). A 15-package bump that breaks the build is unbisectable.
4. Security advisories: prefer the smallest version delta that clears the advisory; verify the vulnerable path is actually reachable in your usage when deciding urgency.

## After ANY dependency change

- Full install with the project's tool, then the full gate suite: build/typecheck, lint, tests.
- Exercise the features that use the changed package at runtime — type-compatible ≠ behavior-compatible (defaults change, peer behaviors shift).
- Diff the lockfile at a glance: the change should touch what you expect. A one-package bump that rewrites 500 lockfile lines deserves a look before committing.
- Commit lockfile + manifest together, and (unless asked otherwise) separately from feature code.

## Removing

Grep for every import/require/config reference (plugins and configs reference packages by STRING — check rc files, build configs, CI). Remove, reinstall, run gates. Dead dependencies are worth removing when noticed — but as their own commit, not smuggled into a feature diff.

## Red flags to surface rather than push through

Typosquat-adjacent names, install scripts doing surprising work, a needed upgrade that forces a cascade (node version, framework major), or a license change mid-stream. These are decisions for the user, with your recommendation attached.
