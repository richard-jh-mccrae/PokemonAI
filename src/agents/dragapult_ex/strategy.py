"""dragapult_ex — the deck overlay ONLY: Roles, evolution relationships, params and the genuinely deck-bound
Hypotheses. Pure data, no control flow. Weights are seeds, ladder-tuned (ADR-0009).

Doctrine: src/agents/dragapult_ex/STRATEGY.md. Architecture: docs/agent-architecture.md.
Spread + disruption: Dreepy -> Drakloak -> Dragapult ex, whose Phantom Dive pre-loads the opponent's
Bench for Munkidori / Fezandipiti / Boss's Orders to cash later. NO acceleration engine.

Everything here that LOOKS deck-specific — gust, supporter tutor, energy denial, shuffle-refresh, the
fetch/draw suite, the spread infra — is covered by the General Strategy and lives in common, not in
this file (ADR-0046); the deck opts in by running the tagged cards.
"""
from common.strategy import Hypothesis, Plan, Roles, Strategy

# Card ids — dragapult_ex/deck.csv.
DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUDUNSPARCE, BUDEW, DUNSPARCE, ROSAS = 66, 235, 305, 1240
FIRE, PSYCHIC, DARKNESS = 2, 5, 7
UNFAIR_STAMP, BUDDY_POFFIN, NIGHT_STRETCHER, CRUSHING_HAMMER = 1080, 1086, 1097, 1120
ULTRA_BALL, POKE_PAD, BOSS_ORDERS, CRISPIN = 1121, 1152, 1182, 1198
LILLIES, RISKY_RUINS = 1227, 1260

# Sparse Role overlay on the universal Function Tags — only cards driving a role-keyed general rule.
# Phantom Dive's two-Energy readiness override lives on the terminal role declaration.
ROLES = Roles({
    DRAGAPULT_EX: ["win_condition", "primary_attacker"],
    CRISPIN:      ["accel_source"],
    BOSS_ORDERS:  ["gust"],
    NIGHT_STRETCHER: ["recovery"],
    # Adrena-Brain relays ≤3 counters ours→theirs: assembles multi-KO Phantom Dive turns AND peels
    # counters off an Active Budew. The attach seam reads this Role.
    MUNKIDORI:    ["counter_mover"],
    # Deliberately role-LESS: Meowth ex (a `tutor` Role would misfire as a wincon dig) and Rosa's
    # (`accel_source` would mis-boost comeback accel at setup). Everything else is tag/card-id driven.
}, evolves={DREEPY: DRAKLOAK, DRAKLOAK: DRAGAPULT_EX}, ready={DRAGAPULT_EX: 2})

_PLAY, _EVOLVE = 7, 9   # OptionType.PLAY / EVOLVE

# Deck-bound rules (STRATEGY.md §6). Fold into common once the vocabulary proves general (ADR-0034).
HYPOTHESES = [
    Hypothesis(
        id="bench-the-comeback-drawer",
        rationale="Bench Fezandipiti ex once we're entering the grind (RACE/STABILIZE) so Flip the Script "
                  "(draw 3 after our Pokémon is KO'd) is online when the trades start — the positive driver "
                  "the Deploy Marginal's prize-exposure term does not supply (it prices the 2-prize body's "
                  "cost, never its Ability payoff). Not turn 1; a bench slot must be free.",
        when=lambda c: c.option_type == _PLAY and c.card_id == FEZANDIPITI_EX
        and c.board.line_ready and c.board.my_bench < 5,
        weight=18, status="assumed"),
    # `play-risky-ruins-when-net-positive` (+15) DELETED (Issue #386) but NOT taken over: the composer
    # prices a Stadium play at exactly 0.0. Two strict xfails go RED the day that read lands.
]

STRATEGY = Strategy(
    name="dragapult_ex",
    roles=ROLES,
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079, USER-RULED). Dreepy is FIFTH, below
    # both ex's, ON PURPOSE — it is the Line base and wants the Bench; a fragility+prize read inverts it.
    starter_priority=[BUDEW, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, DREEPY, MEOWTH_EX],
    params={"setup_energy_target": 2,     # {F}{P} for Phantom Dive
            "search_budget": 0,           # INERT since ADR-0064 deleted Tier-6 escalation, its only
                                          # consumer; held at 0 to keep the manifest Tier-0 (test-pinned).
            "preferred_start": "second",  # Budew's item-lock only fires T1 going second (player 1 may
                                          # neither attack nor play a Supporter on T1 — rules.md).
            "reactivity": "opponent-filtered",  # forward contract, behavior-NEUTRAL: nothing gates on it
                                          # yet, the opponent-filtered seams are already default-on.
            "my_archetype": "Dragapult ex spread + disruption"},  # Read favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
