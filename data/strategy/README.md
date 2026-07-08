# data/strategy — Strategy Digests

Committed **Strategy Digests** produced by the [`strategy-ingest`](../../.claude/skills/strategy-ingest/SKILL.md)
skill: `<handle>_<slug>_strategy.md`, one per external human-authored source (paid note.com articles now;
video transcripts next).

A Digest is an **English distillation** (not a translation) of one source, sorted into three
Actionability Buckets — **Agent-Doctrine** (grill-fodder → Pilot Hypotheses / Matchup Briefs), **Process**
(our training/gauntlet workflow), **Out-of-Scope** (human advice) — with each Agent-Doctrine entry
scope-tagged and pointed at its downstream Target Home. It is the **input** to a later grill, never a
weight change itself.

- **Raw source text is never committed.** It lives locally under `data/strategy/raw/` (gitignored) — it's
  paid, copyrighted content. Only the transformative Digest is committed.
- **Downstream:** `general` entries → general-strategy authoring; `opponent:<archetype>` → `/matchup-genie`;
  `our-deck:<deck>` → `/deck-genie` / `/deck-align`.

Glossary: [.claude/skills/strategy-ingest/CONTEXT.md](../../.claude/skills/strategy-ingest/CONTEXT.md).
