"""Mega Starmie declarations for the shared Bellman runtime.

Turbo Mega Starmie ex: open Cinderace (Explosiveness), bench Staryu so Turbo Flare's three Basic
Energy have a Benched recipient, evolve that Staryu into Mega Starmie ex, then attack. Nebula Beam
costs CCC and one Ignition Energy on an Evolution provides CCC, so it pays that attack alone.

The evolution and Ignition funding waypoints are declared at this_turn, never immediate: four
adjudicated frames rule that free information leads, and only guaranteed immediate/high hints
outrank general.low_cost_information_access_before_commitment in the beam. See
docs/plans/strategy-beam-bellman.md.
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

PROMOTE_WINCON = "mega_starmie.promote_the_wincon"
# One outcome across three tutors: whichever finds the missing Mega, the line advances.
FIND_THE_EVOLUTION = "mega_starmie.find_the_evolution"
# `:readiest` binds the copy already holding Energy, not whichever sits earliest.
STARYU_BODY = f"own.body.card:{STARYU}:readiest"
STARMIE_BODY = f"own.body.card:{MEGA_STARMIE_EX}:readiest"

STRATEGY = Strategy(
    name="mega_starmie",
    roles=ROLES,
    # Measured deck dissent: the 2026-08-20 general adoptions flip four starmie rulings while
    # every other deck only gains — trail in docs/tuning/runs/ledger_20260820_round1.md.
    ledger_overrides={"demand_dead": 0.40, "kind.special_energy": 0.10},
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
        # --- Finding the Mega. Three tutors reach it; one bundle so one outcome claims one
        # --- protected slot. Wanted only while a Staryu waits, no Mega is in play, AND the
        # --- Mega is still in the deck: a dead tutor must not detour the line (cb70 ruling).
        StrategyHint(
            "mega_starmie.mega_signal_finds_the_mega",
            "deck",
            (
                ActivationCondition(f"own.card.{STARYU}.in_play", "eq", True),
                ActivationCondition("own.deck.card_ids", "contains", MEGA_STARMIE_EX),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "missing"),
            ),
            (DesiredFact("play_card", "own.bench", target_card_ids=(MEGA_SIGNAL,)),),
            "own.bench", "this_turn", "high", "mega_starmie.strategy",
            bundle_id=FIND_THE_EVOLUTION,
        ),
        StrategyHint(
            "mega_starmie.hilda_finds_the_mega_and_energy",
            "deck",
            (
                ActivationCondition(f"own.card.{STARYU}.in_play", "eq", True),
                ActivationCondition("own.deck.card_ids", "contains", MEGA_STARMIE_EX),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "missing"),
            ),
            (DesiredFact("play_card", "own.bench", target_card_ids=(HILDA,)),),
            "own.bench", "this_turn", "medium", "mega_starmie.strategy",
            bundle_id=FIND_THE_EVOLUTION,
        ),
        StrategyHint(
            # Salvatore evolves straight from the deck, skipping the hand entirely.
            "mega_starmie.salvatore_evolves_from_the_deck",
            "deck",
            (
                ActivationCondition(f"own.card.{STARYU}.in_play", "eq", True),
                ActivationCondition("own.deck.card_ids", "contains", MEGA_STARMIE_EX),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "missing"),
            ),
            (DesiredFact("play_card", "own.bench", target_card_ids=(SALVATORE,)),),
            "own.bench", "this_turn", "medium", "mega_starmie.strategy",
            bundle_id=FIND_THE_EVOLUTION,
        ),
        StrategyHint(
            # Poffin reaches Staryu (70 HP) directly onto the Bench.
            "mega_starmie.poffin_benches_the_staryu",
            "deck",
            (
                ActivationCondition("own.bench.space", "gt", 0),
                ActivationCondition("own.bench.card_ids", "not_contains", STARYU),
                ActivationCondition("own.deck.card_ids", "contains", STARYU),
            ),
            (DesiredFact("play_card", "own.bench", target_card_ids=(BUDDY_POFFIN,)),),
            "own.bench", "this_turn", "medium", "mega_starmie.strategy",
        ),
        # The evolution is the whole deck: 70 HP behind the wall becomes 330 in front of it,
        # and Nebula Beam's three Colorless slots are one Ignition Energy on the Evolution.
        # Wanted only while NO Mega stands: with one already attacking, this want rode the
        # whole-deck tutors and detoured the ruled retreat (cb70). Raising the second line
        # while the first still swings is Bellman's call, not doctrine's.
        StrategyHint(
            "mega_starmie.evolve_staryu_into_mega_starmie",
            "deck",
            (
                ActivationCondition(f"own.card.{STARYU}.in_play", "eq", True),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "missing"),
            ),
            (DesiredFact("evolve", STARYU_BODY, target_card_ids=(MEGA_STARMIE_EX,)),),
            STARYU_BODY, "this_turn", "high", "mega_starmie.strategy",
        ),
        StrategyHint(
            "mega_starmie.fund_the_readiest_mega_starmie",
            "deck",
            (ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "eq", True),),
            (DesiredFact("fund_attack", STARMIE_BODY),),
            STARMIE_BODY, "this_turn", "high", "mega_starmie.strategy",
        ),
        # After a loss the replacement is the wincon; the Cinderace wall goes up only while
        # no Mega Starmie ex is in play to take the slot.
        StrategyHint(
            "mega_starmie.promote_the_readiest_mega_starmie",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", None),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "eq", True),
            ),
            (DesiredFact("promote", STARMIE_BODY, target_card_ids=(MEGA_STARMIE_EX,)),),
            STARMIE_BODY, "this_turn", "high", "mega_starmie.strategy",
            bundle_id=PROMOTE_WINCON,
        ),
        StrategyHint(
            "mega_starmie.promote_the_cinderace_wall",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", None),
                ActivationCondition(f"own.card.{CINDERACE}.in_play", "eq", True),
                ActivationCondition(f"own.card.{MEGA_STARMIE_EX}.in_play", "missing"),
            ),
            (DesiredFact("promote", f"own.body.card:{CINDERACE}:first",
                         target_card_ids=(CINDERACE,)),),
            f"own.body.card:{CINDERACE}:first", "this_turn", "medium",
            "mega_starmie.strategy",
            bundle_id=PROMOTE_WINCON,
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
