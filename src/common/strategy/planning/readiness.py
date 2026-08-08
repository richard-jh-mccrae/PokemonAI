"""The readiness leaf's per-body constants. NO methods: POC-T4/5 deleted all twelve.

Only `_READINESS_CAP` has a production reader (`leaf`); the rest are imported by the planner spine to
keep the old path working, and read by `tests/strategy/test_state_value.py` to prove `state_value`'s
own constants are DERIVED from these rather than copied."""
from __future__ import annotations



# The MY-side "how close am I to executing my win" positional term. NO PRODUCTION CALLER since POC-T3.
# Gated-additive: every term capped so Σ readiness < one prize (KO_SCORE), preserving the hard rung.
_READINESS_CAP = 300.0        # Σ readiness ceiling — the dominant positional term, but < KO_SCORE.
                              # Max positional stack (readiness 300 + survival 50 + threat 100 +
                              # value 40) = 490 < 1000 = KO_SCORE — no positional board outranks a prize.

_READINESS_BODY_CAP = 120.0   # per-body contribution cap — one fully-loaded attacker can't dominate the
                              # sum (a 2nd attacker / the engine stays legible in the total).

_READINESS_BENCH_DISCOUNT = 0.45   # bench position weight FLOOR for attack readiness (Active = 1.0) —
                              # the floor of `_bench_position_w`'s promotion-ease lift toward
                              # `_READINESS_PROMO_MAX`, used when the Active cannot vacate freely.

_READINESS_PROMO_MAX = 0.5    # ceiling on the lifted bench weight — a benched attacker must never read
                              # equal to the same attacker Active. 0.5 is the frontier: 1.0/0.75/0.6 regressed.

_READINESS_MOBILITY_W = 2.5   # the who's-Active micro-credit: `_active_quality` × this, once per board
                              # (bench must exist). Ties only: below the ~6 smallest real gap. `leaf_hand_value`.

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
