"""dragapult_ex — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/dragapult_ex/STRATEGY.md (the grilled playing doctrine; re-authored deck-genie 2026-07-09
for the standard meta list — Cinderace OUT; Budew + Dunsparce/Dudunsparce + Rosa's IN; 1x Judge
re-added 2026-07-15 for a Psychic energy — general `shuffle_hand` coverage, no deck rule).

Dragapult ex SPREAD + DISRUPTION (chip-then-cash CONTROL). Win-condition line: Dreepy -> Drakloak ->
Dragapult ex (Stage 2, 320 HP / 2 prizes). Phantom Dive (Fire+Psychic) = 200 to the Active PLUS 6 damage
counters spread across the opponent's Bench; the spread PRE-LOADS benched mons that Munkidori
(Adrena-Brain: move <=3 counters ours->theirs, needs {D}), Fezandipiti (Cruel Arrow 100 to any),
and Boss's Orders then convert into prizes on later turns. NO acceleration engine (Cinderace removed):
energy is manual attach + Crispin + Rosa's Encouragement (comeback-only, from discard to a Stage 2).
Budew opens with a free item-lock (Itchy Pollen, best going SECOND); Dunsparce -> Dudunsparce (Run Away
Draw) is the consistency engine; disruption (Crushing Hammer / Unfair Stamp / Risky Ruins) buys tempo.

MOST of the doctrine is COVERED by the General Strategy (STRATEGY.md §5), incl. parts that look
deck-specific:
  - Boss's Orders gust-to-convert         -> the Gust doctrine (ADR-0022, id 1182)
  - Meowth ex Last-Ditch supporter tutor  -> general `supporter_tutor` TAG + the ADR-0086 Deploy
                                            Marginal + `grab-a-gust-supporter-for-the-ko` — tag-driven,
                                            so NO Role and NO deck rule (mega_lucario 2026-07-03 model)
  - Crushing Hammer                        -> `deny_relevance` (ADR-0080; `energy_denial` tag)
  - Unfair Stamp (ACE SPEC)               -> the Shuffle-Refresh doctrine (`shuffle_hand` tag) + aceSpec
                                            discard guard (same general coverage mega_lucario relies on)
  - Judge (re-added 2026-07-15)           -> the Shuffle-Refresh doctrine (`shuffle_hand` tag), like Lillie's
                                            — no Role, no deck rule (user-confirmed general coverage)
  - Phantom Dive spread / Cruel Arrow / Munkidori / Stadium -> the shipped structural infra (A/B/C/D,
                                            provider.py + oracle + baseline_snipe + Board.stadium_in_play)
  - the fetch/draw suite                  -> the Fetch (ADR-0023) + Shuffle-Refresh (ADR-0024) doctrines

This file holds only the deck overlay: Roles, the Line, params, and the genuinely deck-bound
Hypotheses. Pure data: no engine, no control flow. Weights are seeds (status="assumed") —
ladder-tuned (ADR-0009). The 2026-07-09 re-author's NEW gaps (`use-the-draw-engine-ability`,
`open-the-item-lock-starter` [DELETED 2026-07-28 by ADR-0079 — Budew's opening rank is now this
deck's `starter_priority`] + `item_lock` tag on Budew, `energy_accel` tag on Rosa's,
`dont-strand-the-evolving-engine`) are GENERAL and have SHIPPED into common (deck-align 2026-07-15):
baseline_sequencing.py / baseline_opening.py / doctrine_fetch.py + the two tags in card_functions.json.
They live in common, NOT in this file (ADR-0046); the deck opts in by running the tagged cards.
"""
from common.strategy import Hypothesis, Line, Plan, Ready, Strategy

