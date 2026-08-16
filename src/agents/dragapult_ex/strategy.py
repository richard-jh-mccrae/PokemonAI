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

PHANTOM_DIVE = "dragapult.phantom_dive"
DRAKLOAK_BODY = f"own.body.card:{DRAKLOAK}:first"
DUNSPARCE_BODY = f"own.body.card:{DUNSPARCE}:first"


def _hint(identifier, kind, recipient, *, conditions=(), targets=(), deadline="this_turn",
          confidence="high", bundle_id=None, waypoint=0):
    return StrategyHint(
        f"dragapult.{identifier}", "deck", tuple(conditions),
        (DesiredFact(kind, recipient, target_card_ids=tuple(targets)),),
        recipient, deadline, confidence, "dragapult_ex.strategy",
        bundle_id=bundle_id, waypoint=waypoint,
    )


ROLES = Roles({
    DREEPY: ["primary_attacker"],
    DRAKLOAK: ["primary_attacker"],
    DRAGAPULT_EX: ["primary_attacker"],
    MUNKIDORI: ["backup_attacker", "counter_mover"],
    FEZANDIPITI_EX: ["backup_attacker", "draw_engine"],
    DUNSPARCE: ["draw_engine", "retreat_assist"],
    DUDUNSPARCE: ["draw_engine"],
    BUDEW: ["item_locker"],
    MEOWTH_EX: ["search_engine"],
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
    # Deadline separates WHEN a need is lost; conviction separates HOW MUCH the doctrine wants it.
    # Both must span their range: a beam whose every hint is immediate/high ranks nothing, and
    # leaves the ordering to whatever tie-break sits underneath.
    strategies=(
        # --- The Phantom Dive line: taken now or lost. -------------------------------------
        _hint("fund_active_phantom_dive", "fund_attack", "own.active",
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", DRAGAPULT_EX),
                  ActivationCondition("own.active.attack_ready", "eq", False),
              ), deadline="immediate", bundle_id=PHANTOM_DIVE, waypoint=0),
        _hint("evolve_ready_drakloak", "evolve", DRAKLOAK_BODY,
              conditions=(
                  ActivationCondition(f"own.card.{DRAKLOAK}.energy_count", "ge", 2),
                  ActivationCondition("turn.ability.card_ids", "not_contains", DRAKLOAK),
              ), targets=(DRAGAPULT_EX,), deadline="immediate",
              bundle_id=PHANTOM_DIVE, waypoint=1),
        # Gated on the opponent's bench, not on ours: a turn that evolves Drakloak and THEN
        # attacks must still carry this hint, and activation is fixed at the epoch boundary.
        _hint("phantom_dive_damage_setup", "damage_setup",
              "opponent.bench.highest_role", targets=(DRAGAPULT_EX,),
              conditions=(ActivationCondition(
                  "opponent.bench.role_target_count", "gt", 0),),
              deadline="immediate", bundle_id=PHANTOM_DIVE, waypoint=2),
        # A gust only converts when the target is already inside Phantom Dive's reach.
        _hint("boss_softened_two_prize_target", "play_card",
              "opponent.bench.highest_role",
              conditions=(ActivationCondition(
                  "opponent.bench.softened_multi_prize_count", "gt", 0),),
              targets=(BOSS_ORDERS,), deadline="immediate"),

        # --- Fuelling the line. Energy on the Drakloak that is about to become the payoff is
        # --- worth as much as energy on the active; only the active had a funding hint before.
        _hint("fund_evolving_drakloak", "fund_attack", DRAKLOAK_BODY,
              conditions=(
                  ActivationCondition(f"own.card.{DRAKLOAK}.in_play", "eq", True),
                  ActivationCondition(f"own.card.{DRAKLOAK}.energy_count", "lt", 2),
              )),
        # Two board shapes, one desired outcome: Crispin's recipient does not select the action,
        # so both declare the same outcome and are deduplicated to a single unit of coverage.
        _hint("crispin_fuel_the_line", "play_card", "own.active",
              conditions=(ActivationCondition(f"own.card.{DRAKLOAK}.in_play", "eq", True),),
              targets=(CRISPIN,)),
        _hint("crispin_fuel_the_payoff", "play_card", "own.active",
              conditions=(ActivationCondition(f"own.card.{DRAGAPULT_EX}.in_play", "eq", True),),
              targets=(CRISPIN,)),

        # --- Development. Wanted every turn, but never at the cost of a closing attack. ------
        _hint("establish_benched_dreepy", "deploy", "own.bench", targets=(DREEPY,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),)),
        _hint("establish_benched_munkidori", "deploy", "own.bench", targets=(MUNKIDORI,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),),
              confidence="medium"),
        _hint("establish_benched_dunsparce", "deploy", "own.bench", targets=(DUNSPARCE,),
              conditions=(ActivationCondition("own.bench.space", "gt", 0),),
              confidence="low"),
        _hint("evolve_dunsparce_draw_line", "evolve", DUNSPARCE_BODY,
              conditions=(ActivationCondition(f"own.card.{DUNSPARCE}.in_play", "eq", True),),
              targets=(DUDUNSPARCE,), confidence="low"),
        _hint("evolve_threatened_drakloak", "evolve", DRAKLOAK_BODY,
              conditions=(ActivationCondition(
                  f"own.card.{DRAKLOAK}.hp_fraction", "lt", 0.75),),
              targets=(DRAGAPULT_EX,), confidence="medium"),

        # --- Situational answers. Each is gated on the board that makes it true, so it stops
        # --- claiming the search's attention on every other turn. ---------------------------
        _hint("unfair_stamp_before_draw", "play_card", "own.active",
              conditions=(ActivationCondition("turn.pokemon_ko_window", "eq", True),),
              targets=(UNFAIR_STAMP,), deadline="immediate", confidence="medium"),
        _hint("fezandipiti_bench_snipe_fallback", "damage_setup",
              "opponent.bench.highest_role",
              conditions=(ActivationCondition(
                  "own.active.card_id", "eq", FEZANDIPITI_EX),),
              targets=(FEZANDIPITI_EX,), confidence="medium"),
        _hint("risky_ruins_counter_loop", "play_card", "own.bench",
              conditions=(
                  ActivationCondition(f"own.card.{MUNKIDORI}.ability_ready", "eq", True),
                  ActivationCondition("own.bench.space", "gt", 0),
              ),
              targets=(RISKY_RUINS,), confidence="low"),
        _hint("promote_budew_wall", "promote", f"own.body.card:{BUDEW}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(BUDEW,), confidence="medium"),
        _hint("promote_dunsparce_pivot", "promote", DUNSPARCE_BODY,
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(DUNSPARCE,), confidence="low"),
    ),
)
