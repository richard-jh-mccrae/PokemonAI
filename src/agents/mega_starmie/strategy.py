"""Mega Starmie declarations for the shared Bellman runtime.

Turbo Mega Starmie ex: open Cinderace (Explosiveness), bench Staryu so Turbo Flare's three Basic
Energy have a Benched recipient, evolve that Staryu into Mega Starmie ex, then attack. Nebula Beam
costs CCC and one Ignition Energy on an Evolution provides CCC, so it pays that attack alone.

The evolution and Ignition funding waypoints of that line stay undeclared: every guaranteed
immediate/high hint outranks general.low_cost_information_access_before_commitment in the beam,
and four adjudicated frames rule that free information leads. See docs/plans/strategy-beam-bellman.md.
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
            # Turbo Flare attaches only to BENCHED Pokémon, so an empty Bench wastes the attack.
            # The Bench must hold Staryu before Cinderace attacks, not after it is already funded.
            "mega_starmie.bench_staryu_before_turbo_flare",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", CINDERACE),
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
            # Wally's full heal bounces every Energy on the Mega to hand; general healing already
            # asks for the heal, so only the repayment is this deck's to declare.
            "mega_starmie.reload_the_healed_mega_with_ignition",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", MEGA_STARMIE_EX),
                ActivationCondition("own.active.hp_fraction", "ge", 1.0),
                ActivationCondition("own.active.energy_count", "eq", 0),
            ),
            (DesiredFact("fund_attack", "own.active",
                         target_card_ids=(IGNITION_ENERGY,)),),
            "own.active",
            "immediate",
            "high",
            "mega_starmie.strategy",
        ),
        StrategyHint(
            # Nebula Beam cannot reach the Bench, so the softening is Jetting Blow's 50-damage
            # rider: it drops a scouted role target into the 210 one Nebula Beam takes once gusted.
            "mega_starmie.soften_role_target_into_nebula_beam_range",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", MEGA_STARMIE_EX),
                ActivationCondition("opponent.bench.role_target_count", "gt", 0),
            ),
            (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
            "opponent.bench.highest_role", "this_turn", "medium",
            "mega_starmie.strategy",
        ),
    ),
)
