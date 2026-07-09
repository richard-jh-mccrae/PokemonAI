# Handoff — the opponent-modeling capability-gap cluster

**Repo:** `C:\Users\Richard\Projects\PokemonAI`
**Next session's task (user's words):** *"save as /handoff, we do this in another session"* — build the
opponent-side resource/out model that unblocks a cluster of deferred strategy proposals.
**Date raised:** 2026-07-09 (during the big `/update-strategy` compilation).
**Why deferred, not built:** every one of these needs the SAME unbuilt infra — a model of the
opponent's remaining resources / outs. There is none today (`deck_odds.py` / `deck_tracker.py` are
**own-deck only**). Faking a weight without the signal is refused (ADR-0026 killed diffuse priors).

## The one shared build (do this first): an OpponentResourceModel

Mirror our own-deck knowledge onto the opponent. Model, per match, from the Read's representative
decklist prior minus everything visible:
- **`opp_copies_left(card)` / rebuild-odds** — infer the opp's decklist from the Read's representative
  build, subtract visible board + discard + revealed logs, split unseen copies over their hidden
  prizes (hypergeometric, exactly like `deck_odds.p_contains` but opponent-side).
- **`opp_deckout_in_turns`** — their `deckCount` trajectory (already read as a snapshot at
  `objectives.py:304`, `planner.py:582/1451`, `pilot.py:1666`, never accumulated).
- **`opp_hand_size_delta` + `opp_last_turn_dumped`** — cross-turn hand-size change + whether they
  resolved an Ultra-Ball-class discard-cost card last turn (from `obs['logs']` + opp discard diff).
- **A Board "I took a KO on the opponent this turn" flag** (not exposed today).

Model home: a new `src/common/opponent_model.py` (match-scoped, like `deck_tracker.py`), surfaced as
Board fields. Sources of truth: `src/common/scouting/scout.py` (the Read's `expected_cards` /
`evolution_paths`), `obs['logs']`, opp `discard` / `handCount` / `deckCount` / `prize`.

## What unblocks once it exists (the deferred proposals)

All in `data/strategy/proposals/` (status `deferred`), with per-item definition-of-done already written
by the analysis subagents:

1. **`kou-30deck-general.md` · unfair-stamp-comeback-posture** — needs the *KO-this-turn* Board flag +
   an `opp_comeback_disruptor` opponent property (route its per-archetype assertion to `/matchup-genie`
   for the 21 Briefs). Then: after I take a KO, don't empty my hand — hold a recovery out (they can now
   Unfair-Stamp me). Offensive/user side is already COVERED.
2. **`learnthetcg-fundamentals.md` · ko-target-maximise-opponent-whiff** — the KO-target tiebreak
   (behind-gated, sub-`KO_SCORE`): prefer the KO that leaves them needing the most specific cards.
   Needs `opp_copies_left` / rebuild-odds.
3. **`learnthetcg-fundamentals.md` · risk-scales-with-prize-position** (the AHEAD "play around their
   one out" half only — the behind/gamble + ahead-stabilise halves are COVERED) — needs the opp
   comeback-out model ("what would I hate to draw off their Iono? cut it").
4. **`learnthetcg-fundamentals.md` · disrupt-tailored-hand-dont-hoard-iono** (side 1 only — side 2 is
   COVERED by the Shuffle-Refresh dead-hand gate) — value hand-disruption when the opp tailored a big
   hand to a few key cards right after an Ultra Ball. Needs `opp_hand_size_delta` + `opp_last_turn_dumped`.
5. **`learnthetcg-fundamentals.md` · deck-knowledge-bottom-tracking-and-opponent-resources** (opponent
   half — own guarantee-out-no-shuffle sequencing is a SEPARATE buildable, see below) — exact endgame
   deck-out + play-around-the-last-copy. Needs the full OpponentResourceModel.

## Two adjacent gaps that are NOT opponent-modeling (note, decide separately)

> **Now carved out to their own handoff** (ADR-0047): the three items below live in
> `pokemonai-handoff-ownside-sequencing-and-lethal-depth.md`. Build them there, not under the Opponent
> Model. Kept here for context.


- **`dont-spend-unneeded-supporter` (generic half)** — needs an OWN-side `turn_goal_satisfied` Board
  predicate (Turn-Planner directed goal already met + nothing still being searched + no thinning
  value). Then a hold-the-draw-supporter hypothesis gated on it (seed 10–20, must not regress the
  refuted-hoarding endorsement, `doctrine_shuffle_refresh.py:8`). The Boss's-Orders "save it" half is
  already COVERED by `gust-for-the-ko`.
- **own-deck guarantee-out sequencing** (the OWN half of #5) — buildable TODAY on `deck_known_counts` +
  draw-depth: a `guaranteed_out_at_risk_from_shuffle` predicate ("a thin that could shuffle away a
  certain draw is not a thin"). Planner-code, no opponent model needed.
- **`revive-the-dead-hand-full-refresh` → REFUTED, and it exposes a DEEPER LETHAL class.** The user
  re-examined f15's exact state and found it is NOT a dead hand — it is a **missed lethal** (turn 3):
  *Petrel → tutor Air Balloon → attach to Active Makuhita → free-retreat (Air Balloon −2 = Makuhita's
  retreat 2) → promote benched Mega Lucario ex → Aura Jab {F} 130 ≥ Riolu 80, opp bench empty → WIN.*
  So the shuffle-for-8 tag was suboptimal; the dead-hand rule is refuted for its only fixture. The real
  gap is the **Lethal Solver going one composition deeper**: a play that *enables a retreat* into a
  ready benched attacker (attach an in-hand retreat tool, OR a Supporter that TUTORS one) → promote →
  attack → win. Today's grab-enables-lethal tactical (`_grab_lethal_tactical`, ADR-0030) handles the
  energy-recover case; this is the retreat-enabler case. Engine-verified line facts in the proposal.
  Home: extend `_family_win_candidates` / a new tactical in `pilot.py`, cascade-verified like tiers 3/4.

## Guardrails (do not repeat past mistakes)
- **Ladder-validate, don't gauntlet-A/B** — the cross-deck gauntlet is invalid-for-gain
  (`[[gauntlet-invalid-ladder-only]]`). Ship each feature default-on, kill-switched, with
  blunder-buster telemetry; the Kaggle ladder + user corrections are the gate.
- **The HIGH-BAR opponent properties** (`opp_is_engine_dependent`, `opp_comeback_disruptor`) price a
  wrong assertion ~4% — assert only with strong evidence (`opponent_properties.json` notes).
- **Sound-or-silent** — an opponent-out estimate must fail OPEN (never suppress a real line on a guess),
  exactly like `deck_odds`.

## Files
- Proposals: `data/strategy/proposals/{kou-30deck-general,learnthetcg-fundamentals}.md` (status `deferred`).
- Own-deck analog to mirror: `src/common/deck_odds.py`, `src/common/deck_tracker.py`.
- Read / decklist prior: `src/common/scouting/scout.py`, `src/common/scouting/opponent_properties.json`.
- Snapshot opp reads to accumulate: `objectives.py:304`, `planner.py:582/1451`, `pilot.py:1666`.
