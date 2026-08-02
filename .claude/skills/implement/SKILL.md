---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

## Step 0 — verify the premise BEFORE writing any code

**Do this first, every time. It takes minutes and it is the only step that can save the whole build.**

A spec is a snapshot of a belief. Two things can be wrong with it by the time you build, and they
fail for different reasons:

- **It was never true.** The feature already existed when the issue was filed and nobody looked.
  Real example: a spec to add *"energy count + type requirements"* labelling, when both were already
  shipped fields on `AttackStat` — `cost` and `energyTypes` (`src/common/scouting/provider.py`,
  ADR-0032). The filing agent searched for the name it had invented, found nothing, and read that as
  confirmation.
- **It stopped being true.** `main` moved between filing and building. ADR-0093 opens with *"Every
  measurement in Issue #228's body is stale"* — four claims did not survive re-measurement, one was
  flatly false, and one outcome the issue *recorded no possibility of* actually occurred. Issue
  #294's scope item 2 demanded a wave ruling because a fix "moves every forced discard in the
  corpus"; it moved **zero**.

So, before any edit:

1. **Restate the spec's central factual claim in one sentence** — the thing that must be true for
   this work to be worth doing. Usually of the form *X does not exist*, *only these N call sites do
   Y*, *nothing handles Z*.
2. **Verify it against `HEAD`.** If the issue carries a `## Prior art` section
   (`docs/agents/issue-tracker.md` requires one for any gap claim), rerun those queries — they are
   written to be rerunnable. If it does not, run them yourself: **search by behaviour or data, never
   by the spec's proposed feature name**, and check `docs/adr/README.md`, `CONTEXT-MAP.md` and
   `docs/adr/0065-glossary.md` before grepping. A grep for an invented label returns nothing whether
   or not the capability exists.
3. **A negative result needs a positive control.** Before accepting "it isn't there", point the same
   query at something that MUST match. If that stays quiet, your instrument is broken, not the
   codebase — and **file existence is never evidence of file content**: if the claim is about what is
   *inside* a module, open it and quote it.
4. **Report the outcome in one line before proceeding**, then act on it:
   - *holds* → build;
   - *already built* → **stop**, say what it is and where, and propose closing the issue rather than
     building it;
   - *refuted or materially stale* → **stop and say so**, with the measurement. Do not quietly
     rescope around it. On Issue #294 this retired a wave ruling that was never owed.

This duplicates the filing-time check on purpose. Either can be skipped, and they catch different
things: filing-time catches *already built*, build-time also catches *decayed since*.

Stay hands-off: the spec is the source of truth **for decisions** — what was agreed, why, which
option won. It is **not** authoritative about facts of the codebase; the tree is, and step 0 is where
they get reconciled. Resolve ambiguity from it, the codebase,
`CONTEXT.md`/ADRs, and the source-of-truth docs (`docs/rules.md`, `src/cg/api.py`, card data) rather
than interrupting. But when a decision genuinely isn't settled by any of those and would change what
gets built, **ask** — don't guess and build the wrong thing.

When you must ask, use the **same format as `grill-with-docs`**: plain chat text (never the
`AskUserQuestion` picker UI), one question at a time, your recommended answer as option 1 *(recommended)*,
each option explained in both plain English and technical terms, plus the reasoning for your
recommendation. Then wait — expect clarifying questions back before the developer decides.

## Respond via `/caveman`

Route your chat prose — status updates, hand-offs, the running narration of what you're doing and
why — through the `/caveman` skill: terse fragments, no fluff, facts stated plainly. The dual
plain-English + technical explanation of each option in the question protocol above is the one
carve-out — it stays written out in full, exactly as `grill-with-docs` specifies, since that's what
makes the option legible to the developer in the first place.

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

Once the full test suite passes, /code-review is clean, and the work is committed, invoke the
`open-pr` skill automatically — don't wait to be asked — **but only if there are no pending
questions**: nothing asked via the plain-chat format above is still awaiting an answer, and no
ambiguity was punted rather than resolved. If a question is still open, stop and wait for the
answer instead of opening a PR around unresolved decisions.

If the work doesn't trace to a branch that's meant to become a PR (e.g. you're already iterating on
an existing open PR), skip this section — commit and hand off as usual.
