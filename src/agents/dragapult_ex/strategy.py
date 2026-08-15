"""Dragapult ex declarations for the shared Bellman runtime."""

from common.strategy import Roles, Strategy


DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUNSPARCE, BUDEW = 305, 235
NIGHT_STRETCHER, CRUSHING_HAMMER = 1097, 1120
BOSS_ORDERS, CRISPIN, RISKY_RUINS = 1182, 1198, 1260


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
)
