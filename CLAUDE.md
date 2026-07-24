Codebase for the Kaggle **Pokémon TCG AI Battle Challenge — Strategy** competition. Goal: a Python agent that builds a deck and plays the Pokémon TCG (NOT Pokemon TCG Pocket mobile app) via a provided native simulator. Strategy category = the agent's decision-making/search approach is the deliverable.

## Rules & card facts: ALWAYS verify at source — never from memory

This is the Pokémon **TCG** (Scarlet & Violet rules), NOT Pokémon TCG Pocket. Card stats, evolution
lines, attacks, HP, mechanics **and the game rules** in this set differ from the mainline/real TCG and
from Pocket. Before stating, using, or reasoning about ANY rule OR card fact — strategy, blunder-busting,
meta parsing, tuning, anything — read it at the source. Never recall it from training knowledge.

- **Game rules** (turn structure, first/second-player restrictions, per-turn limits, weakness ×2,
  prizes, special conditions, win conditions, deck-building): **read `docs/rules.md` first** — the
  curated, provenance-tagged digest (engine-enforced vs reason-only; engine-source vs official-rule).
  Its primary source — and the full text for anything not digested — is the official rulebook **plus
  the competition-specific simulator deltas**: **`docs/rulebook.txt`**. ⚠️ The deltas
  OVERRIDE the official rules (e.g. a simultaneous win is a **draw**, not a tiebreaker; **Mega
  Evolution Pokémon *ex* do NOT end your turn on evolving** — opposite of the old Mega-EX). **The
  simulator's behavior is the authority** where anything conflicts. ALWAYS consult these before any
  strategy, deck-building, blunder-busting, meta-parsing, tuning, or game/card-mechanics reasoning.
- **Card data:** `data/EN_Card_Data.csv` (cols incl. stage, `evolvesFrom`/Previous-stage *name*, HP,
  weakness/resistance *type*, retreat, attacks, costs, damage). At runtime the same data comes through
  `cg.api` `all_card_data()` → `CardStat` (`src/common/scouting/provider.py`).
- **Behavioral tags:** `src/common/card_functions.json` (behavioral-only). **Engine vocabulary**
  (areas, card/energy types, special conditions, select contexts): `src/cg/api.py` enums.
- **Worked example of the trap:** the evolution line is **Riolu (Basic) → Mega Lucario ex (Stage 1)** —
  a *single* hop, with NO intermediate "Lucario" (mainline TCG has Riolu→Lucario→Mega Lucario; this set
  does not). The rulebook states it outright: "Mega Lucario ex doesn't evolve from Lucario or Lucario
  ex—just Riolu" (`docs/rulebook.txt` Appendix 1). Verify, don't recall.

## Conventions (override global standards)

- **Windows + Linux are both first-class.** Dev/build is on Windows; the Kaggle grader is
  Linux — both must work. `.github/workflows/ci.yml` runs the pytest suite + the Scouting
  coverage gate on `windows-latest` and `ubuntu-latest` (Python 3.12). The committed
  `cg/cg.dll` (Windows) and `cg/libcg.so` (Linux) let the native engine load on both, so the
  whole suite runs offline. Keep code cross-platform: `pathlib` not string paths, explicit
  `encoding="utf-8"`, no OS-only assumptions.
- **CI runs tests only.** The rest of the global CI spec (Doxygen / Sphinx / GitHub Pages /
  PDF) stays out until those toolchains exist here. Run locally: `python -m pytest tests/ -q`.
  Details: `docs/ci.md`.

## Secrets

`kaggle_api_token/` holds a real Kaggle API token (`instructions.txt`). **Never commit it or paste the token into code, configs, or chat.** A root `.gitignore` already excludes `kaggle_api_token/`, `data/meta/`, and `reports/`; the Kaggle CLI reads the token from `KAGGLE_API_TOKEN` or `%USERPROFILE%\.kaggle\access_token` (preferred for the scheduled task).

## Agent skills

External engineering skills from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT)
are vendored under `.claude/skills/` (`teach`, `wayfinder`, `to-spec`, `to-tickets`, `implement`,
`tdd`, `code-review`, `research`, `prototype`, `domain-modeling`, `grilling`,
`setup-matt-pocock-skills`). Intended flow for a GitHub issue: `/grill-with-docs` (or `/grilling`)
to lock decisions → `/to-spec` to synthesise the spec → `/implement` to build it hands-off;
`/to-tickets` chunks a large spec, `/wayfinder` handles work too big/foggy for one session.

### Issue tracker

GitHub issues on `richard-jh-mccrae/PokemonAI`, driven via the GitHub **MCP tools**
(`mcp__github__*`) — no `gh` CLI in web/mobile sessions. One `status:*` chip per issue tracks the
`grill → spec → build` pipeline (`status:1-grilling` → `2-spec` → `3-build` → `4-done`); `/to-spec`
and `/implement` advance it automatically. See `docs/agents/issue-tracker.md`.

### Domain docs

Multi-context: `CONTEXT-MAP.md` indexes per-context `CONTEXT.md` files; all ADRs live in one
system-wide `docs/adr/` series. See `docs/agents/domain.md`.
