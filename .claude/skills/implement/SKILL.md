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
