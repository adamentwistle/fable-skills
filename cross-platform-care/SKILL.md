---
name: cross-platform-care
description: Write scripts and file handling that survive the machine they didn't develop on — path separators, shell dialects, line endings, case-sensitivity, missing tools. Use when writing shell scripts, CI steps, path manipulation, file I/O, or install/setup instructions others will run.
---

# cross-platform-care

"Works on my machine" is an environment assumption you didn't notice making (see environment-first — this is its prevention side).

1. **Build paths with the path library**, never string concatenation with `/` or `\`: `os.path.join`/`pathlib`, `path.join`, `filepath.Join`. Same for home (`~` doesn't expand everywhere), temp dirs (use the platform API — or the session's designated scratchpad), and current-dir assumptions (prefer absolute paths derived from a known root).
2. **Know which shell your script actually targets.** Bashisms (`[[`, arrays, `set -o pipefail`) fail in POSIX `sh`; zsh and bash differ on word splitting and globs; CI images may have `dash` as `/bin/sh`. Declare the shebang you mean and test with that shell.
3. **Quote every variable expansion in shell** (`"$var"`, `"$@"`): unquoted expansion breaks on the first path with a space — which is every macOS user directory. Filenames can contain spaces, quotes, unicode, and leading dashes; `--` before positional args guards the last one.
4. **Case-sensitivity is a filesystem property:** macOS is usually case-insensitive (so `import utils` finds `Utils.py` locally and dies on Linux CI); imports, includes, and asset references must match the file's real casing exactly.
5. **Line endings and encodings:** CRLF from Windows checkouts breaks shebangs and string comparisons; declare encoding explicitly when reading text (`utf-8`), don't inherit the platform default.
6. **Don't assume tools exist or match:** GNU vs BSD flags differ (`sed -i`, `date -d` vs `-v`, `grep -P`); check availability or use the portable subset. Version-check anything whose behavior you depend on.
7. **Timezones on servers are UTC; laptops aren't.** Code that depends on local time behaves differently in CI/production — be explicit about which zone every timestamp is in (see edge-case-sweep).

Test: "would this run on a fresh Linux CI container and on a macOS laptop with a space in the username?" Both, or state which one it targets.
