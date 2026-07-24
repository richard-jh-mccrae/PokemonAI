---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the current branch.

If this work traces to a tracked issue, once the full test suite passes and review is clean, advance that issue's status chip from `status:3-build` to `status:4-done` and close it (`state_reason: completed`). See `docs/agents/issue-tracker.md`.
