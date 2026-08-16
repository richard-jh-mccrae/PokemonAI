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

# One named outcome, whichever half of the pair is missing.
SOLROCK_PAIR = "mega_lucario.complete_the_solrock_pair"
GUST_EVOLUTION = "mega_lucario.evolve_into_the_gust"
# The wincon line, one waypoint at a time: body, Energy, evolution. One bundle so the line
# never spends more than one protected slot on itself.
LUCARIO_LINE = "mega_lucario.raise_the_lucario_line"
PROMOTE_WINCON = "mega_lucario.promote_the_wincon"
# Named, not `evolvable:first`: Riolu also evolves, so first-on-the-Bench binds the wrong body.
BENCHED_MAKUHITA = f"own.bench.card:{MAKUHITA}"
# `:readiest` keeps every stage of the line pointed at the same copy — the one already
# holding Energy — instead of whichever copy sits earliest on the Bench.
RIOLU_BODY = f"own.body.card:{RIOLU}:readiest"
LUCARIO_BODY = f"own.body.card:{MEGA_LUCARIO_EX}:readiest"

# Sparse deck intent. Meowth ex is absent on purpose: its Supporter tutor is a shared Card
# Function. Evolution relationships come from card facts, not from this table.
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
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Solrock opens: one Energy buys
    # 70 and it is not the primary line's base. Meowth ex last: a setup Active cannot use its draw.
    starter_priority=(SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX),
    # No `prize_plan`: a route also CAPS Worth per resource job at its own count, and this deck
    # plays three Solrock against a route naming one. Its −5 frame measurement is pre-guard-repair.
    # Card-fact hints mint from Function Tags: Lunatone's `draw` tag becomes the Lunar Cycle
    # use-Ability hint the deck otherwise never declares.
    params={"preferred_start": "first", "use_general_card_strategies": True},
    strategies=(
        # A Solrock without its partner cannot attack, so the pair outranks an ordinary bench
        # fill. One bundle across all three: one outcome must not spend both protected slots.
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
            bundle_id=SOLROCK_PAIR,
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
            bundle_id=SOLROCK_PAIR,
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
            bundle_id=SOLROCK_PAIR,
        ),
        # --- The wincon line. Bench a Riolu, put Energy on it, evolve it. Aura Jab (one
        # --- Energy, 130) then refunds the Bench from the discard, so the line pays for
        # --- itself once it is standing. Waypoints hold each stage until the last is done.
        StrategyHint(
            "mega_lucario.bench_a_riolu",
            "deck",
            (
                ActivationCondition("own.bench.card_ids", "not_contains", RIOLU),
                ActivationCondition("own.bench.space", "gt", 0),
            ),
            (DesiredFact("deploy", "own.bench", target_card_ids=(RIOLU,)),),
            "own.bench", "this_turn", "high", "mega_lucario.strategy",
            bundle_id=LUCARIO_LINE, waypoint=0,
        ),
        StrategyHint(
            "mega_lucario.fund_the_readiest_riolu",
            "deck",
            (ActivationCondition(f"own.card.{RIOLU}.in_play", "eq", True),),
            (DesiredFact("fund_attack", RIOLU_BODY),),
            RIOLU_BODY, "this_turn", "high", "mega_lucario.strategy",
            bundle_id=LUCARIO_LINE, waypoint=1,
        ),
        StrategyHint(
            "mega_lucario.evolve_riolu_into_mega_lucario",
            "deck",
            (ActivationCondition(f"own.card.{RIOLU}.in_play", "eq", True),),
            (DesiredFact("evolve", RIOLU_BODY, target_card_ids=(MEGA_LUCARIO_EX,)),),
            RIOLU_BODY, "this_turn", "high", "mega_lucario.strategy",
            bundle_id=LUCARIO_LINE, waypoint=2,
        ),
        # Mega Brave (270) reads two Energy; the second one wants to be down the turn BEFORE
        # the swing is needed. Unbundled: a standing Lucario funds while a new line rises.
        StrategyHint(
            "mega_lucario.fund_the_readiest_mega_lucario",
            "deck",
            (
                ActivationCondition(f"own.card.{MEGA_LUCARIO_EX}.in_play", "eq", True),
                ActivationCondition(f"own.card.{MEGA_LUCARIO_EX}.energy_count", "lt", 2),
            ),
            (DesiredFact("fund_attack", LUCARIO_BODY),),
            LUCARIO_BODY, "this_turn", "high", "mega_lucario.strategy",
        ),
        # --- After a loss the replacement is the wincon, not whatever stands nearest. A bare
        # --- Riolu goes up only when no Mega Lucario ex is in play to take the slot.
        StrategyHint(
            "mega_lucario.promote_the_readiest_mega_lucario",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", None),
                ActivationCondition(f"own.card.{MEGA_LUCARIO_EX}.in_play", "eq", True),
            ),
            (DesiredFact("promote", LUCARIO_BODY, target_card_ids=(MEGA_LUCARIO_EX,)),),
            LUCARIO_BODY, "this_turn", "high", "mega_lucario.strategy",
            bundle_id=PROMOTE_WINCON,
        ),
        StrategyHint(
            "mega_lucario.promote_a_riolu_to_grow",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", None),
                ActivationCondition(f"own.card.{RIOLU}.in_play", "eq", True),
                ActivationCondition(f"own.card.{MEGA_LUCARIO_EX}.in_play", "missing"),
            ),
            (DesiredFact("promote", RIOLU_BODY, target_card_ids=(RIOLU,)),),
            RIOLU_BODY, "this_turn", "medium", "mega_lucario.strategy",
            bundle_id=PROMOTE_WINCON,
        ),
        # Heave-Ho Catcher rides the evolution, so the Makuhita line is worth most on the turn the
        # opposing Bench holds something worth dragging out. Declared per position, one bundle:
        # the gust is one outcome and it does not care which slot the Makuhita stands in.
        StrategyHint(
            "mega_lucario.evolve_makuhita_for_the_gust",
            "deck",
            (
                ActivationCondition("own.active.card_id", "eq", MAKUHITA),
                ActivationCondition("opponent.bench.role_target_count", "gt", 0),
            ),
            (DesiredFact("evolve", "own.active", target_card_ids=(HARIYAMA,)),),
            "own.active", "this_turn", "high", "mega_lucario.strategy",
            bundle_id=GUST_EVOLUTION,
        ),
        StrategyHint(
            "mega_lucario.evolve_benched_makuhita_for_the_gust",
            "deck",
            (
                ActivationCondition("own.bench.card_ids", "contains", MAKUHITA),
                ActivationCondition("opponent.bench.role_target_count", "gt", 0),
            ),
            (DesiredFact("evolve", BENCHED_MAKUHITA, target_card_ids=(HARIYAMA,)),),
            BENCHED_MAKUHITA, "this_turn", "high", "mega_lucario.strategy",
            bundle_id=GUST_EVOLUTION,
        ),
    ),
)
