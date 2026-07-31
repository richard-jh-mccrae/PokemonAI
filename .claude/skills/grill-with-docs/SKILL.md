---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

Run a `/grilling` session, using the `/domain-modeling` skill, to interrogate the plan/issue until
we reach a shared understanding — capturing glossary terms and ADRs as they crystallise.

## How to ask (interaction protocol — overrides defaults)

**Ask in plain chat text. Do NOT use the multiple-choice question UI (the `AskUserQuestion`
tool).** This is a live conversation, not a form — the developer will often reply with clarifying
questions of their own before answering, and the picker UI can't hold that exchange.

**One question at a time.** Ask a single question, then stop and wait for the reply. Never batch
questions — a wall of questions is bewildering and breaks the thread.

For **each** question, structure it like this, in ordinary markdown:

1. **The question** — one sharp decision, stated plainly.
2. **Options, recommended one first.** Present the candidate answers as a short list with your
   **recommendation as option 1**, clearly marked *(recommended)*. Include the realistic
   alternatives after it so the developer sees the trade-off, not just your pick.
3. **Explain each option twice:**
   - *In plain English* — what it means for someone who isn't deep in the code.
   - *Technically* — the concrete mechanism, types, files, or engine behaviour involved.
4. **Your reasoning** — a sentence or two on *why* option 1 is your recommendation: what it
   optimises for, what it gives up, and what about this repo/issue makes it the right call. Pick
   option 1 by the criteria below, not by convenience.
5. **A one-line call-to-action**, always the last line of the question: **"Reply `option 1` to
   accept the recommendation, or tell me which option / what instead."** Claude Code has no
   mechanism to pre-fill the developer's input box — there is no hook, tool, or SDK feature for
   it — so this explicit line is the closest substitute: it turns "accept the recommendation"
   into a one-word reply instead of the developer having to reconstruct it.

## Respond via `/caveman`

Route your chat prose around the questions — the setup, the reasoning line, the wrap-up between
one answer and the next question — through the `/caveman` skill: terse fragments, no fluff, facts
stated plainly. The one carve-out is step 3 above, **"Explain each option twice"**: the *plain
English* translation and the *technical* explanation both stay written out in full sentences,
exactly as specified — that dual explanation is the whole point of the format, not filler to be
trimmed.

## What "recommended" means (ranking criteria — not negotiable)

**The recommended option is always the most sound, modular, best-practice option available** — the
one that is most robust, complete and comprehensive from a *performance*, *architectural* and
*verifiable* standpoint. Rank the candidates in this order:

1. **Correctness & robustness** — handles the real cases, the edge cases, and the failure modes;
   doesn't quietly break under load, bad input, or the next feature.
2. **Architectural soundness & modularity** — right seams, right layer, clear ownership, narrow
   interfaces, no leakage of one context's concerns into another; extends the existing design
   language (`CONTEXT.md`, ADRs) rather than bolting on beside it.
3. **Verifiability** — the design can be tested at its seams, asserted on, and gated in CI; state
   and behaviour are observable rather than inferred.
4. **Completeness** — solves the whole problem the issue names, not a slice of it that leaves a
   known gap behind.
5. **Performance** — appropriate algorithmic and runtime cost for how hot the path actually is.

**Never recommend an option merely because it is the smallest change, the least disruptive, the
fastest to ship, or has the least blast radius.** Low blast radius is *not* a virtue in the ranking
— it is at most a tiebreak between options that are already equal on 1–5. A narrower change that
duplicates logic, bypasses a seam, hardcodes what should be data, skips a test hook, or defers the
real fix is the *worse* option and must be presented as such, however small it looks.

Say the cost of the recommendation out loud — more files touched, a migration, a refactor first, a
longer build — and let the developer decide to trade it away. Do not pre-emptively trade it away for
them by demoting the sound option to "alternative". If the correct option requires groundwork
(extracting a seam, an ADR, a schema change) that groundwork is *part of* the recommendation, not a
reason to avoid it.

Then **wait**. Expect the developer to ask follow-ups before deciding — answer those directly (look
the facts up; see below), and only once they've decided do you record the decision and move to the
next question.

## What to look up vs. what to ask

