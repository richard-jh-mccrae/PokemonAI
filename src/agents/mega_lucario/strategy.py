"""Mega Lucario declarations for the shared Bellman runtime."""

from common.strategy import PrizePlan, Roles, Strategy


RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071


ROLES = Roles({
    MEGA_LUCARIO_EX: ["primary_attacker", "accel_source"],
    SOLROCK: ["secondary_attacker"],
    HARIYAMA: ["secondary_attacker"],
})


STRATEGY = Strategy(
    name="mega_lucario",
    roles=ROLES,
    starter_priority=(SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX),
    prize_plan=PrizePlan(routes=(
        (SOLROCK, MEGA_LUCARIO_EX, HARIYAMA, MEGA_LUCARIO_EX),
    )),
    params={"preferred_start": "first"},
)
