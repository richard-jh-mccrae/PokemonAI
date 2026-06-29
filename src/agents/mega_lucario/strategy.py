"""mega_lucario — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/mega_lucario/STRATEGY.md (the grilled playing doctrine, deck-genie 2026-06-29).

Flexible Fighting multi-attacker. Win-condition: Mega Lucario ex (Riolu -> Mega ex, single hop,
340 HP / 3 prizes) — alternate Mega Brave (FF 270) with Aura Jab (F 130 + load up to 3 Basic {F}
from discard onto the Bench, the deck's sole energy engine). The Solrock<->Lunatone pair is a
self-contained draw engine + early 70 attacker + discard-fuel source; Hariyama is the prize-trade
star (210 for 1 prize) + a free gust on evolve. Most of the doctrine is COVERED by the General
Strategy (see STRATEGY.md §5); this file holds only the deck-specific overlay (Roles, Line, params)
and the deck-specific Hypotheses. Pure data: no engine, no control flow. Weights are seeds
(status="assumed") — ladder-tuned (ADR-0009).
"""
from common.strategy import Hypothesis, Line, Plan, Strategy

# --- Card ids (mega_lucario/deck.csv; verified against the engine 2026-06-29) -------------
RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071
FIGHTING_ENERGY = 6
ULTRA_BALL, FIGHTING_GONG, POKE_PAD, PREMIUM_POWER_PRO, SWITCH = 1121, 1142, 1152, 1141, 1123
LILLIES, JUDGE, BOSS_ORDERS = 1227, 1213, 1182
MAX_BELT, AIR_BALLOON = 1158, 1174
WATCHTOWER, GRAVITY_MOUNTAIN = 1256, 1252

_TO_HAND = 7        # SelectContext.TO_HAND — a search: choose which card to take into hand

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards).
# Roles drive deck Hypotheses + the universal role-keyed general rules (win_condition exemptions etc.).
ROLES = {
    MEGA_LUCARIO_EX: ["win_condition", "primary_attacker"],
    RIOLU:    ["win_condition_base"],            # Line pre-evo (the Line drives line-piece rules)
    SOLROCK:  ["secondary_attacker", "engine"],  # early Cosmic Beam 70 + Lunar Cycle enabler
    LUNATONE: ["engine"],                         # native draw engine (Lunar Cycle, Ability)
    HARIYAMA: ["secondary_attacker", "gust"],     # prize-trade star (210/1-prize) + Heave-Ho gust
    MAKUHITA: ["evolution_base"],
    MEOWTH_EX: ["tutor"],                          # situational Last-Ditch Supporter fetch
    BOSS_ORDERS: ["gust"],                         # the `gust` TAG drives the shipped general doctrine
    MAX_BELT: ["damage_tool"],
    AIR_BALLOON: ["retreat_tool"],
}

HYPOTHESES = [
    Hypothesis(
        id="fetch-the-engine-first",
        rationale="In setup, a free tutor (Fighting Gong / Poké Pad) should prioritise the "
                  "Solrock + Lunatone ENGINE — the draw + early attacker that fuels Aura Jab — over "
                  "the rest of the line. Fetch an `engine`-Role piece first; the Riolu line / energy "
                  "follow. Seeded just above the general `prefer-wincon-line-piece` (Riolu, +18) so "
                  "the engine edges the line piece early; the payoff (Mega Lucario ex) still wins via "
                  "the general `fetch-the-wincon` (+30) at Ultra Ball, the only tutor that reaches it.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _TO_HAND and "engine" in c.roles,
        weight=20, status="assumed"),
    # NOTE — most of this deck's doctrine is COVERED by the General Strategy (STRATEGY.md §5):
    #   evolve-into-wincon, build-active-wincon (builds the Active Mega toward Mega Brave FF),
    #   attach-before-hand-shuffle + the new general hold-wincon-dont-shuffle (Lillie's/Judge),
    #   keep-key-cards-at-discard (Ultra Ball won't pitch the Mega), fetch-the-wincon /
    #   fetch-energy-when-starved / prefer-wincon-line-piece, the Boss's Orders gust doctrine,
    #   dont-bench-multiprize (discourages a casual Meowth ex bench). See STRATEGY.md §6/§9 for the
    #   deck-specific rules still to build (Aura-Jab load-targeting & discard-awareness, the dual-Mega
    #   retreat-swap, the prize-aware attacker choice, the Heave-Ho four-mechanic gust split).
]

STRATEGY = Strategy(
    name="mega_lucario",
    # readiness engine-derived: online at 1 F (Aura Jab 130), not the FF of Mega Brave.
    lines=[Line(path=[RIOLU, MEGA_LUCARIO_EX], payoff=MEGA_LUCARIO_EX, role="win_condition")],
    roles=ROLES,
    params={"setup_energy_target": 2,    # FF — toward the first Mega Brave (build-active-wincon target)
            "search_budget": 0},          # 0 = Tier-0 closed-form combat; >0 = Tier-1 Search (ADR-0019)
    hypotheses=HYPOTHESES,
)
