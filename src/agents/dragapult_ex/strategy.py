"""dragapult_ex — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/dragapult_ex/STRATEGY.md (the grilled playing doctrine, deck-genie 2026-07-03).

Dragapult ex SPREAD + DISRUPTION. Win-condition line: Dreepy -> Drakloak -> Dragapult ex
(Stage 2, 320 HP / 2 prizes). Phantom Dive (Fire+Psychic) = 200 to the Active PLUS 6 damage
counters spread across the opponent's Bench; the spread PRE-LOADS benched mons that Munkidori
(Adrena-Brain: move <=3 counters ours->theirs, needs {D}), Fezandipiti (Cruel Arrow 100 to any),
and Boss's Orders then convert into prizes on later turns. Cinderace x4 is the energy engine
(Explosiveness open + Turbo Flare bench-seed) off a thin 9-energy base; disruption (Crushing
Hammer / Judge / Unfair Stamp / Risky Ruins) buys the tempo to convert.

MOST of the doctrine is COVERED by the General Strategy (STRATEGY.md §5), incl. parts that look
deck-specific:
  - Cinderace open + Turbo-Flare accel   -> open-the-accelerator / advance-the-accel-pieces /
                                            develop-the-accel-recipient / dont-fetch-the-setup-only-opener
  - Boss's Orders gust-to-convert         -> the Gust doctrine (ADR-0022, id 1182)
  - Meowth ex Last-Ditch supporter tutor  -> general `supporter_tutor` TAG + `bench-the-supporter-tutor`
                                            + `grab-a-gust-supporter-for-the-ko` (tutor Boss's) — tag-driven,
                                            so NO Role and NO deck rule (mega_lucario 2026-07-03 model)
  - Unfair Stamp (ACE SPEC)               -> the Shuffle-Refresh doctrine (`shuffle_hand` tag) + aceSpec
                                            discard guard (same general coverage mega_lucario relies on)
  - Phantom Dive spread targeting         -> the snipe cluster at the DAMAGE select (per-counter)
  - the fetch/draw suite                  -> the Fetch (ADR-0023) + Shuffle-Refresh (ADR-0024) doctrines

This file holds only the deck overlay: Roles, the Line, params, and the genuinely deck-bound
Hypotheses. Pure data: no engine, no control flow. Weights are seeds (status="assumed") —
ladder-tuned (ADR-0009). Deck Hypotheses + the structural infra (Phantom Dive spread valuation,
Cruel Arrow targeting, Munkidori ability, Stadium state) are being added incrementally, each
test-first, per STRATEGY.md §8.
"""
from common.strategy import Hypothesis, Line, Plan, Ready, Strategy

# --- Card ids (dragapult_ex/deck.csv; verified against the engine 2026-07-03) -------------
DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, CINDERACE, MEOWTH_EX = 112, 140, 666, 1071
FIRE, PSYCHIC, DARKNESS = 2, 5, 7
UNFAIR_STAMP, BUDDY_POFFIN, NIGHT_STRETCHER, CRUSHING_HAMMER = 1080, 1086, 1097, 1120
ULTRA_BALL, POKE_PAD, BOSS_ORDERS, CRISPIN = 1121, 1152, 1182, 1198
JUDGE, LILLIES, RISKY_RUINS = 1213, 1227, 1260

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards that
# drive a role-keyed general rule; everything else rides its tags / the Line / a card-id deck rule).
ROLES = {
    DRAGAPULT_EX: ["win_condition", "primary_attacker"],
    DREEPY:       ["win_condition_base"],          # Line pre-evo (the Line drives line-piece rules)
    CINDERACE:    ["accel_source", "starter"],     # Explosiveness open + Turbo Flare (mega_starmie folds)
    CRISPIN:      ["accel_source"],                # color-fixer: fetch+attach the missing Phantom Dive color
    BOSS_ORDERS:  ["gust"],                         # the `gust` TAG/Role drives the shipped Gust doctrine
    NIGHT_STRETCHER: ["recovery"],
    # Meowth ex (1071): NO Role — the general `supporter_tutor` TAG + `bench-the-supporter-tutor`
    #   + `grab-a-gust-supporter-for-the-ko` drive it (a `tutor` Role would misfire as a WINCON dig).
    # Munkidori / Fezandipiti / Risky Ruins / Crushing Hammer: driven by deck Hypotheses (added
    #   incrementally), keyed on card_id / function tag — not a Role.
    # Tutors (Ultra Ball / Poké Pad / Poffin) + Judge / Lillie's: the Fetch / Shuffle-Refresh
    #   doctrines key on their function tags — no Role needed.
}

