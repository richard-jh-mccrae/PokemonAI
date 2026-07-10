# Deferred: the retreat-Tool-enabled lethal (`lethal-retreat-enabler`)

**Status:** deferred at apply time, 2026-07-10 (`/update-strategy`). Proposal:
`data/strategy/proposals/blunder-20260709-mega_lucario.md#lethal-retreat-enabler`.
Correction: `84071010:f15`. Fixture: `tests/fixtures/corrections/ml_dead_hand_full_refresh_f15.json`.

## The line

Turn 3. My Active is a 50/80 Makuhita (retreat **2**, zero Energy attached). My Bench holds a Mega
Lucario ex carrying one `{F}`. The opponent's only Pokémon is an 80/80 Riolu; their Bench is **empty**.

> Team Rocket's Petrel → tutor **Air Balloon** → attach it to Makuhita (retreat 2 − 2 = **0**) →
> retreat free → promote **Mega Lucario ex** → **Aura Jab {F} 130 ≥ 80** → their board is empty → **WIN.**

Verified at source: Air Balloon is a Pokémon Tool, "The Retreat Cost of the Pokémon this card is attached
to is {C}{C} less" (`CardStat.retreatReduction == 2`, parsed 2026-07-10); Makuhita's printed retreat is 2;
Aura Jab is `{F}` for 130; `Planner._attack_wins` already models the bench-out win.

## Why it was NOT built

The Lethal Solver's contract is *sound-or-silent*: "SOUND only when the deck DEFINITELY still holds …
a probable fetch is never a win" (`_family_win_candidates` tier 3, ADR-0030/0037). Measured on the f15
state:

```
deck_definitely_has(Air Balloon)   -> False
deck_definitely_empty_of(...)      -> False
deck_contains_probability(...)     -> 0.9877
obs has own_prizes                 -> False   (the deck tracker never anchors)
```

The tutor target is only **98.8% likely** to be in the deck, not certain. Locking the win here would be
exactly the phantom lethal the family forbids — the one catastrophic error class. In a live match the
match-scoped deck tracker anchors after a search reveal and `deck_definitely_has` can become True, but the
single-frame Correction cannot express that, so **the proposal has no gate as stored**: its own fixture
records the *refuted* dead-hand framing (`correct = [1]`, Lillie's Determination) rather than the Petrel
line, and the live `chosen` was already `[0]` (Petrel).

## Definition of done

1. **Re-capture the fixture** carrying `obs["own_prizes"]` (backfill via `tools/train/backfill_obs.py`)
   so the deck tracker anchors and `deck_definitely_has(Air Balloon)` is decidable in a retest. Re-tag
   `correct` to the Petrel line (`[0]`) — the stored `correct` belongs to the refuted framing.
2. **Model retreat affordability in the solver.** Add a `retreatReduction` term so
   `Planner._can_retreat`-style logic (see `Pilot._can_retreat`, shipped 2026-07-10) accounts for an
   in-hand retreat Tool: `retreat_cost - retreatReduction <= attached_energy`.
3. **Add the enabler family** to `_family_win_candidates`: play/attach a retreat Tool (optionally
   tutored first by a Trainer-tutor Supporter whose target is `deck_definitely_has`) → retreat →
   promote a ready benched attacker → `_develop_wins`. Cascade-verify like tiers 3/4: a refute drops the
   candidate, a `None` verdict keeps the sound lock.
4. **Gate:** the re-captured f15 fixture locks (`planned.goal == "win"`, `next_step == [0]`), the three
   shipped counter-fixtures still lock (`ml_lethal_recover_energy_via_gong_f48`,
   `ml_lethal_recover_energy_retreat_ko_f26`, `ms_lethal_recover_energy_to_win_f110`), no fixture
   regresses, suite green.

Related: `[[lethal-solver-plan]]`, the shipped `Pilot._grab_enabler_lethal_tactical` (the *bench-the-
enabler* sibling, ml f13), and `Pilot._can_retreat` (the retreat-affordability precondition that the
phantom-grab-lethal fix already introduced).
