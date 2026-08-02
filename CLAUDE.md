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

- **Windows + Linux are both first-class *as a code requirement*.** Dev/build is on Windows;
  the Kaggle grader is Linux — both must work. The committed `cg/cg.dll` (Windows) and
  `cg/libcg.so` (Linux) let the native engine load on either, so the whole suite runs offline
  on both. Keep code cross-platform: `pathlib` not string paths, explicit `encoding="utf-8"`,
  binary-safe writes to committed data (several stores are CRLF), no OS-only assumptions.
  **CI itself runs Linux only** — `.github/workflows/ci.yml` is `os: [ubuntu-latest]`
  (Python 3.12), and that is **deliberate**, not a gap. Windows is covered by developing on
  it, so cross-platform discipline is upheld by the local run and review rather than by a
  second CI job. Widening the matrix is a one-line change (`docs/ci.md`) if that ever changes.
- **CI runs tests, plus two main-watchdog gates.** `ci.yml` is the suite; `leaf-gate-main.yml`
  runs ADR-0072's **Discrimination Gate** on every push to `main` and fails on an unruled
  `OK → MISS` leaf flip (added 2026-07-28), and `decider-gate-main.yml` runs the same ADR's
  **Decision Gate** and fails on an unruled `REGRESSION` — a frame whose DECISION moved off the
  human's ruling (added 2026-07-30, ADR-0085 Amendment J; it measured 31.6 s to the leaf gate's
  71 s, so the "too slow" objection did not survive measurement). Both are a narrow, deliberate
  widening of the old "tests only" rule, because each gate was owed on main and nothing ran it
  there. Neither **ever** re-captures its baseline (`data/leaf_lab/baseline.json`,
  `data/decider_lab/baseline.json`): a baseline is a ruling record, and auto-recapture would make
  the gate vacuous — which is not hypothetical, it is exactly how the old Decision Gate died. The
  rest of the global CI spec (Doxygen / Sphinx / GitHub Pages / PDF) stays out until those
  toolchains exist here. Run locally: `python -m pytest tests/ -q`. Details: `docs/ci.md`.
- **Reference issues and PRs by kind, never a bare number.** In prose — chat, commit messages,
  PR/issue bodies and comments, skill docs — write **Issue #145** and **PR #6**, never a bare
  `#145`/`#6` (GitHub shares one number space across issues and PRs, so a bare number is
  ambiguous about which it is). *Exception:* GitHub's own functional syntax stays bare exactly as
  GitHub requires it to work — closing keywords (`Closes #45`, `Fixes #45`), inline autolinks, and
  data-field values (e.g. a `"owner": "#165"` ledger entry) are not prose and must not gain an
  inserted word.
- **A test fixture/Correction is not a "pin."** Don't use "pin"/"pins" as a casual generic word
  for a regression fixture, Correction, or test case — say **test** (or the specific, more precise
  term a doc calls for) instead. This does not touch the deliberately narrower, ADR-backed
  vocabulary in `tools/train/CONTEXT.md` (Decision Claim / Axis Claim / Endorsement Claim, etc.),
  which already retired "pin" in favor of those more precise names and reserves "test" for the
  pytest suite specifically — that glossary remains authoritative as written.

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

**A SELF-FILED issue is not a spec — it is the implementer's own reading, and it inherits the
implementer's mistakes.** When the same session files an issue and then builds it (the `/implement`
chip-spawn path), the usual protection — a spec written by someone who read the code independently —
is absent, so the issue can assert evidence nobody gathered and no later step will notice. Two rules
follow, both cheap:

- **`/code-review`'s Spec axis MUST be told the spec is self-filed**, and told to distrust it *more*,
  not less; its report gains a clause for *claims in the spec that verification does not support*.
  The brief must also NAME the one factual claim the decision rests on and say what rides on it. See
  `.claude/skills/code-review/SKILL.md` §4.
- **A negative result needs a positive control.** Before writing "X appears nowhere" or "nothing
  fires at Y" into an issue, run the same instrument against a case that MUST match; if it stays
  quiet, the instrument is broken, not the codebase. **File existence is never evidence of file
  content** — if the claim is about what is *in* a module, quote the module.

Both come from Issue #319, where a self-filed issue's decisive table ("every sibling flag falls back
to a surviving rung ladder") was derived from `ls` alone. `baseline_promote.py` reads *"EMPTY since
ADR-0100. All seven promote rungs are DELETED."* The false claim reached the issue body and a shipped
docstring; only the Spec axis — briefed with both rules above — caught it.

### Domain docs

Multi-context: `CONTEXT-MAP.md` indexes per-context `CONTEXT.md` files; all ADRs live in one
system-wide `docs/adr/` series. See `docs/agents/domain.md`.