_PLAY, _EVOLVE = 7, 9   # OptionType.PLAY / EVOLVE

# Deck Hypotheses — the genuinely deck-bound rules (STRATEGY.md §6). Seeds (status="assumed"),
# ladder-tuned by id (ADR-0009). Folding candidates: once their vocabulary proves general (a
# comeback-draw tag; a general evolution-readiness / stadium-net-value rule), fold them (ADR-0034).
HYPOTHESES = [
    Hypothesis(
        id="bench-the-comeback-drawer",
        rationale="Bench Fezandipiti ex once we're entering the grind (RACE/STABILIZE) so Flip the Script "
                  "(draw 3 after our Pokémon is KO'd) is online when the trades start — the positive driver "
                  "missing beside `dont-bench-multiprize`, which correctly keeps a 2-prize ex off the early "
                  "SETUP bench. Not turn 1; a bench slot must be free.",
        when=lambda c: c.option_type == _PLAY and c.card_id == FEZANDIPITI_EX
        and c.plan in (Plan.RACE, Plan.STABILIZE) and c.board.my_bench < 5,
        weight=18, status="assumed"),
    Hypothesis(
        id="hold-evolution-until-attacker-ready",
        rationale="Delay evolving Drakloak into Dragapult ex until the body carries its 2 FP energy for "
                  "Phantom Dive — keep using Drakloak's Recon Directive (dig) each turn meanwhile, and don't "
                  "strand an energyless Dragapult while wasting the Recon turns. Counters the general "
                  "`evolve-into-wincon` (+40) pull. CARVE-OUT: evolve now if my Active is in KO danger "
                  "(`active_doomed`) — secure the 320-HP body / don't lose the line piece. Seed; ladder-tuned.",
        when=lambda c: c.option_type == _EVOLVE and c.card_id == DRAGAPULT_EX
        and c.evolve_body_energy is not None and c.evolve_body_energy < 2
        and not c.board.active_doomed,
        weight=-18, status="assumed"),
    Hypothesis(
        id="play-risky-ruins-when-net-positive",
        rationale="Play Risky Ruins (bench-chip Stadium) when net-positive: no Stadium is in play (place "
                  "ours to chip the opponent's Basic non-{D} bench-entries), OR an OPPONENT's Stadium is up "
                  "(replacing it disrupts them — a second, independent reason). The engine enforces "
                  "'different from the Stadium in play', so this never re-plays our own Ruins. v1 net gate + "
                  "stadium-denial; the bench-our-Basics-first sequencing and the skip-vs-{D}-decks refinement "
                  "are deferred (Read).",
        when=lambda c: c.option_type == _PLAY and c.card_id == RISKY_RUINS
        and (c.board.stadium_in_play is None or c.board.opp_stadium_in_play),
        weight=15, status="assumed"),
]

STRATEGY = Strategy(
    name="dragapult_ex",
    # readiness OVERRIDDEN to FP (Phantom Dive), NOT the engine's cheapest-attack default (Jet
    # Headbutt at C) — the RACE flip is the real payoff, so we stay in SETUP digging until FP is up.
    lines=[Line(path=[DREEPY, DRAKLOAK, DRAGAPULT_EX], payoff=DRAGAPULT_EX,
                role="win_condition", ready=Ready(energy=2))],
    roles=ROLES,
    params={"setup_energy_target": 2,     # FP for Phantom Dive
            "search_budget": 0,           # 0 = Tier-0 closed-form combat; >0 = Tier-1 Search (ADR-0019)
            "preferred_start": "first",   # setup-heavy: develop first + Risky-Ruins T1 (honor-preferred-start)
            "my_archetype": "Dragapult ex spread + disruption"},  # Read favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
