"""mega_starmie — Strategy test fixture (mirrors src/agents/mega_starmie/strategy.py).

Turbo Mega Starmie ex as DECLARATIONS ONLY: Roles / prize plan / params, ZERO deck Hypotheses —
the play lives in the General Strategy, keyed on these declarations (the 2026-07-02 fold;
see the real file's docstring for the deck-rule -> general-rule table). Pure data, lib-free.
"""
from common.strategy import PrizePlan, Roles, Strategy

# --- Card ids (mega_starmie/deck.csv) -------------------------------------
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

# Per-deck Role overlay (sparse — only deck-intentional cards).
# Roles ARE the deck's opt-in to the role-keyed General Strategy rules.
ROLES = Roles({
    MEGA_STARMIE_EX: ["primary_attacker"],
    STARYU: ["primary_attacker"],
    CINDERACE: ["accel_source"],
})

STRATEGY = Strategy(
    name="mega_starmie",
    roles=ROLES,
    # The deck's ordered opening bodies (ADR-0079) — mirrors the shipped agent so this fixture keeps
    # exercising the declaration-keyed `open-the-declared-starter` at the Set-Up Active pick.
    starter_priority=[CINDERACE, STARYU],
    prize_plan=PrizePlan(routes=(
        (CINDERACE, MEGA_STARMIE_EX, MEGA_STARMIE_EX),
        (MEGA_STARMIE_EX, CINDERACE, MEGA_STARMIE_EX),
    )),
    params={"preferred_start": "second"},
)
