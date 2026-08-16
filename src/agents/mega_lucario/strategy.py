"""Mega Lucario declarations for the shared Bellman runtime.

Aura Jab (one Energy, 130) recycles up to three Basic {F} Energy from the discard onto the Bench, so
Lunar Cycle's per-turn Energy discard funds the Bench rather than losing tempo. Mega Brave (270)
locks itself for a turn, so it is the exception rather than the plan. Cosmic Beam is 70 for one
Energy but does nothing without Lunatone Benched, which is why the pair is declared as partners.
"""
from common.strategy import (
    ActivationCondition, DesiredFact, Roles, Strategy, StrategyHint,
)

# Card ids — mega_lucario/deck.csv.
RIOLU, MEGA_LUCARIO_EX = 677, 678
MAKUHITA, HARIYAMA = 673, 674
SOLROCK, LUNATONE, MEOWTH_EX = 676, 675, 1071
FIGHTING_ENERGY = 6
UNFAIR_STAMP, ULTRA_BALL, SWITCH = 1080, 1121, 1123
PREMIUM_POWER_PRO, FIGHTING_GONG, POKE_PAD, AIR_BALLOON = 1141, 1142, 1152, 1174
BOSS_ORDERS, BLACK_BELTS_TRAINING, JUDGE = 1182, 1211, 1213
TEAM_ROCKETS_PETREL, LILLIES_DETERMINATION, WALLYS_COMPASSION = 1219, 1227, 1229
GRAVITY_MOUNTAIN = 1252

# Sparse deck intent over portable card facts. Meowth ex is deliberately absent: its Supporter
# tutor is a shared Card Function, so `general_pokemon_roles` resolves it the same way in every
# deck that plays it. Evolution relationships come from card facts, not from this table.
ROLES = Roles({
    RIOLU: ["primary_attacker"],
    MEGA_LUCARIO_EX: ["primary_attacker", "accel_source"],
    SOLROCK: ["backup_attacker", "engine"],
    LUNATONE: ["engine"],
    MAKUHITA: ["backup_attacker"],
    HARIYAMA: ["backup_attacker"],
})

STRATEGY = Strategy(
    name="mega_lucario",
    roles=ROLES,
    # Cosmic Beam and Lunar Cycle each read the other body in play, so either alone is dead weight.
    partners={SOLROCK: (LUNATONE,), LUNATONE: (SOLROCK,)},
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Solrock opens: one Energy buys 70,
    # and unlike Riolu it is not the base of the primary line. Meowth ex is last — a setup Active
    # cannot use Last-Ditch Catch, which is the only reason the card is here.
    starter_priority=(SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX),
    # No `prize_plan`. Solrock/Hariyama around two Mega Lucario ex genuinely makes the opponent take
    # EIGHT prizes, but declaring the route ALSO caps board and hand Worth per resource job at the
    # route's own count (`BoardPotential._prize_job_capacities`). This deck plays three Solrock
    # against a route naming one, so the third scored ZERO and the setup decisions moved with it:
    # measured 27/70 against 32/70 on the correction corpus. Restore only with that coupling split.
    params={"preferred_start": "first"},
    strategies=(
        # A Solrock without its partner cannot attack at all, so completing the pair outranks the
        # ordinary bench fill. Declared per Solrock position because the Active is not on the Bench.
        StrategyHint(
            "mega_lucario.pair_active_solrock_with_lunatone",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", SOLROCK),
                ActivationCondition("own.bench.card_ids", "not_contains", LUNATONE),
                ActivationCondition("own.bench.space", "gt", 0),
            ),
            (DesiredFact("deploy", "own.bench", target_card_ids=(LUNATONE,)),),
            "own.bench", "immediate", "high", "mega_lucario.strategy",
        ),
        StrategyHint(
            "mega_lucario.pair_benched_solrock_with_lunatone",
            "deck",
            (
                ActivationCondition("own.bench.card_ids", "contains", SOLROCK),
                ActivationCondition("own.bench.card_ids", "not_contains", LUNATONE),
                ActivationCondition("own.bench.space", "gt", 0),
            ),
            (DesiredFact("deploy", "own.bench", target_card_ids=(LUNATONE,)),),
            "own.bench", "immediate", "high", "mega_lucario.strategy",
        ),
        # Lunar Cycle is the draw engine and it reads Solrock anywhere in play, so a lone Lunatone
        # wants its partner just as much.
        StrategyHint(
            "mega_lucario.pair_lunatone_with_solrock",
            "deck",
            (
                ActivationCondition("own.bench.card_ids", "contains", LUNATONE),
                ActivationCondition("own.bench.card_ids", "not_contains", SOLROCK),
                ActivationCondition("own.bench.space", "gt", 0),
            ),
            (DesiredFact("deploy", "own.bench", target_card_ids=(SOLROCK,)),),
            "own.bench", "immediate", "high", "mega_lucario.strategy",
        ),
        # Heave-Ho Catcher rides the evolution itself, so the Makuhita line is worth the most on the
        # turn there is something on the opposing Bench worth dragging out. This raises that turn's
        # search priority; it never suppresses the general evolve, which Bellman still values.
        StrategyHint(
            "mega_lucario.evolve_makuhita_for_the_gust",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", MAKUHITA),
                ActivationCondition("opponent.bench.role_target_count", "gt", 0),
            ),
            (DesiredFact("evolve", "own.active", target_card_ids=(HARIYAMA,)),),
            "own.active", "this_turn", "high", "mega_lucario.strategy",
        ),
    ),
)
