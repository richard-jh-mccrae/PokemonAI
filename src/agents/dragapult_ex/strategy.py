"""Dragapult ex deck declarations for the shared runtime."""

from common.strategy import Roles, Strategy


DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUDUNSPARCE, DUNSPARCE, BUDEW = 66, 305, 235
RISKY_RUINS = 1260


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
    params={"preferred_start": "second", "prize_path": "flexible_best_available"},
)
