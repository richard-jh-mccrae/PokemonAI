# Handoff — own-side resource sequencing + Lethal-Solver depth (the NOT-opponent-modeling cluster)

**Repo:** `C:\Users\Richard\Projects\PokemonAI`
**What this is:** the three gaps that ADR-0047 explicitly carved OUT of the Opponent Model as *not
opponent-modeling*. They were flagged inside
[pokemonai-handoff-opponent-modeling-cluster.md](pokemonai-handoff-opponent-modeling-cluster.md) §"Two
adjacent gaps that are NOT opponent-modeling" — extracted here so they survive that handoff being
consumed. **None depends on the Opponent Model / OpponentResourceModel.** Two are own-side Planner-code;
one is a Lethal-Solver depth extension.
**Date raised:** 2026-07-09.
**Guardrails (all three):** ladder-validate, don't gauntlet-A/B (`gauntlet-invalid-ladder-only`); ship
default-on, kill-switched, blunder-buster telemetry; the Kaggle ladder + user corrections are the gate.

---

## 1. `dont-spend-unneeded-supporter` — needs an OWN-side `turn_goal_satisfied` predicate

**Proposal:** `data/strategy/proposals/learnthetcg-fundamentals.md` § `dont-spend-unneeded-supporter`
(status `deferred`, `target_layer: general-hypothesis`, `verification_contract: seed-ladder`).

Playing a draw supporter is not mandatory just because it's in hand. If the hand already meets the turn's
goal and there's no dig / disruption / thinning value in drawing, **hold** it — usually to save a
Boss's-Orders-class or new-evolution supporter for a later decisive turn.

**Definition of done.** A net-new OWN-side Board predicate **`turn_goal_satisfied`** = Turn-Planner
directed goal (ADR-0045 Game Plan) already met **AND** nothing still being searched **AND** no thinning
value left. Then a hold-the-draw-supporter Hypothesis gated on it (seed **10–20**). The payoff is a
preserved scarce future resource, not tempo now.
**Must not regress** the refuted-hoarding endorsement at `doctrine_shuffle_refresh.py:8`. The
Boss's-Orders "save it for the KO" half is already **COVERED** by `gust-for-the-ko`. If the predicate
isn't exposable, route honestly as a small capability-gap.

---

## 2. Own-deck guarantee-out sequencing — the OWN half of `deck-knowledge-bottom-tracking-...`

**Proposal:** `data/strategy/proposals/learnthetcg-fundamentals.md` §
`deck-knowledge-bottom-tracking-and-opponent-resources` (status `deferred`, `target_layer: planner-code`,
`verification_contract: seed-ladder`) — **own half only**; the opponent half is the OpponentResourceModel
work (ADR-0047, separate).

Exploit your own known late-game deck: sequence shuffle vs no-shuffle to *guarantee* an out (e.g. draw
down so the last Counter Catcher is certain). **"A thin that could shuffle away a certain draw is not a
thin."**

**Definition of done.** Buildable **TODAY** on `deck_known_counts` + draw-depth — no opponent model
needed. A Planner-code predicate **`guaranteed_out_at_risk_from_shuffle`** that demotes a "thin" which
would shuffle away a currently-guaranteed draw. **First confirm** whether the Planner already prefers
no-shuffle-to-guarantee sequencing — if so, mark **covered** rather than building. Sources:
`src/common/deck_tracker.py` (sound emptiness oracle), `src/common/deck_odds.py` (content odds).

---

## 3. `revive-the-dead-hand-full-refresh` is REFUTED → it exposes a deeper LETHAL class

**Proposal:** `data/strategy/proposals/blunder-20260709-mega_lucario.md` §
`revive-the-dead-hand-full-refresh` (status **`refuted`**). **Do not build the dead-hand detector.**

The user re-examined f15's exact state and found it is **NOT a dead hand** — it is a **missed lethal on
turn 3**. Line (engine-verified per correction `84071010:f15`, fixture
`tests/fixtures/corrections/ml_dead_hand_full_refresh_f15.json` — re-verify at source on build):

> Team Rocket's Petrel → tutor **Air Balloon** → attach to Active **Makuhita** → free-retreat (Air
> Balloon −2 == Makuhita retreat 2) → promote benched **Mega Lucario ex** → **Aura Jab {F} 130 ≥ Riolu
> 80**, opponent bench empty → **WIN.**

So the shuffle-for-8 tag was suboptimal and the dead-hand rule is refuted for its only fixture.

**The real gap = the Lethal Solver going one composition deeper.** A play that *enables a retreat* into a
ready benched attacker: attach an in-hand retreat tool **OR** play a Supporter that **tutors** one →
promote the benched attacker → attack → win. Today's grab-enables-lethal tactical
(`_grab_lethal_tactical`, ADR-0030) handles the **energy-recover** case; this is the new
**retreat-enabler** case.
**Home:** extend `_family_win_candidates` / add a new tactical in `src/common/pilot.py`, cascade-verified
like tiers 3/4 (refute drops the line, coin-floor keeps it — sound-or-silent).
**Sibling** `84071010-30` (the same episode's 1-card-hand case) is already **COVERED** by
`attack-last` + `dig-before-commit`.

---

## Files
- Proposals: `data/strategy/proposals/learnthetcg-fundamentals.md` (items 1, 2),
  `data/strategy/proposals/blunder-20260709-mega_lucario.md` (item 3).
- Own-deck signal sources: `src/common/deck_tracker.py`, `src/common/deck_odds.py`,
  `src/common/doctrine_shuffle_refresh.py`.
- Lethal Solver: `src/common/pilot.py` (`_family_win_candidates`, `_grab_lethal_tactical`), ADR-0030.
- Turn Planner directed goal: ADR-0045 Game Plan.
- Parent context (the carve-out): ADR-0047 §Scope; opponent-cluster handoff §"adjacent gaps".