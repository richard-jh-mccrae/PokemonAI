---
name: open-pr
description: Open or update a pull request in this repo — rebase onto main first, finalize any temp-named ADRs to their real numbers, push, create/update the PR from the repo's template, then arm a 5-minute CI check-in cadence that auto-fixes red CI (merge conflicts or failed tests) and stops itself once CI goes green. Use whenever the user asks to open, create, make, submit, or update a PR, or when /implement finishes a build with no pending questions.
---

Open or update a pull request for the current branch.

## 1. Rebase onto `main` first

Every time — not just the first PR for a branch. Fetch and rebase the branch onto the latest
`main`, resolving any conflicts that surface, before pushing. Do not push straight from a stale
base.

## 2. Finalize any temp-named ADRs

`/grill-with-docs` authors new ADRs as `docs/adr/temp-issue<N>-<slug>.md`, tagged `ADR-TEMP-<N>` in
prose, so they can't collide with another branch's ADR before merge (see that skill and
`docs/adr/README.md`). Right now — freshly rebased onto `main`, immediately before pushing — is the
truest moment to know the real next-free number, so assign it here:

1. **Find them**: `git status`/`git diff --name-only origin/main...HEAD` for
   `docs/adr/temp-issue*.md` added on this branch. If there are none, skip this step entirely.
2. **Compute the real number(s)**: scan `docs/adr/` on the now-rebased branch for the highest
   `NNNN-*.md` prefix and increment by one (cross-check against `docs/adr/README.md`'s "Next free
   number" line, but the disk scan is the ground truth — the pointer has been wrong before). If more
   than one temp ADR landed on this branch, assign consecutive numbers in authoring order.
3. **Rename**: `git mv docs/adr/temp-issue<N>-<slug>.md docs/adr/<NNNN>-<slug>.md` — the slug is
   untouched, only the prefix changes.
4. **Rewrite references**: `grep -rl 'ADR-TEMP-<N>'` across the repo (the file's own H1, any other
   ADR or `CONTEXT.md` that cross-referenced it mid-session) and replace with `ADR-<NNNN>`.
5. **Strip the temp-name banner** from each renamed file — the line
   `⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.`
   plus its blank line. It is written by `/grill-with-docs` and is FALSE the moment step 3 runs;
   left in place it tells every later reader to cite the issue instead of the number it now has.
   This step was missing until 2026-08-01 and ADR-0087, ADR-0090 and six others shipped carrying it.
6. **Update `docs/adr/README.md`**: add the Index row, and move the "Next free number" pointer past
   the number(s) just assigned. **Both, not either** — `tests/test_adr_index.py` fails on an ADR
   with no row, on a row whose link 404s or names a different number, and on a pointer that is not
   actually free.
7. **Commit** this as its own mechanical commit (e.g. `Finalize ADR-0NNN numbering (was
   ADR-TEMP-<N>)`), separate from the feature commits.
8. **Verify**: `python -m pytest tests/test_adr_index.py -q`. It also fails on a **duplicate number
   prefix**, which is the one failure mode nothing used to catch — ADR-0073 was claimed by two
   ADRs that merged eleven hours apart and the duplicate sat undetected for five days.

Residual race: another branch can still merge the same number between your rebase and your push —
now rare instead of routine. If push/CI reveals that collision, follow the existing convention in
`docs/adr/README.md`'s collision log (first-merged keeps the number, this branch renumbers again)
and repeat steps 2–8. **A number claimed by an open PR is taken**, even though it is not on `main`
yet and a disk scan will not see it — check the open PRs before settling on a number, and skip past
anything in flight rather than picking a number you already know will collide.

## 3. Push

`git push -u origin <branch-name>`.

## 4. Create or update the PR

Use `.github/pull_request_template.md` as the body layout:

- **Title** always states the issue number when this work traces to a tracked issue, e.g.
  `Issue #145: short description`.
- **Body**: a brief human-readable **Summary** (what/why/how) followed by a **Technical details**
  section written in caveman mode (terse fragments, no fluff — files/functions touched, edge
  cases, tests).

Use the GitHub MCP tools (`mcp__github__create_pull_request`) or `gh pr create`, whichever this
session has available.

## 5. Auto-subscribe, 5-minute check-in cadence

As soon as the PR is opened, call `subscribe_pr_activity` immediately — don't ask first. Use
`send_later` for the self check-in fallback at a 5-minute cadence instead of the default ~1 hour.
On each firing, check CI status:

- **CI red:** pull in the failure details (merge conflicts or failed tests) and fix them, push the
  fix, then re-arm `send_later` for another 5-minute check-in.
- **CI green:** report it as green and ready to merge, then **stop** re-arming — no further
  5-minute check-ins for that PR.

The four monitoring tool calls this relies on (`subscribe_pr_activity`, `unsubscribe_pr_activity`,
`send_later`, `delete_trigger`) are allowlisted in `.claude/settings.json` so this runs without a
manual approval prompt each time.

If those tools aren't available in the current session (e.g. no `Claude_Code_Remote` MCP
connection), fall back to `CronCreate` with the same every-5-minutes cadence and the same
red/green branching logic, and say so — note the fallback's limits (session-only, dies if the
session ends, auto-expires after 7 days).
