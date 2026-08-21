"""Mega Starmie deck declarations for the shared runtime."""

from common.strategy import PrizePlan, Roles, Strategy


STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666


ROLES = Roles({
    MEGA_STARMIE_EX: ["primary_attacker"],
    STARYU: ["primary_attacker"],
    CINDERACE: ["backup_attacker", "accel_source"],
})


STRATEGY = Strategy(
    name="mega_starmie",
    roles=ROLES,
    ledger_overlay={"demand.dead": 0.15, "kind.special_energy": 0.05,
                    "energy.concentration": 0.02},
    starter_priority=(CINDERACE, STARYU),
    prize_plan=PrizePlan(routes=(
        (CINDERACE, MEGA_STARMIE_EX, MEGA_STARMIE_EX),
        (MEGA_STARMIE_EX, CINDERACE, MEGA_STARMIE_EX),
    )),
    params={"preferred_start": "second"},
)
