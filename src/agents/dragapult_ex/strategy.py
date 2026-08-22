"""Dragapult ex deck declarations for the shared runtime."""

from common.strategy import PrizePlan, Roles, Strategy


DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUDUNSPARCE, DUNSPARCE, BUDEW = 66, 305, 235
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
})


STRATEGY = Strategy(
    name="dragapult_ex",
    roles=ROLES,
    starter_priority=(BUDEW, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, DREEPY, MEOWTH_EX),
    prize_plan=PrizePlan(),
    params={"preferred_start": "second"},
)
