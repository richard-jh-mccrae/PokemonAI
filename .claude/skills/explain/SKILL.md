---
name: explain
description: Explain an issue, PR, concept, or piece of code in plain English, then answer follow-up questions in a relaxed back-and-forth. Phone-friendly — plain chat text, no files, no workspace. Use when the user says "explain <thing>", "what is this issue about", "help me understand X", or invokes /explain.
disable-model-invocation: true
argument-hint: "What should I explain? (an issue number, a PR, a file, a concept — or leave blank for the thing we're on)"
---

The user wants something explained in plain English, then wants to ask questions back and forth.
Optimised for reading and replying on a **phone**: this is a chat, not a document. `/teach` builds
an HTML lesson workspace — the opposite of what's wanted here. Produce **no files, no artifacts, no
workspace**. Everything lives in the chat.

## What to explain

The argument (or the current context) names the subject. Figure out which it is:

- **A GitHub issue / PR** — a number like `42`, `#42`, or a phrase like "the issue at hand", "this
  PR". Fetch it via the GitHub MCP tools (`mcp__github__issue_read`, `mcp__github__pull_request_read`)
  on `richard-jh-mccrae/PokemonAI`. Read the body and the discussion, not just the title. Once you
  know which it is, refer to it as **Issue #42** or **PR #42** in your explanation, never a bare
  `#42` (per `CLAUDE.md`).
- **A file, function, or bit of code** — read it before explaining it.
- **A concept, rule, or card mechanic** — a Pokémon TCG rule, a strategy term, an ADR, part of the
  pipeline.
- **Nothing named** — explain whatever we're currently looking at. If it's genuinely unclear what
  "the issue at hand" is, ask one short question to pin it down.

## Verify at source — do not explain from memory

This repo's cardinal rule (`CLAUDE.md`) applies with full force here: **never explain a game rule or
card fact from training knowledge.** A confident wrong explanation is worse than no explanation.

- Game rules → read `docs/rules.md` (then `docs/rulebook.txt` for anything not digested).
- Card data → `data/EN_Card_Data.csv`.
- Anything about the code → read the actual file.

Ground the explanation in what you just read, and it's fine to say where it came from ("per
`docs/rules.md`…") so the user can double-check.

## How to explain (mobile-first)

- **Plain English first.** Lead with the gist in a sentence or two — what this *is* and why it
  matters — before any detail. Assume the user is on a small screen skimming.
- **Short.** A few short paragraphs or a tight bullet list. No walls of text, no long tables, no big
  code dumps. Quote only the few lines that matter.
- **No jargon unlabelled.** If a term is unavoidable, define it in the same breath.
- **Plain chat text only.** Do NOT use the `AskUserQuestion` multiple-choice UI — this is a live
  conversation. When you need to check something, just ask in one plain sentence and wait.
- **Structure for a thumb.** If the thing has parts (a problem, a proposed fix, open questions), a
  couple of short labelled bullets beats a paragraph.

## Then hand the conversation back

End the first explanation by inviting questions — briefly, e.g. *"Ask me anything about it — want me
to go deeper on any part?"* Then **stop and wait.**

This is stateful within the chat but stateless on disk. Stay in the topic across turns:

- Answer each follow-up at the same altitude — plain, short, verified at source.
- If a question needs a fact you haven't confirmed, go read it before answering. Don't guess to keep
  the conversation flowing.
- Offer to zoom in or out ("that's the summary — want the detailed version?"), and to move on to a
  related piece when the user's done.
- The user may pivot the subject mid-thread. Follow the pivot; re-anchor on the new thing.

Only take an action beyond explaining (edit code, comment on an issue, open a PR) if the user
explicitly asks. By default `/explain` just talks.
