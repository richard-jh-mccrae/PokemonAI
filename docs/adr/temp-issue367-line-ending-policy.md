# ADR-TEMP-367 - Committed line-ending policy

**Status:** Accepted for Issue #367. Draft ADR; `/open-pr` assigns the final number.

## Context

The repo had no committed `.gitattributes`, while Windows and Linux are both first-class code
targets. `git ls-files '*.gitattributes'` was empty, `git config core.autocrlf` returned `false`,
and `git config core.eol` was unset. Positive control: the same `git ls-files` instrument found
`.gitignore` and `.github/workflows/ci.yml`.

That left line endings as a per-writer accident. Issue #367 records two paid incidents around
`tests/strategy/test_planner.py`, including a whole-file rebase conflict caused by a semantic patch
being replayed across a CRLF/LF flip.

## Decision

Choose Issue #367 option 1: add `.gitattributes` with `* text=auto`, force Python source to LF, and
explicitly exempt byte-stable data stores and `src/cg/`.

Reject option 2 for this build: do not run `git add --renormalize`. It would remove the immediate
hazard from existing eligible CRLF Python files, but it would also create the exact large mechanical
diff and open-branch conflict window this issue is trying to stop. Existing files normalize only
when a later semantic edit touches them.

Reject option 3: do not accept recurrence. The issue records multiple prior costs, and a small
committed policy prevents new `.py` files from entering with platform-dependent blobs.

## Policy

- `* text=auto` gives the repo a default check-in policy for new text files.
- `*.py text eol=lf` and `*.pyi text eol=lf` make source blobs and checkouts stable on Windows and
  Linux.
- `data/** -text !eol` preserves committed ruling/data stores byte-for-byte.
- `src/cg/** -text !eol` keeps the native-engine wrapper untouched, including its Python shim files.
- Binary extensions are marked `binary`.

## Verification

`tests/test_line_endings_policy.py` is the guard. It checks the effective Git attributes, then
creates two temporary repositories using this `.gitattributes`: one writes a Python file with CRLF,
the other with LF. Both commit the same `probe.py` blob.

The build also verifies `git diff --stat -- data src/cg` stays empty, so neither committed data
stores nor the native wrapper move in this change.
