"""mega_starmie — Strategy (declarative doctrine). See docs/agent-architecture.md.

Turbo Mega Starmie ex: open Cinderace (Explosiveness), Turbo Flare to load the bench,
tutor + evolve Staryu -> Mega Starmie ex, then fire Nebula Beam (one Ignition Energy on an
Evolution = CCC). Weights are seed values, every Hypothesis status="assumed" — to be
ladder-tuned and corrected (ADR-0009). Pure data: no engine, no control flow.
"""
from common.strategy import Hypothesis, Line, Plan, Strategy

# --- Card ids (mega_starmie/deck.csv) -------------------------------------
STARYU, MEGA_STARMIE_EX, CINDERACE = 1030, 1031, 666
WATER_ENERGY, IGNITION_ENERGY = 3, 17
MEGA_SIGNAL, BUDDY_POFFIN, SALVATORE, HILDA, ULTRA_BALL = 1145, 1086, 1189, 1225, 1121
CRUSHING_HAMMER, BOSS_ORDERS, WALLYS, NIGHT_STRETCHER = 1120, 1182, 1229, 1097

_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON (cg/api.py)
_PLAY, _ATTACH = 7, 8  # OptionType — board-commit options (vs a search/ToHand card sub-selection)

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards).
ROLES = {
    MEGA_STARMIE_EX: ["win_condition", "primary_attacker"],
    CINDERACE: ["accel_source", "starter"],     # Explosiveness opener + Turbo Flare
    STARYU: ["starter"],
    IGNITION_ENERGY: ["accel_source"],           # CCC on an Evolution = one-attach Nebula Beam
    MEGA_SIGNAL: ["tutor"], SALVATORE: ["tutor"], HILDA: ["tutor"],
    BUDDY_POFFIN: ["tutor"], ULTRA_BALL: ["tutor"],
    CRUSHING_HAMMER: ["disruption"], BOSS_ORDERS: ["gust"],
    WALLYS: ["recovery"], NIGHT_STRETCHER: ["recovery"],
}

HYPOTHESES = [
    Hypothesis(
        id="open-cinderace",
        rationale="Cinderace's Explosiveness lets it open the Active Spot; Turbo Flare then "
                  "accelerates from turn one — prefer it over Staryu as the opener.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _SETUP_ACTIVE
        and "accel_source" in c.roles,
        weight=40, status="assumed"),
    Hypothesis(
        id="accel-into-main",
        rationale="Rush energy onto the Mega Starmie ex line as fast as possible.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type in (_PLAY, _ATTACH)
        and "accel_source" in c.roles,
        weight=30, status="assumed"),
    Hypothesis(
        id="tutor-the-wincon",
        rationale="During setup, dig for the win-condition pieces (Mega Signal / Salvatore / Hilda) "
                  "by playing a tutor. (Choosing WHICH card a search pulls is the deck-agnostic "
                  "`fetch-the-wincon` / `fetch-energy-when-starved` in common/general_strategy.py.)",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "tutor" in c.roles,
        weight=25, status="assumed"),
    # NOTE: discard-Energy discipline (don't waste Ignition) is now the deck-agnostic
    # `dont-waste-discard-energy` in common/general_strategy.py — it fires off the `discard_eot`
    # Function Tag, so every deck that runs Ignition (or any discard-at-EOT Energy) inherits it.
]

STRATEGY = Strategy(
    name="mega_starmie",
    lines=[Line(path=[STARYU, MEGA_STARMIE_EX], payoff=MEGA_STARMIE_EX,
                role="win_condition")],   # readiness engine-derived: online at 1 W (Jetting Blow), not CCC
    roles=ROLES,
    params={"setup_energy_target": 3,    # aspirational target (Nebula Beam CCC) — future attach-priority
            "search_budget": 0},          # 0 = Tier-0 closed-form combat; >0 = Tier-1 Search (ADR-0019)
    hypotheses=HYPOTHESES,
)
