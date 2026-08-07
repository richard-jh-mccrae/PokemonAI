"""The readiness leaf's per-body constants. NO methods: POC-T4/5 deleted all twelve, and these are what
outlived them.

Only `_READINESS_CAP` still has a production reader (`leaf`). The other eight are imported by the
planner spine purely to keep the old import path working, and their real consumer is
`tests/strategy/test_state_value.py`, which reads two of them to prove `state_value`'s own constants
are DERIVED from these rather than copied. That is a reason to keep them and a reason to leave them
here, where the emptiness is visible, instead of scattered through a module that still has code."""
from __future__ import annotations



# ═══ READINESS LEAF + SPEND ACCOUNT (board-state-valuation-grill.md / t0-planner-disposition.md,
#     decided 2026-07-16) ═════════════════════════════════════════════════════════════════════════
# The MY-side "how close am I to executing my win" positional term. NO PRODUCTION CALLER since
# POC-T3: `_engine_leaf_value` is `KO_SCORE x state_value(end board) + min(_LINE_CAP, line)`. Gated-
# additive: every term capped so Σ readiness < one prize (KO_SCORE), preserving the hard-rung invariant
# (a positional board never outranks a real prize). The opponent is NOT modelled here (the survival term
# + the later 2-ply own that). The measured problem it fixes: full within-turn search reaches ~36 distinct
# end-boards but the old leaf collapsed them to ~5 values (SOLE-top ~5%). See the grill spec.
_READINESS_CAP = 300.0        # Σ readiness ceiling — the dominant positional term, but < KO_SCORE.
                              # Max positional stack (readiness 300 + survival 50 + threat 100 +
                              # value 40) = 490 < 1000 = KO_SCORE — no positional board outranks a prize.

_READINESS_BODY_CAP = 120.0   # per-body contribution cap — one fully-loaded attacker can't dominate the
                              # sum (a 2nd attacker / the engine stays legible in the total).

_READINESS_BENCH_DISCOUNT = 0.45   # bench position weight FLOOR for attack readiness (Active = 1.0).
                              # v2 (the who's-Active term, 2026-07-20): the FLOOR of `_bench_position_w`'s
                              # PROMOTION-EASE lift toward `_READINESS_PROMO_MAX` — a benched attacker is
                              # nearer-Active when the Active can vacate freely. Degrades to this flat v1
                              # weight when the Active can't retreat free and no switch is visible (or
                              # stats are unknown).

_READINESS_PROMO_MAX = 0.5    # ceiling of the lifted bench weight — promotion is never free (it still
                              # costs the once-per-turn retreat action + the tempo of the swap), so a
                              # benched attacker must NEVER read equal to the same attacker Active.
                              # Measured on the leaf lab (2026-07-20): 1.0 let "hide the loaded attacker
                              # behind a free-retreat wall" boards overtake the human's attacker-in-front
                              # boards (39→37 SOLE / 190→184 shared); 0.75/0.6 still lost frames; 0.5 is
                              # the frontier with ZERO regressed frames (40/190, E 83.8→84.7).

_READINESS_MOBILITY_W = 2.5   # the who's-Active micro-credit: `_active_quality` × this, once per board
                              # (a bench must exist — a good Active with nowhere to go is nothing). The
                              # second who's-Active facet the lift can't reach: a free-retreat body UP
                              # FRONT (Cinderace r0, Lunatone+Air Balloon) or a building line pre-evo is
                              # what the human boards consistently keep, and the dissected residual ties
                              # differ by exactly this when the bench is unloaded. Micro-sized: it splits
                              # exact-value ties, never outranks a real readiness gap (smallest genuine
                              # attack contribution ≈ a 30-chip × 0.45 × 0.45 ≈ 6). HAND-ARMED
                              # (`leaf_hand_value`): measured hand-blind it nets sole +4 but trades a
                              # shared-top frame whose label pivots on HIDDEN-hand context (the held
                              # Lunar-Cycle {F} / the Mega-in-hand attach) — with the injected hand the
                              # context is readable, so the credit rides the hand-visibility arm.

_READINESS_ATTACK_W = 0.45    # damage → readiness scale (Mega Brave 270 × 0.45 = 121 → body cap 120; a
                              # 70 chip → 31): keeps attack readiness the dominant, legible term.

_READINESS_SATURATED = 0.1    # a 2nd in-play body filling a UTILITY/ENGINE role already filled contributes
                              # ~this (a 2nd Lunatone is fodder — "we only ever need one"); ATTACKERS are
                              # never saturated (a 2nd attacker advances the prize race).

_READINESS_ABILITY_VALUE = {  # value of a body's best FIREABLE setup ability, by behavioral Function Tag
    "energy_accel": 55.0,     # (card_functions.json) — draw/accel/dig/tutor abilities are a FIRST-CLASS
    "draw": 45.0,             # contribution in these ability-centric setup decks (Lunatone draw-3,
    "dig": 45.0,              # Drakloak Recon), CO-EQUAL with an attack. A body with an `engine`/
    "search": 40.0,           # `accel_source` Role but no matching tag gets `_READINESS_ENGINE_ABILITY`.
    "tutor_energy": 35.0, "tutor_pokemon": 35.0, "tutor_mega": 35.0,
    "supporter_tutor": 30.0, "recycle": 25.0, "stall": 20.0,
}

_READINESS_ENGINE_ABILITY = 45.0   # fallback ability value for an `engine`/`accel_source`-Role body whose
                              # ability the Function Tags miss (Lunatone's Lunar Cycle draw is
                              # role-declared, untagged — verified: card_functions.json has no id 675).