# --- Card ids (dragapult_ex/deck.csv; verified against the engine 2026-07-09) -------------
DREEPY, DRAKLOAK, DRAGAPULT_EX = 119, 120, 121
MUNKIDORI, FEZANDIPITI_EX, MEOWTH_EX = 112, 140, 1071
DUDUNSPARCE, BUDEW, DUNSPARCE, ROSAS = 66, 235, 305, 1240   # re-author 2026-07-09 (handled via general + proposals)
FIRE, PSYCHIC, DARKNESS = 2, 5, 7
UNFAIR_STAMP, BUDDY_POFFIN, NIGHT_STRETCHER, CRUSHING_HAMMER = 1080, 1086, 1097, 1120
ULTRA_BALL, POKE_PAD, BOSS_ORDERS, CRISPIN = 1121, 1152, 1182, 1198
LILLIES, RISKY_RUINS = 1227, 1260

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards that
# drive a role-keyed general rule; everything else rides its tags / the Line / a card-id deck rule).
ROLES = {
    DRAGAPULT_EX: ["win_condition", "primary_attacker"],
    DREEPY:       ["win_condition_base"],          # Line pre-evo (the Line drives line-piece rules)
    CRISPIN:      ["accel_source"],                # primary un-gated accel: fetch+attach the Phantom Dive color
    BOSS_ORDERS:  ["gust"],                         # the `gust` TAG/Role drives the shipped Gust doctrine
    NIGHT_STRETCHER: ["recovery"],
    # Budew (235): the SACRIFICIAL item-lock starter (30 HP, free retreat, 0-cost Itchy Pollen) — open
    #   it Active, spend it (soak a hit for one prize: `interpose`/`promote-the-staller`), never fund
    #   it (free attack → `attach_target_needs` False). Its `starter` ROLE was RETIRED 2026-07-28
    #   (ADR-0079: the Role drove nothing — a hand holding any Basic never reaches the mulligan prompt,
    #   so `_hand_startable` never read it for a Basic). Opening it is now `starter_priority` rank 1.
    MUNKIDORI:    ["counter_mover"],               # Adrena-Brain: relay ≤3 counters ours→theirs each turn —
    #   spreads extra damage to assemble multi-KO Phantom Dive turns AND heals our own (peel counters
    #   off an Active Budew to keep the lock alive). A declared plan piece (user doctrine 2026-07-19):
    #   worth = the engine band, and the attach seam reads the Role — a stuck-Active Munkidori may take
    #   its {P} on top of the {D} fuel (Mind Bend 60 + Confusion) once the benched line is fed.
    # Meowth ex (1071): NO Role — the general `supporter_tutor` TAG + `bench-the-supporter-tutor`
    #   + `grab-a-gust-supporter-for-the-ko` drive it (a `tutor` Role would misfire as a WINCON dig).
    # Budew (235): its OPENING rank is `starter_priority` (ADR-0079, which deleted the
    #   `open-the-item-lock-starter` rung this line used to name); the `item_lock` TAG still drives the
    #   fetch-side reads. Rosa's (1240): `energy_accel` TAG -> `use-acceleration`
    #   (NOT the `accel_source` Role — it would mis-boost the comeback accel at setup). Both pending.
    # Fezandipiti / Risky Ruins / Crushing Hammer: driven by deck Hypotheses / infra / tags
    #   (Crushing Hammer -> general `play-energy-denial`), keyed on card_id / function tag — not a Role.
    # Dunsparce/Dudunsparce draw engine + tutors (Ultra Ball / Poké Pad / Poffin) + Lillie's: the Fetch /
    #   Shuffle-Refresh doctrines key on their function tags — no Role needed.
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
        and c.board.line_ready and c.board.my_bench < 5,   # "entering the grind" (ADR-0040 migration:
        weight=18, status="assumed"),                      # was plan in (RACE, STABILIZE) — ≡ today
    # `play-risky-ruins-when-net-positive` (+15) DELETED — POC-T4/5, Issue #386 — and the family it
    # priced is NOT yet taken over. Saying so plainly, because the first draft of this note said the
    # opposite ("its worth is a `state_value` delta, and the composer scores the Stadium play as an
    # ordinary MODELLED option") and that is false. `state_value`'s `development` term names the gap
    # in its own `blind_to`: *"the STADIUM — `model.stadium` has a supplier and no reader, so playing
    # or replacing one prices exactly 0. T4 lists stadium among the families it takes over, and this
    # is the term that would have to grow the read."* Measured on both of this deck's Risky Ruins
    # boards, the composer's 1-ply delta for the Stadium play is exactly 0.0 and it emits no gap:
    # the option is MODELLED and priced at nothing, which is the worst of the two failure shapes
    # because it looks like a considered valuation.
    #
    # The rung is still deleted rather than kept, because a flat +15 standing in for an unmeasured
    # quantity is the thing this issue exists to stop. What is owed is the `development` read, and
    # `tests/agents/test_dragapult_ex_triggers.py` carries two strict xfails that go RED the day it
    # lands. Its two gates were `wincon_in_play` (a proxy for "our fragile line is through the
    # vulnerable phase") and `opp_stadium_in_play` (replacing their Stadium removes its effect) —
    # both board facts, so neither is lost; only the pricing is.
]

