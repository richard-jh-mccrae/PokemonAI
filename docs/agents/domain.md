# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the
codebase. **This repo is multi-context** and already maintains this layout — read it, don't recreate it.

## Before exploring, read these

- **`CONTEXT-MAP.md`** at the repo root — the index of contexts. It points at one `CONTEXT.md` per
  context; read each one relevant to the topic you're touching.
- The relevant **per-context `CONTEXT.md`** (e.g. `src/common/CONTEXT.md`, `tools/sim/CONTEXT.md`,
  `.claude/skills/<skill>/CONTEXT.md`) — the glossary for that context.
- **`docs/adr/`** — all architectural decisions live here as one numbered, system-wide series
  (`0001-…` … `0069-…` and up). Read the ADRs that touch the area you're about to work in; the
  `CONTEXT-MAP.md` "Relationships" section links the ADR behind each cross-context edge.

There are currently **no per-context `docs/adr/` directories** — every ADR is in the root series.
If any expected file is missing, **proceed silently**; `/domain-modeling` (reached via
`/grill-with-docs`) creates docs lazily when a term or decision actually gets resolved.

## Actual layout

```
/
├── CONTEXT-MAP.md                     ← index of all contexts + their relationships
├── CONTEXT.md                         ← Meta Tracker context (root glossary)
├── docs/adr/                          ← ALL decisions, one system-wide numbered series
│   ├── 0001-data-source.md
│   └── … 0069-…
├── src/
│   ├── common/CONTEXT.md              ← Agent Runtime (Pilot, Value Model, Scouting)
│   └── cgpy/CONTEXT.md                ← pure-Python engine twin
├── tools/
│   ├── sim/CONTEXT.md                 ← Agent Checks
│   ├── train/CONTEXT.md               ← Training
│   ├── submit/CONTEXT.md              ← Submission & Tracking
│   └── arena/CONTEXT.md               ← Arena
└── .claude/skills/
    ├── strategy-ingest/CONTEXT.md     ← Strategy Ingestion
    └── update-strategy/CONTEXT.md     ← Strategy Application
```

`CONTEXT-MAP.md` is the source of truth for which context lives where — consult it rather than this
snapshot if they ever disagree.

## Use the glossary's vocabulary

When your output names a domain concept (an issue title, a spec, a ticket, a test name), use the
term exactly as the relevant `CONTEXT.md` defines it, and honour the `_Avoid_:` synonyms it lists
(e.g. use **Episode** not "game/match", **Replay** not "log", **Meta** not "metagame"). Shared terms
(`Archetype`, `Meta`, `Rank Band`, main-line/sub-line/engine Pokémon) are defined once in the Meta
Tracker `CONTEXT.md` and reused verbatim elsewhere — don't redefine them.

If the concept you need isn't in any glossary yet, that's a signal — either you're inventing
language the project doesn't use (reconsider), or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0008 (Pilot is a layered rules pipeline) — but worth reopening because…_

The competition-specific rules in `docs/rules.md` / `docs/rulebook.txt` and the enums in
`src/cg/api.py` are authoritative for game-rule and card facts (see `CLAUDE.md`); verify at source
rather than recalling.
