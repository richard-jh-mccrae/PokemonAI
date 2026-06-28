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
_TO_HAND = 7        # SelectContext.TO_HAND — a search: choose which card to take into hand
_IS_FIRST = 41      # SelectContext.IS_FIRST — the coin-toss "Would you like to go first?" (YesNo)
_PLAY, _ATTACH = 7, 8  # OptionType — board-commit options (vs a search/ToHand card sub-selection)
_YES = 1            # OptionType.YES — the affirmative at a YesNo select
_ACTIVE = 4         # AreaType.ACTIVE — an attach onto the Active Spot
_WINCON_ROLES = {"win_condition", "primary_attacker"}

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
                  "`fetch-the-wincon` / `fetch-energy-when-starved` in common/general_strategy.py.) "
                  "Stands down once the win-condition is already in hand — no need to dig for a copy "
                  "you're holding.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "tutor" in c.roles
        and not c.board.wincon_in_hand,
        weight=25, status="assumed"),
    Hypothesis(
        id="prefer-going-second",
        rationale="This turbo deck wants to attack as early as possible: at the coin toss, decline "
                  "to go first. The player going first cannot attack on their first turn, and going "
                  "first also risks an unusable end-of-turn Ignition Energy — so going second "
                  "(attacking turn one) is the stronger line for a deck that sprints its attacker "
                  "online. Deck-specific (setup-heavy decks prefer first), so it lives here, not in "
                  "the General Strategy.",
        when=lambda c: c.select_context == _IS_FIRST and c.option_type == _YES,
        weight=-30, status="assumed"),
    Hypothesis(
        id="never-fetch-cinderace",
        rationale="Cinderace can only enter play via its Explosiveness Ability at game start (no "
                  "Raboot line in this deck), so a fetched copy is a dead card. At a search, never "
                  "take an `opener`-tagged setup-only Pokémon into hand — pull the win-condition "
                  "line piece instead. Reads the universal `opener` tag, so it generalises to any "
                  "setup-only opener; gated to a search (TO_HAND), so it never touches the legitimate "
                  "open-Cinderace-as-the-Active choice during setup.",
        when=lambda c: c.select_context == _TO_HAND and "opener" in c.tags,
        weight=-60, status="assumed"),
    Hypothesis(
        id="conserve-ignition-prefer-water",
        rationale="Ignition Energy is a finite, non-recyclable burst (4 copies, discarded each turn, "
                  "not recoverable by Night Stretcher); its only value is the one-attach CCC that "
                  "powers Nebula Beam. So don't spend it when the cheaper Jetting Blow already does "
                  "the job: if the Active win-condition's cheapest attack would already Knock Out the "
                  "opponent's Active AND a reusable Water is in hand, attach the Water (and Jetting "
                  "Blow) instead, saving the Ignition for a turn that genuinely needs the 210 / "
                  "ignore-effects. When the cheap attack CAN'T KO, Nebula is needed, so this stands "
                  "down — it never blocks the Ignition you actually need (the greedy '>=2 Ignition' "
                  "case is subsumed: if the cheap attack KOs, Nebula never gets ahead). Complements "
                  "the general `dont-waste-discard-energy`, which exempts the win-condition.",
        when=lambda c: c.option_type == _ATTACH and "discard_eot" in c.tags
        and c.attach_target_area == _ACTIVE and bool(_WINCON_ROLES & set(c.attach_target_roles))
        and c.board.reusable_energy_in_hand and c.board.active_cheap_attack_kos,
        weight=-40, status="assumed"),
    # NOTE: Hero's Cape (ACE SPEC, +100 HP) deployment is now the deck-agnostic
    # `deploy-hp-tool-on-breakpoint` in common/general_strategy.py — it reads the per-Tool HP off
    # `CardStat.hpBonus` (parsed +100 for the Cape) and the weakness-aware `incoming_active_damage`,
    # so every deck running an unconditional +HP Tool inherits the breakpoint deploy without
    # hardcoding the bonus. The ACE SPEC scarcity reluctance is the general `protect-ace-spec-tool`.
    # NOTE: discard-Energy discipline (don't waste Ignition) is the deck-agnostic
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
