# ADR-0151 — Evolution underpricing: line continuity under the body, size as a dark lever

Status: Accepted (2026-08-20); BUILT. Follows ADR-0150; owner's sitting of the same day.

## Context

Every evolve in the corpus priced negative (−0.04 to −0.47; one frame DECLINED a ruled
evolve at −0.42). Decomposition on four frames: the hand pays the evolution card at full
worth (−0.26..−0.33) while the board credits near-parity — pre-evolution and evolution share
a role tier, the tucked card collapses to `zone_under_body 0.10`, absolute HP is invisible,
and a Mega ex even ADDS prize liability. The 8-miss "should have evolved" cluster is this
one accounting hole.

## Decision

- **`zone_under_body` 0.10 → 0.65** (an existing lever, no code): the card invested under an
  evolution keeps most of its worth — evolving is a zone TRANSFER of the line's assets, not a
  spend. Measured: floor 40.9% → 44.2%, agrees 201 → 209 of 427, mega_starmie reaches 50.0%,
  zero regressions.
- **`hp_value`** (new, default 0.0 = off): prizes per 100 printed max HP on every body,
  inside the damage multiplier — size becomes worth, chip damage prices as a constant real
  loss per HP, and a store-unknown opponent body carries threat weight from its printout
  alone. Every tried value (0.05–0.2) traded real rulings (Jetting-vs-Nebula KO math,
  attach-when-able) for its gains, so it ships DARK for a later round; the mechanism tests
  pin both shapes.
- **Four maneuver rulings dispositioned `deferred-multi-turn`** by the owner (81904451-37,
  81904451-50, 85785609-82, 83667237-107): each rationale narrates a fetch→retreat→promote→
  attack, KO-chain, or prize-math line no 1-ply price can see. They had blocked three rounds
  of otherwise-clean adoptions; they return to grading when the turn planner grades
  maneuvers. Retiring a ruling to clear a lever is an OWNER call, made here explicitly.

## Consequences

- Evolves price positive where the doctrine wants them; the decline-a-ruled-evolve failure
  mode is gone at the source.
- KO'ing an evolved body now costs its whole stack (under-cards at 0.65), which also reads
  as honest threat weight on the opponent's evolved bodies.
- `hp_value` and `concentration` (ADR-0150) are the two dark levers awaiting a round that
  can afford their trades — likely after the planner absorbs the maneuver frames.

## Addendum 2026-08-21

`hp_value` armed at 0.2 by owner order under the bootstrap lens: the Ledger is the
SearchAlgo's leaf evaluation, and bulk is a LEAF property search inherits, while the corpus
flips it costs (13 out, 13 in vs the 217/422 baseline) flow through 1-ply policy channels —
retreat-doom laundering chief among them (decomposed on frame d98fc4c74107: both attach
prices identical, the flip rides Retreat +0.012 -> +0.137) — that search replaces. Floor
46.5% -> 50.8%, every deck above half. The duplicate-on-last-slot refusal is now offset at
defaults (its mechanism stays pinned with the lever zeroed).
