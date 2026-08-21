# ADR-0152 — Brief-deck store records and the doomed-active read

Status: Accepted (2026-08-20); BUILT. Follows ADR-0148/0151; owner's order of the same day.

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

The doomed read was re-ruled ASYMMETRIC and armed at 0.4 by owner order. THEIR active is
doomed only on our paid-up outright KO this turn (the engine still prices every actual attack;
the record read only bridges the pre-attack step — ours-only measured 210/426, NET negative,
so the anticipation stays). OURS is doomed under the conservative incoming read: their active
receives its coming attach (missing color first) plus one DIRECT evolution, energy carried,
before it swings (`worth.projected_incoming_damage`). Armed profile vs the armed-concentration
baseline: 213 -> 216 of 426, floor dragapult_ex 46.5% (19 up, 16 down).
