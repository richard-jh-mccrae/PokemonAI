---
name: open-pr
description: Open or update a pull request in this repo — rebase onto main first, push, create/update the PR from the repo's template, then arm a 5-minute CI check-in cadence that auto-fixes red CI (merge conflicts or failed tests) and stops itself once CI goes green. Use whenever the user asks to open, create, make, submit, or update a PR, or when /implement finishes a build with no pending questions.
---

Open or update a pull request for the current branch.

## 1. Rebase onto `main` first

Every time — not just the first PR for a branch. Fetch and rebase the branch onto the latest
`main`, resolving any conflicts that surface, before pushing. Do not push straight from a stale
base.

## 2. Push

`git push -u origin <branch-name>`.

## 3. Create or update the PR

Use `.github/pull_request_template.md` as the body layout:

- **Title** always states the issue number when this work traces to a tracked issue, e.g.
  `Issue #145: short description`.
- **Body**: a brief human-readable **Summary** (what/why/how) followed by a **Technical details**
  section written in caveman mode (terse fragments, no fluff — files/functions touched, edge
  cases, tests).

Use the GitHub MCP tools (`mcp__github__create_pull_request`) or `gh pr create`, whichever this
session has available.

## 4. Auto-subscribe, 5-minute check-in cadence

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