If a *fact* can be settled from the environment — the filesystem, `CONTEXT.md`/`CONTEXT-MAP.md`, the
ADRs, `docs/rules.md` / `docs/rulebook.txt`, `src/cg/api.py` enums, card data, tools — **look it up
and state it**, don't ask the developer to recall it. Per `CLAUDE.md`, verify rules and card facts
at source, never from memory. The *decisions*, though, are the developer's: put each one to them and
wait for their answer. Do not act on the plan until they confirm a shared understanding is reached.

## What to ask vs. what to just decide (side issues)

The test is **margin, not stakes**: would a competent reviewer look at option 1 vs. the runner-up
under the §"What 'recommended' means" ranking and see a clear, obvious winner — or a real
trade-off worth someone's input? Blast radius and reversibility do NOT decide this on their own; a
low-blast-radius, easily-reversible choice can still be genuinely contested (ask), and a
hard-to-reverse choice can still have an obvious best answer (just decide).

**Ask:** option 1 beats the alternatives by judgment call, taste, or a trade-off a reviewer could
reasonably weigh differently — the ranking criteria narrow it down but don't fully settle it.

**Just decide (state it, don't wait):** option 1 is the obvious, undisputed best option — nothing
else is a serious contender once the ranking criteria are applied, or an existing ADR /
`CONTEXT.md` entry / `CLAUDE.md` convention already dictates it.

When a side issue clears the "just decide" bar: state the decision and a one-line reason in the
same terse `/caveman` prose used between questions, then keep moving — do not phrase it as a
question, do not wait for a reply, do not use the numbered question format above. Record it (see
end-of-session summary below) so the developer still sees it, just not as a stop-and-answer.

When genuinely unsure which bucket a decision falls in, ask — the cost of one extra question is
lower than silently deciding something that turns out to matter. This is a bias toward fewer
*trivial* questions, not toward fewer questions overall.

## End-of-session summary

When the grill concludes (shared understanding reached, before advancing the issue's status chip),
give a brief summary of every decision made in the session — both the ones the developer answered
and the ones auto-decided under "just decide" above. Keep it a scannable list: one line per
decision, decision + one-line reason, grouped or ordered however the grill unfolded. Flag the
auto-decided ones distinctly (e.g. a marker like *(auto)*) so the developer can spot-check them at
a glance and object before `/to-spec` runs.

## Capture as you go

Use `/domain-modeling` inline: the moment a term is pinned down, write it to the relevant
`CONTEXT.md`; when a hard-to-reverse, non-obvious, genuinely-traded-off decision is made, offer an
ADR in `docs/adr/`. Don't batch these to the end — capture them as they resolve.

### New ADRs get a temp name, not a number (until PR time)

`docs/adr/README.md`'s collision log records the same failure eight times over: a number claimed at
grill time is only a claim, and a long-lived branch reliably collides with some other branch's ADR
at merge — forcing a renumber (sometimes twice) and a scramble to fix every cross-reference. Don't
claim a number at grill time at all:

- **Filename**: `docs/adr/temp-issue<N>-<slug>.md`, where `<N>` is the originating issue number and
  `<slug>` is exactly the kebab-case title slug `ADR-FORMAT.md` would otherwise use for the final
  file. Skip `ADR-FORMAT.md`'s "scan for the highest number" step entirely — issue numbers are
  already unique, so a temp name can never collide with another branch's temp ADR.
- **Title / self-reference**: use the tag `ADR-TEMP-<N>` everywhere the real `ADR-0NNN` number would
  otherwise appear — the H1 title inside the file, and any cross-reference from another ADR or
  `CONTEXT.md` written later in this same session. `ADR-TEMP-<N>` greps unambiguously and can't be
  mistaken for a real ADR number.
- **Don't touch `docs/adr/README.md` yet** — no Index row, no move of the "Next free number"
  pointer. Both are only meaningful once a real number is assigned, which happens once, late,
  during `/open-pr`'s rebase-onto-`main` step (see that skill) — right before the branch is pushed
  and the PR opened, which is the last, truest moment to know what the next free number actually is.

If a grill produces more than one ADR, give each its own issue-scoped temp name as usual (they share
`<N>` but keep distinct slugs) — finalization assigns them consecutive real numbers in the order
they were authored.

When the grill is done — shared understanding reached, decisions locked — advance the issue's status
chip from `status:1-grilling` to `status:2-spec` (grilling complete; see
`docs/agents/issue-tracker.md`), then hand off to `/to-spec`.