STRATEGY = Strategy(
    name="dragapult_ex",
    # readiness OVERRIDDEN to FP (Phantom Dive), NOT the engine's cheapest-attack default (Jet
    # Headbutt at C) — the RACE flip is the real payoff, so we stay in SETUP digging until FP is up.
    lines=[Line(path=[DREEPY, DRAKLOAK, DRAGAPULT_EX], payoff=DRAGAPULT_EX,
                role="win_condition", ready=Ready(energy=2))],
    roles=ROLES,
    # Who takes the ACTIVE Spot at the pregame pick, best first — the COMPLETE ranking of this deck's
    # startable bodies (ADR-0079; order USER-RULED 2026-07-28). Read by the general
    # `open-the-declared-starter`; the ids live here, never in a trigger.
    #   Budew (30 HP) — the free item-lock. Itchy Pollen costs nothing and taxes an Item-heavy setup
    #     engine while our line assembles; `preferred_start="second"` exists so it fires T1. Was
    #     `open-the-item-lock-starter` (+35).
    #   Munkidori (110 HP, Mind Bend {P}+C 60) — the best BODY on offer: the most HP in the most-exposed
    #     slot and a real attack. This is dragapult f2 (86091728|0|decision|2), which the seam used to
    #     lose to an option-index tie-break with every option at 0.0.
    #   Dunsparce (70 HP) then Fezandipiti ex (210 HP) — bodies we can afford to have shot at.
    #   Dreepy (70 HP) — FIFTH, deliberately BELOW a 2-prize ex. Not because it is fragile but because
    #     it is MISPLACED: it is the win-condition Line base and it wants the BENCH, evolving toward
    #     Drakloak → Dragapult ex behind cover (`develop-the-wincon-base-first`). An Active Dreepy is a
    #     line that is not being built, which costs more than exposing a body the deck can spare.
    #     (A naive fragility+prize read would rank it ABOVE both ex's — the doctrine is the opposite.)
    #   Meowth ex (170 HP, 2 prizes) — last: multi-prize liability, and opening it forfeits Last-Ditch
    #     Catch (in-game bench-from-hand only). Was `dont-open-multiprize-active` (−15).
    starter_priority=[BUDEW, MUNKIDORI, DUNSPARCE, FEZANDIPITI_EX, DREEPY, MEOWTH_EX],
    params={"setup_energy_target": 2,     # FP for Phantom Dive
            "search_budget": 0,           # inert since ADR-0064 removed the Tier-6 escalation (its only
                                          # functional consumer). The remaining engine sims
                                          # (lethal_verify, lethal_family) run UNBUDGETED at 0. Kept at 0 to
                                          # hold the submission manifest at Tier-0 (test-pinned).
            "preferred_start": "second",  # Budew item-lock fires T1 only going 2nd (1st player can't attack
                                          # OR play a Supporter T1 — rules.md L72-73); guru-unanimous. (was "first")
            "reactivity": "opponent-filtered",  # deck-personality (learnthetcg): a spread + disruption
                                          # deck FILTERS each decision through the opponent's next turn
                                          # (single-prize to deny Counter Catcher, forgo a KO to deny
                                          # draw). Forward contract (behavior-neutral) — the opponent-
                                          # filtered seams are already default-on; deck-gating them to a
                                          # consumer that reads the Read's believed archetype is a follow-up.
            "my_archetype": "Dragapult ex spread + disruption"},  # Read favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
