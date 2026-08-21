# ADR-0152 — Brief-deck store records and the doomed-active read

Status: Accepted (2026-08-20); doomed projection superseded by Issue #582.

## Context

The store covered only our three decks' 50 printings; every opponent card priced at the
unknown floor and the gap census logged ~275 affected decisions. The owner ordered records
for every card the 16 scouting Briefs name.

## Decision

- `tools/build_pokemon_cards.py` generates from the DECK lists AND the Brief-named printings:
  130 new records (store 50 → 180). Pokémon default roles derive from the Briefs' own role
  declarations (filtered to the POKEMON_ROLES vocabulary, which gains the Brief target trio);
  two hand entries (Dunsparce 65, Fan Rotom 174). 96 attack texts hand-encoded into
  ATTACK_CLAUSES; 35 abilities + 12 trainers/stadiums/tools/special energies authored into
  `effect_overrides.json` with per-card `_covers` verdicts (45 full, 2 partial fail-closed).
  The coverage tests' owed set widens to deck ∪ Brief ids.
- **Doomed-active read** (`worth.best_payable_damage` + `doomed_active_discount`, default 0.0
  = off): an active either side's opposing active can KO outright — fully-paid printed
  attacks, weakness ×2 / resistance −30 from the records — prices as mostly spent. Ships
  DARK: at 0.4 it lifts the floor to 48.1% (+4 net) but flips 11 frames.

## Consequences

- Corpus agreement is NET FLAT (208/426): ADR-0148's recognition layer was already carrying
  the worth signal for these archetypes — the records' value is coverage honesty
  (gap-affected decisions 275 → 208), their-side attack/weakness/prize facts, and the doom
  read those facts enable.
- One frame exposed and deferred (82523164-55, owner-ruled): its prior agree was an all-zero
  tie accident; the ruled line is a gust→attack→snipe double KO, planner scope.
- Dark levers now three: `concentration`, `hp_value`, `doomed_active_discount` — all with
  measured profiles awaiting a round (or the planner) that can afford their trades.

## Addendum 2026-08-21

Issue #582 superseded the invented guaranteed attachment/evolution projection. The Ledger now
uses typed visible resources, Functions, turn allowances, and configured uncertain horizon reach.

Ammunition waiver (same day, owner doctrine on frame d98fc4c74107 — tempo aggression when
options are thin): usable Energy on OUR doomed active converts to damage this very turn, so
the doom discount spares that term; the body, dead units, and concentration progress still
read mostly spent. Gate-clean: 216 -> 217 of 426, zero flips, the gained frame is the ruling
frame itself.
