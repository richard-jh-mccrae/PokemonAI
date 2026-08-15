"""Mega Starmie declarations for the shared Bellman runtime.

Turbo Mega Starmie ex: open Cinderace (Explosiveness), Turbo Flare to load the Bench, tutor + evolve
Staryu -> Mega Starmie ex, then fire Nebula Beam (one Ignition Energy on an Evolution = CCC).
"""
from common.strategy import (
    ActivationCondition, DesiredFact, StrategyHint, PrizePlan, Roles, Strategy,
)

# Card ids — mega_starmie/deck.csv.
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

# Sparse deck intent over portable card facts.
ROLES = Roles({
    MEGA_STARMIE_EX: ["primary_attacker"],
    STARYU: ["primary_attacker"],
    CINDERACE: ["backup_attacker", "accel_source"],
})

STRATEGY = Strategy(
    name="mega_starmie",
    roles=ROLES,
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Staryu is the Line base and wants
    # the BENCH, evolving behind the Cinderace wall rather than sitting in the most-exposed slot.
    starter_priority=[CINDERACE, STARYU],
    prize_plan=PrizePlan(routes=(
        (CINDERACE, MEGA_STARMIE_EX, MEGA_STARMIE_EX),
        (MEGA_STARMIE_EX, CINDERACE, MEGA_STARMIE_EX),
    )),
    params={"preferred_start": "second"},  # turbo: attack T1
    strategies=(
        StrategyHint(
            "mega_starmie.establish_benched_staryu_before_turbo_flare",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", CINDERACE),
                ActivationCondition("own.active.attack_ready", "eq", True),
                ActivationCondition("own.bench.space", "gt", 0),
                ActivationCondition("own.bench.card_ids", "not_contains", STARYU),
            ),
            (DesiredFact("deploy", "own.bench", target_card_ids=(STARYU,)),),
            "own.bench",
            "immediate",
            "high",
            "mega_starmie.strategy",
        ),
        StrategyHint(
            "mega_starmie.soften_role_target_for_nebula_beam",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", MEGA_STARMIE_EX),
                ActivationCondition("opponent.bench.role_target_count", "gt", 0),
            ),
            (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
            "opponent.bench.highest_role", "this_turn", "medium",
            "mega_starmie.strategy",
        ),
        NeedStrategy(
            "mega_starmie.deploy_backup_staryu",
            "deck",
            (ActivationCondition("own.board.evolvable_count", "eq", 0),),
            (DesiredFact("deploy", "turn"),),
            "turn",
            "this_turn",
            "high",
            "mega_starmie.strategy",
        ),
    ),
)
