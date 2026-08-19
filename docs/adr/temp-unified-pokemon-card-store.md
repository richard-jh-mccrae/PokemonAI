# ADR-TEMP — One frozen record per card printing under `common/cards/`

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
printed facts, its Function Tags, and its effects **embedded**: Attacks and Abilities on the
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
`common/cards.py` module folded into the package as `common/cards/functions.py`; the public
import `from common.cards import CardFunctions` is unchanged.

## Consequences

A mid-game card query is one dict hit plus attribute reads, and the store covers every card in
all three decklists — `tests/cards/test_energy_store.py` pins exactly that, while the
`test_pokemon_store.py` / `test_trainer_store.py` guards assert every fact class against its
source (engine defs, tag table, clause store, shipped role derivation), so a hand edit to a
generated file cannot drift silently. The legacy stores remain live for off-deck cards and every
current consumer until the decision code repoints; that migration is the follow-up, not this
decision.
