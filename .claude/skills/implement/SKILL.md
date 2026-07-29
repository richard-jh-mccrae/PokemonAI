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

## Build the sound option, not the small one

Whether you're recommending an option or silently resolving an ambiguity yourself, apply
`grill-with-docs`'s **"What 'recommended' means"** ranking: correctness & robustness →
architectural soundness & modularity → verifiability → completeness → performance. The default is
always the most sound, modular, best-practice implementation available.

**Never pick an approach because it is the smallest diff, touches the fewest files, or has the least
blast radius.** That is a tiebreak between otherwise-equal options, never a reason on its own. In
particular, do not:

- duplicate logic to avoid touching a shared module — extract or extend the shared module;
- special-case at the call site what belongs behind the seam;
- hardcode what the design says should be data/config;
- skip a test seam because the code "works" without one;
- leave a known gap the spec covers and call it out as follow-up.

If doing it properly needs groundwork first — extracting a seam, a small refactor, a schema or
interface change, a new ADR — do that groundwork as part of the work. If the groundwork is large
enough that it changes the shape of the job, say so and ask (in the format above) rather than
shipping the shortcut. Flag any cost you incur (files touched, refactor, migration) in the commit
message and the hand-off, so the trade is visible rather than hidden.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Commit your work to the current branch.

If this work traces to a tracked issue, once the full test suite passes and review is clean, advance that issue's status chip from `status:3-build` to `status:4-done` and close it (`state_reason: completed`). See `docs/agents/issue-tracker.md`.

## Auto-open the PR when the work is actually finished

Once the full test suite passes, /code-review is clean, and the work is committed, open the pull
request automatically — don't wait to be asked — **but only if there are no pending questions**:
nothing asked via the plain-chat format above is still awaiting an answer, and no ambiguity was
punted rather than resolved. If a question is still open, stop and wait for the answer instead of
opening a PR around unresolved decisions.

Follow `CLAUDE.md`'s pull request conventions exactly:

1. **Rebase onto `main` first.** Fetch and rebase the branch onto the latest `main`, resolving any
   conflicts that surface, before pushing.
2. **Push** the branch (`git push -u origin <branch-name>`).
3. **Create the PR** with the GitHub MCP tools (`mcp__github__create_pull_request`), using
   `.github/pull_request_template.md` as the body layout: a brief human-readable **Summary**
   (what/why/how) and a **Technical details** section in caveman mode (terse fragments — files/
   functions touched, edge cases, tests). Title always states the issue number, e.g.
   `Issue #145: short description`, when this work traces to a tracked issue.
4. **Subscribe immediately.** As soon as the PR is opened, call `subscribe_pr_activity` in the same
   turn — don't ask first. Then use `send_later` to arm a self check-in **5 minutes** out (not the
   default ~1 hour), re-arming after each firing until the PR is merged or closed, per `CLAUDE.md`'s
   PR-monitoring cadence.

If the work doesn't trace to a branch that's meant to become a PR (e.g. you're already iterating on
an existing open PR), skip this section — commit and hand off as usual.
