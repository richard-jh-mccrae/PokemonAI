"""Dragapult ex declarations for the shared Bellman runtime."""

from common.strategy import (
    ActivationCondition, DesiredFact, Roles, Strategy, StrategyHint, StrategyOverride,
)
from agents.dragapult_ex.potential import DragapultPotential


DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUDUNSPARCE, DUNSPARCE, BUDEW = 66, 305, 235
NIGHT_STRETCHER, CRUSHING_HAMMER = 1097, 1120
BOSS_ORDERS, CRISPIN, RISKY_RUINS = 1182, 1198, 1260
UNFAIR_STAMP = 1080


def _hint(identifier, kind, recipient, *, conditions=(), targets=(), deadline="this_turn",
          confidence="high"):
    return StrategyHint(
        f"dragapult.{identifier}", "deck", tuple(conditions),
        (DesiredFact(kind, recipient, target_card_ids=tuple(targets)),),
        recipient, deadline, confidence, "dragapult_ex.strategy",
    )


ROLES = Roles({
    DREEPY: ["primary_attacker"],
    DRAKLOAK: ["primary_attacker"],
    DRAGAPULT_EX: ["primary_attacker"],
    MUNKIDORI: ["backup_attacker", "counter_mover"],
    FEZANDIPITI_EX: ["backup_attacker", "draw_engine"],
    DUNSPARCE: ["draw_engine", "pivot"],
    DUDUNSPARCE: ["draw_engine", "pivot"],
    BUDEW: ["item_locker", "pivot"],
    MEOWTH_EX: ["support", "supporter_tutor"],
}, ready={DRAGAPULT_EX: 2})


STRATEGY = Strategy(
    name="dragapult_ex",
    roles=ROLES,
    starter_priority=(BUDEW, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, DREEPY, MEOWTH_EX),
    partners={MUNKIDORI: (RISKY_RUINS,)},
    worth_overrides={RISKY_RUINS: 10.0},
    params={
        "preferred_start": "second",
        "prize_path": "flexible_best_available",
        "use_general_card_strategies": True,
    },
    potential_factory=DragapultPotential,
    strategy_overrides=(
        StrategyOverride(
            "general.evolve_active_attacker",
            additional_conditions=(ActivationCondition("own.active.card_id", "ne", DRAKLOAK),),
        ),
    ),
    strategies=(
        _hint("establish_benched_dreepy", "deploy", "own.bench", targets=(DREEPY,)),
        _hint("establish_benched_munkidori", "deploy", "own.bench", targets=(MUNKIDORI,)),
        _hint("establish_benched_dunsparce", "deploy", "own.bench", targets=(DUNSPARCE,)),
        _hint("risky_ruins_counter_loop", "play_card", "own.bench",
              conditions=(
                  ActivationCondition(f"own.card.{MUNKIDORI}.ability_ready", "eq", True),
                  ActivationCondition("own.bench.space", "gt", 0),
              ),
              targets=(RISKY_RUINS,)),
        _hint("preserve_drakloak_draw_engine", "use_ability",
              f"own.body.card:{DRAKLOAK}:first",
              conditions=(ActivationCondition("turn.ability.card_ids", "contains", DRAKLOAK),),
              targets=(DRAKLOAK,), deadline="immediate"),
        _hint("evolve_ready_drakloak", "evolve", f"own.body.card:{DRAKLOAK}:first",
              conditions=(
                  ActivationCondition(f"own.card.{DRAKLOAK}.energy_count", "ge", 2),
                  ActivationCondition("turn.ability.card_ids", "not_contains", DRAKLOAK),
              ), targets=(DRAGAPULT_EX,)),
        _hint("evolve_threatened_drakloak", "evolve", f"own.body.card:{DRAKLOAK}:first",
              conditions=(ActivationCondition(
                  f"own.card.{DRAKLOAK}.hp_fraction", "lt", 0.75),),
              targets=(DRAGAPULT_EX,), confidence="medium"),
        _hint("phantom_dive_damage_setup", "damage_setup",
              "opponent.bench.highest_role", targets=(DRAGAPULT_EX,)),
        _hint("boss_softened_two_prize_target", "play_card",
              "opponent.bench.highest_role",
              conditions=(ActivationCondition(
                  "opponent.bench.softened_multi_prize_count", "gt", 0),),
              targets=(BOSS_ORDERS,)),
        _hint("crispin_dragapult_acceleration", "play_card",
              f"own.body.card:{DRAKLOAK}:first",
              conditions=(ActivationCondition(f"own.card.{DRAKLOAK}.in_play", "eq", True),),
              targets=(CRISPIN,)),
        _hint("crispin_munkidori_fallback", "play_card",
              f"own.body.card:{MUNKIDORI}:first",
              conditions=(ActivationCondition(f"own.card.{MUNKIDORI}.in_play", "eq", True),),
              targets=(CRISPIN,), confidence="medium"),
        _hint("crispin_fezandipiti_fallback", "play_card",
              f"own.body.card:{FEZANDIPITI_EX}:first",
              conditions=(ActivationCondition(f"own.card.{FEZANDIPITI_EX}.in_play", "eq", True),),
              targets=(CRISPIN,), confidence="medium"),
        _hint("fezandipiti_bench_snipe_fallback", "damage_setup",
              "opponent.bench.highest_role", targets=(FEZANDIPITI_EX,), confidence="medium"),
        _hint("unfair_stamp_before_draw", "play_card", "own.active",
              targets=(UNFAIR_STAMP,), deadline="immediate"),
        _hint("promote_dunsparce_pivot", "promote", f"own.body.card:{DUNSPARCE}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(DUNSPARCE,), confidence="medium"),
        _hint("promote_budew_wall", "promote", f"own.body.card:{BUDEW}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(BUDEW,), confidence="medium"),
    ),
)
