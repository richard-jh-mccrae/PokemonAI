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
   optimises for, what it gives up, and what about this repo/issue makes it the right call.

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
