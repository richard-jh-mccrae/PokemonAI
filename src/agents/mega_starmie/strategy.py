"""mega_starmie — DECLARATIONS ONLY: this deck carries ZERO deck Hypotheses. Every rule it ever
authored was FOLDED into the General Strategy, keyed on the Roles / Lines / params below, so any deck
making the same declarations inherits the play. Weights stay ladder-tuned by id (ADR-0009).

Architecture: docs/agent-architecture.md.
Turbo Mega Starmie ex: open Cinderace (Explosiveness), Turbo Flare to load the Bench, tutor + evolve
Staryu -> Mega Starmie ex, then fire Nebula Beam (one Ignition Energy on an Evolution = CCC).
"""
from common.strategy import Line, Strategy

# Card ids — mega_starmie/deck.csv.
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

# Sparse Role overlay on the universal Function Tags — the deck's opt-in to the role-keyed general rules.
ROLES = {
    MEGA_STARMIE_EX: ["win_condition", "primary_attacker"],
    CINDERACE: ["accel_source"],                # Explosiveness opener + Turbo Flare
    # RETIRED 2026-07-28, ADR-0079: the `starter` Role on Cinderace + Staryu. Naming the openers is
    # `starter_priority` below; Cinderace keeps `accel_source`, Staryu is carried by the Line.
    IGNITION_ENERGY: ["accel_source"],           # CCC on an Evolution = one-attach Nebula Beam
    MEGA_SIGNAL: ["tutor"], SALVATORE: ["tutor"], HILDA: ["tutor"],
    BUDDY_POFFIN: ["tutor"], ULTRA_BALL: ["tutor"],
    CRUSHING_HAMMER: ["disruption"], BOSS_ORDERS: ["gust"],
    WALLYS: ["recovery"], NIGHT_STRETCHER: ["recovery"],
}

STRATEGY = Strategy(
    name="mega_starmie",
    lines=[Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX,
                role="win_condition")],   # no Ready() override: engine-derived at 1 {W} (Jetting Blow)
    roles=ROLES,
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Staryu is the Line base and wants
    # the BENCH, evolving behind the Cinderace wall rather than sitting in the most-exposed slot.
    starter_priority=[CINDERACE, STARYU],
    params={"setup_energy_target": 3,    # Nebula Beam's CCC
            "search_budget": 0,           # INERT since ADR-0064 deleted Tier-6 escalation, its only
                                          # consumer; held at 0 to keep the manifest Tier-0 (test-pinned).
            "my_archetype": "Cinderace / Mega Starmie ex",   # Posture favorability key (ADR-0026 lever A)
            "reactivity": "solitaire",    # UNCONSUMED since Issue #386 deleted its one reader (the
                                          # planner's forgo-KO rung). A declaration, not a live lever.
            "preferred_start": "second"},  # turbo: attack T1
    hypotheses=[],                        # empty BY DESIGN — every rule folded into the general layer
)
