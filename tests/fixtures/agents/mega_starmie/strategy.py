"""mega_starmie — Strategy test fixture (mirrors src/agents/mega_starmie/strategy.py).

Turbo Mega Starmie ex as DECLARATIONS ONLY: Lines / Roles / params, ZERO deck Hypotheses —
the play lives in the General Strategy, keyed on these declarations (the 2026-07-02 fold;
see the real file's docstring for the deck-rule -> general-rule table). Pure data, lib-free.
"""
from common.strategy import Line, Strategy

# --- Card ids (mega_starmie/deck.csv) -------------------------------------
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

# Per-deck Role overlay on universal Function Tags (sparse — only deck-intentional cards).
# Roles ARE the deck's opt-in to the role-keyed General Strategy rules.
ROLES = {
    MEGA_STARMIE_EX: ["win_condition", "primary_attacker"],
    CINDERACE: ["accel_source"],                # Explosiveness opener + Turbo Flare
    # (the `starter` Role was retired by ADR-0075; the openers are STRATEGY.starter_priority below)
    IGNITION_ENERGY: ["accel_source"],           # CCC on an Evolution = one-attach Nebula Beam
    MEGA_SIGNAL: ["tutor"], SALVATORE: ["tutor"], HILDA: ["tutor"],
    BUDDY_POFFIN: ["tutor"], ULTRA_BALL: ["tutor"],
    CRUSHING_HAMMER: ["disruption"], BOSS_ORDERS: ["gust"],
    WALLYS: ["recovery"], NIGHT_STRETCHER: ["recovery"],
}

STRATEGY = Strategy(
    name="mega_starmie",
    lines=[Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX,
                role="win_condition")],   # readiness engine-derived: online at 1 W (Jetting Blow), not CCC
    roles=ROLES,
    # The deck's ordered opening bodies (ADR-0075) — mirrors the shipped agent so this fixture keeps
    # exercising the declaration-keyed `open-the-declared-starter` at the Set-Up Active pick.
    starter_priority=[CINDERACE, STARYU],
    params={"setup_energy_target": 3,    # aspirational target (Nebula Beam CCC) — future attach-priority
            "search_budget": 0,           # 0 = Tier-0 closed-form combat; >0 = Tier-1 Search (ADR-0019)
            "preferred_start": "second"},  # turbo: attack T1 -> general `honor-preferred-start`
    hypotheses=[],                        # empty by design — declarations drive General Strategy
)
