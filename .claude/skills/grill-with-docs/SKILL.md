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

## Capture as you go

Use `/domain-modeling` inline: the moment a term is pinned down, write it to the relevant
`CONTEXT.md`; when a hard-to-reverse, non-obvious, genuinely-traded-off decision is made, offer an
ADR in `docs/adr/`. Don't batch these to the end — capture them as they resolve.

When the grill is done — shared understanding reached, decisions locked — advance the issue's status
chip from `status:1-grilling` to `status:2-spec` (grilling complete; see
`docs/agents/issue-tracker.md`), then hand off to `/to-spec`.
