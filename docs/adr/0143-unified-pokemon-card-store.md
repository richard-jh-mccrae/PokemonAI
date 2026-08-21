# ADR-0143 — One frozen record per card printing under `common/cards/`

Status: Accepted; built for every card in the three shipped decks' lists.

## Context

Answering "what is this card?" mid-game took five separate lookups — the stat record, a second
attack table keyed by attack id, the tag table, the clause table, and the role tables — plus
per-decision caches rebuilt from those on every `decide()`. Attack effects lived as ~28 flat
columns on `AttackStat`, most empty on any given attack, and every new effect shape meant a new
column.

## Decision

`src/common/cards/` holds one frozen record per printing — `PokemonCard` under `pokemon_cards/`,
`TrainerCard` under `trainer_cards/`, `EnergyCard` under `energy_cards/` — one generated module
per card, loaded once per process and served as one dict by `card_store()`. A record carries its
printed facts and typed effect Clauses **embedded**: Attacks and Abilities on the
Pokémon record, the play effect on the Trainer record, the provision riders on the Energy
record, every effect encoded as `Clause` legs.

`Clause` is a required `kind` plus that card's own **named parameters**; an unset parameter reads
as None. The vocabulary is `card_effects.json`'s, and the open shape is deliberate: the audited
encodings grow a key or two with each new card shape, and a fixed-field record would need editing
before such a card's file could exist. Drift is caught by source-sync tests, not by the record.
Amounts are damage points, never counters. Trainer class rules (one Supporter per turn, Tools
attach, Stadiums replace) follow from the record's `kind`, never from per-card data. Deck-intent
roles stay per-match overlays; only tag-derived defaults ship, minted by `pokemon_default_roles()`
with the same semantics as `general_pokemon_roles`.

`tools/build_pokemon_cards.py` generates every card module from the engine-twin defs plus the
shipped tag/clause stores and refuses to emit any effect it has no encoding for. The former
The former loose-tag adapter was later quarantined with the Bellman teacher by Issue #582.

## Where a card function's logic lives

`common/cards/functions/` holds one module per card function, named for the function it owns:
`fetch.py`, `draw.py`, `damage.py` (with `damage_context.py` beside it for the scaling variables),
`energy.py`, `attack_lock.py`. There is deliberately no registry — a function is found by its
filename — and the package init stays empty of re-exports so importing one function cannot drag in
its siblings or cycle back into the card records. Every one of these modules imports nothing from
the project, which is what made the move free.

The tag and clause tables stay where they are — 88% of their rows are opponent cards, which the
scouting rework replaces. `card_worth.py` stays out: it prices a function rather than defining
one, and ADR-0065 owns that currency.

## How facts reach the functions (amended 2026-08-19; wired the same day)

A function's hands hold records, never ids: `PokemonCard`, `Attack`, `Clause` arrive as plain
arguments, and the id-to-record resolution happens once at the edge, where each board-state
consumer holds a `cards` mapping that defaults to `card_store()` (tests inject synthetic records
through the same parameter). The store's clause vocabulary is canonical — a function conforms to
the card file, never the reverse — and derived readings live once, on the record (`prize_value`,
`is_rule_box`, `has_ability`, `clause(kind)` as a plain scan; `play_clauses(card)` for the effect
legs a play offers — a record's own plus its Abilities', never its attacks').

The wiring pass ran as one event per function, energy first and damage last. The two silent traps
`tests/cards/test_function_wiring_prep.py` had pinned (`bench_reach` reading a store Attack as
zero reach; the attack-lock fold reading one as never locking) are FLIPPED: the same tests now
assert the real readings. The rewire also caught a record defect the prep tests had wrongly
pinned — a Mega Evolution ex gives up three prizes, not two — surfaced by three human-ruled
acceptance gates flipping and settled against the engine provider.

## Consequences

A mid-game card query is one dict hit plus attribute reads, and the store covers every card in
all three decklists — `tests/cards/test_energy_store.py` pins exactly that, while the
`test_pokemon_store.py` / `test_trainer_store.py` guards assert every fact class against its
source (engine defs, tag table, clause store, shipped role derivation), so a hand edit to a
generated file cannot drift silently. The six card functions and their Bellman consumers now read
the records; the legacy stat/effects tables remain live only for the scouting layer, the strategy
authoring/minting layer, and the Lethal Solver's coverage gate, all of which the scouting rework
owns.
