# ADR-0153 — The card store absorbs the JSON tables; a card is one record module

Status: Accepted (2026-08-21); BUILT. Follows ADR-0143/0152; owner's directive.

## Context

Four JSON tables under `src/common` carried per-card facts the unified store was built to own:
`card_functions.json` (behavior tags), `card_effects.json` (effect clauses + coverage verdicts),
`attack_overrides.json` (engine stat corrections), and its provenance sidecar. Each was a second
copy of card truth with its own loader, unreviewable in diffs and invisible to the type system —
exactly the shape ADR-0143 exists to retire. The owner's ruling: one class definition per card
under `src/common/cards/`, tag and function logic beside it, no long JSON definitions.

## Decision

Card records are the single runtime source; the JSON tables leave `src/common` entirely.

- **The store grows two tiers.** CORE (deck slots + Brief printings) keeps the fail-loud
  completeness gates: authored roles, every effect text clause-encoded. TAIL is every other id
  the authoring inputs know something about — tags, clauses, verdicts, or stat corrections —
  emitted honestly partial: a missing clause set reads as a hole, exactly as an absent record
  does. `tests/cards_helpers.py` computes both tiers from the same inputs the builder reads.
- **Schema carries what the tables carried.** `Attack` gains typed engine-correction fields
  (`engine_overrides()` reassembles the stat-provider patch); every record class gains `covers`,
  the clause-completeness verdict, whose prose reasons stay with the authoring source.
- **Loaders become store views with unchanged APIs.** `CardFunctions.load()` serves record tags;
  `load_attack_overrides()` reassembles patches from record attacks and feeds the same
  `build_attack_stats`. Equivalence was proven against the tables before deletion: zero tag
  mismatches, zero verdict mismatches, all 117 attack patches byte-identical, and the teacher's
  six correction pins reproduce exactly.
- **Authoring inputs live with the authoring tools.** `measured_functions.json` (probe
  accumulation), `attack_overrides.json` + provenance (generator output), and the measured/
  override effect sources sit under `tools/meta_tracker/`; `build_pokemon_cards.py` bakes them
  into record modules and remains byte-idempotent. `build_card_effects.py` is now the merge
  library the builder and gates share.
- **The teacher keeps a frozen table.** `deprecated/bellman/card_effects.json` moved beside its
  quarantined loader and is deliberately never regenerated; the Ledger corpus replay binds it
  explicitly, so ADR-0147's honest-grading numbers replay unchanged.

## Consequences

The store triples to ~493 modules; the bundle ships record modules and no JSON. Tag or clause
edits are now typed, reviewable diffs on one card's file. The sync gates invert: records are
verified against the tools-side authoring inputs rather than a shipped table. A new meta card
enters by record generation (tail) or full authoring (core) — never by editing a table by hand.
