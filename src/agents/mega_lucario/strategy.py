"""Mega Lucario declarations for the shared Bellman runtime."""

from common.strategy import Roles, Strategy


RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071
FIGHTING_GONG, BOSS_ORDERS, AIR_BALLOON = 1142, 1182, 1174


ROLES = Roles({
    MEGA_LUCARIO_EX: ["primary_attacker", "accel_source"],
    SOLROCK: ["backup_attacker", "engine"],
    LUNATONE: ["engine"],
    HARIYAMA: ["backup_attacker"],
    MEOWTH_EX: ["engine"],
})


STRATEGY = Strategy(
    name="mega_lucario",
    roles=ROLES,
    partners={SOLROCK: (LUNATONE,), LUNATONE: (SOLROCK,)},
    starter_priority=(SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX),
    params={"preferred_start": "first"},
)
