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
DRAKLOAK_BODY = f"own.body.card:{DRAKLOAK}:readiest"
#: Protection is about the copy in the WORST shape. Naming the readiest one evolves a healthy
#: Drakloak while the threatened one, which is why the hint activated, still dies.
THREATENED_DRAKLOAK = f"own.body.card:{DRAKLOAK}:weakest"
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
        # Drakloak is held, not raced through. Evolving spends a draw engine and puts a
        # two-prize body on the board, and the evolution can be made on the very turn it
        # attacks -- so it is wanted only once the line has no payoff of its own and the
        # Energy to swing is already down. A Dragapult ex in play means the job is taken:
        # the benched Drakloak keeps drawing instead.
        _hint("evolve_drakloak_for_the_attack", "evolve", DRAKLOAK_BODY,
              conditions=(
                  ActivationCondition(f"own.card.{DRAGAPULT_EX}.in_play", "missing"),
                  ActivationCondition(f"own.card.{DRAKLOAK}.energy_count", "ge", 2),
              ), targets=(DRAGAPULT_EX,), deadline="immediate",
              bundle_id=PHANTOM_DIVE, waypoint=1),
        # Adrena-Brain and Phantom Dive are one play, not two: counters moved off our own hurt
        # bodies land on the opponent's bench, and the attack's six counters then finish what
        # they started while the 200 still lands on the Active. Same bundle, ahead of the swing.
        _hint("munkidori_counters_into_the_spread", "use_ability",
              f"own.body.card:{MUNKIDORI}:first",
              conditions=(
                  ActivationCondition("turn.ability.card_ids", "contains", MUNKIDORI),
                  ActivationCondition("own.damaged_count", "gt", 0),
                  ActivationCondition("opponent.bench.role_target_count", "gt", 0),
              ), targets=(MUNKIDORI,), deadline="immediate",
              bundle_id=PHANTOM_DIVE, waypoint=2),
        # Gated on the opponent's bench, not on ours: a turn that evolves Drakloak and THEN
        # attacks must still carry this hint, and activation is fixed at the epoch boundary.
        _hint("phantom_dive_damage_setup", "damage_setup",
              "opponent.bench.highest_role", targets=(DRAGAPULT_EX,),
              conditions=(ActivationCondition(
                  "opponent.bench.role_target_count", "gt", 0),),
              deadline="immediate", bundle_id=PHANTOM_DIVE, waypoint=3),
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
        # The other reason to evolve: 90 HP becomes 320 and the damage already on it stops
        # being lethal. Worth it even while a Dragapult ex is already attacking, because
        # losing the Drakloak loses the line behind it.
        _hint("evolve_threatened_drakloak", "evolve", THREATENED_DRAKLOAK,
              conditions=(ActivationCondition(
                  f"own.card.{DRAKLOAK}.hp_fraction", "lt", 0.75),),
              targets=(DRAGAPULT_EX,), confidence="medium"),

        # --- Situational answers. Each is gated on the board that makes it true, so it stops
        # --- claiming the search's attention on every other turn. ---------------------------
        _hint("unfair_stamp_before_draw", "play_card", "own.active",
              conditions=(ActivationCondition("turn.pokemon_ko_window", "eq", True),),
              targets=(UNFAIR_STAMP,), deadline="immediate", confidence="medium"),
        # Cruel Arrow is a pinch attack, not a plan: it costs two prizes if Fezandipiti falls.
        # Wanted only while no Dragapult ex is on the board at all, so a turn that could promote
        # or evolve into the real attacker is never spent shooting with the fallback.
        _hint("fezandipiti_bench_snipe_fallback", "damage_setup",
              "opponent.bench.highest_role",
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", FEZANDIPITI_EX),
                  ActivationCondition(f"own.card.{DRAGAPULT_EX}.in_play", "missing"),
              ),
              targets=(FEZANDIPITI_EX,), confidence="low"),
        _hint("risky_ruins_counter_loop", "play_card", "own.bench",
              conditions=(
                  ActivationCondition(f"own.card.{MUNKIDORI}.ability_ready", "eq", True),
                  ActivationCondition("own.bench.space", "gt", 0),
              ),
              targets=(RISKY_RUINS,), confidence="low"),
        # A standing Dragapult ex outranks every other replacement: it is the attacker the
        # whole line was built to raise, and promoting anything past it wastes the build.
        _hint("promote_readiest_dragapult", "promote",
              f"own.body.card:{DRAGAPULT_EX}:readiest",
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", None),
                  ActivationCondition(f"own.card.{DRAGAPULT_EX}.in_play", "eq", True),
              ), targets=(DRAGAPULT_EX,)),
        # Two Drakloak on the board are not interchangeable: promote the one holding Energy at
        # full health, use its Ability, evolve it. The hurt one stays benched, keeps drawing,
        # and is what Munkidori's counter-move is for.
        _hint("promote_readiest_drakloak", "promote", DRAKLOAK_BODY,
              conditions=(
                  ActivationCondition("own.active.card_id", "eq", None),
                  ActivationCondition(f"own.card.{DRAKLOAK}.in_play", "eq", True),
              ), targets=(DRAKLOAK,)),
        _hint("promote_budew_wall", "promote", f"own.body.card:{BUDEW}:first",
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(BUDEW,), confidence="medium"),
        _hint("promote_dunsparce_pivot", "promote", DUNSPARCE_BODY,
              conditions=(ActivationCondition("own.active.card_id", "eq", None),),
              targets=(DUNSPARCE,), confidence="low"),
    ),
)
