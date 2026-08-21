"""Mega Lucario deck declarations for the shared runtime."""

from common.strategy import Roles, Strategy


RIOLU, MEGA_LUCARIO_EX = 677, 678
MAKUHITA, HARIYAMA = 673, 674
SOLROCK, LUNATONE, MEOWTH_EX = 676, 675, 1071


ROLES = Roles({
    RIOLU: ["primary_attacker"],
    MEGA_LUCARIO_EX: ["primary_attacker", "accel_source"],
    SOLROCK: ["backup_attacker", "support_pokemon"],
    LUNATONE: ["draw_engine"],
    MAKUHITA: ["backup_attacker"],
    HARIYAMA: ["backup_attacker"],
})


STRATEGY = Strategy(
    name="mega_lucario",
    roles=ROLES,
    partners={SOLROCK: (LUNATONE,), LUNATONE: (SOLROCK,)},
    starter_priority=(SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX),
    params={"preferred_start": "first"},
)
