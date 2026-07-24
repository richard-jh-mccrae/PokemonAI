---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Stay hands-off: the spec is the source of truth, so resolve ambiguity from it, the codebase,
`CONTEXT.md`/ADRs, and the source-of-truth docs (`docs/rules.md`, `src/cg/api.py`, card data) rather
than interrupting. But when a decision genuinely isn't settled by any of those and would change what
gets built, **ask** — don't guess and build the wrong thing.

When you must ask, use the **same format as `grill-with-docs`**: plain chat text (never the
`AskUserQuestion` picker UI), one question at a time, your recommended answer as option 1 *(recommended)*,
each option explained in both plain English and technical terms, plus the reasoning for your
recommendation. Then wait — expect clarifying questions back before the developer decides.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the current branch.

If this work traces to a tracked issue, once the full test suite passes and review is clean, advance that issue's status chip from `status:3-build` to `status:4-done` and close it (`state_reason: completed`). See `docs/agents/issue-tracker.md`.
