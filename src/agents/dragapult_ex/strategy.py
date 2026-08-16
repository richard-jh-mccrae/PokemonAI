"""Dragapult ex declarations for the shared Bellman runtime."""

from common.strategy import ActivationCondition, DesiredFact, Roles, Strategy, StrategyHint


DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUNSPARCE, BUDEW = 305, 235
NIGHT_STRETCHER, CRUSHING_HAMMER = 1097, 1120
BOSS_ORDERS, CRISPIN, RISKY_RUINS = 1182, 1198, 1260
FIRE_ENERGY = 2


ROLES = Roles({
    DREEPY: ["primary_attacker"],
    DRAKLOAK: ["primary_attacker"],
    DRAGAPULT_EX: ["primary_attacker"],
}, ready={DRAGAPULT_EX: 2})


STRATEGY = Strategy(
    name="dragapult_ex",
    roles=ROLES,
    starter_priority=(BUDEW, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, DREEPY, MEOWTH_EX),
    params={"preferred_start": "second"},
    strategies=(
        StrategyHint(
            "dragapult.fund_active_phantom_dive", "deck",
            (ActivationCondition("own.active.card_id", "eq", DRAGAPULT_EX),
             ActivationCondition("own.active.attack_ready", "eq", False)),
            (DesiredFact("fund_attack", "own.active", target_card_ids=(FIRE_ENERGY,)),),
            "own.active", "immediate", "high", "dragapult_ex.strategy",
            bundle_id="dragapult.phantom_dive", waypoint=0,
        ),
        StrategyHint(
            "dragapult.pressure_benched_primary", "deck",
            (ActivationCondition("own.active.card_id", "eq", DRAGAPULT_EX),),
            (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
            "opponent.bench.highest_role", "immediate", "high",
            "dragapult_ex.strategy", bundle_id="dragapult.phantom_dive", waypoint=2,
        ),
    ),
)
