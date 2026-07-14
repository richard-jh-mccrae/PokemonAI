"""dragapult_ex — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/dragapult_ex/STRATEGY.md (the grilled playing doctrine; re-authored deck-genie 2026-07-09
for the standard meta list — Cinderace/Judge OUT; Budew + Dunsparce/Dudunsparce + Rosa's IN).

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
  - Meowth ex Last-Ditch supporter tutor  -> general `supporter_tutor` TAG + `bench-the-supporter-tutor`
                                            + `grab-a-gust-supporter-for-the-ko` (tutor Boss's) — tag-driven,
                                            so NO Role and NO deck rule (mega_lucario 2026-07-03 model)
  - Crushing Hammer                        -> general `play-energy-denial` (`energy_denial` tag)
  - Unfair Stamp (ACE SPEC)               -> the Shuffle-Refresh doctrine (`shuffle_hand` tag) + aceSpec
                                            discard guard (same general coverage mega_lucario relies on)
  - Phantom Dive spread / Cruel Arrow / Munkidori / Stadium -> the shipped structural infra (A/B/C/D,
                                            provider.py + oracle + baseline_snipe + Board.stadium_in_play)
  - the fetch/draw suite                  -> the Fetch (ADR-0023) + Shuffle-Refresh (ADR-0024) doctrines

This file holds only the deck overlay: Roles, the Line, params, and the genuinely deck-bound
Hypotheses. Pure data: no engine, no control flow. Weights are seeds (status="assumed") —
ladder-tuned (ADR-0009). The 2026-07-09 re-author's NEW gaps (`use-the-draw-engine-ability`,
`open-the-item-lock-starter` + `item_lock` tag on Budew, `energy_accel` tag on Rosa's,
`dont-strand-the-evolving-engine`) are GENERAL and queued as Strategy Proposals
(data/strategy/proposals/deck-genie-20260709-dragapult_ex.md) for /update-strategy to author + gate —
NOT yet in this file (ADR-0046). The deck opts in by running the tagged cards.
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
    # Meowth ex (1071): NO Role — the general `supporter_tutor` TAG + `bench-the-supporter-tutor`
    #   + `grab-a-gust-supporter-for-the-ko` drive it (a `tutor` Role would misfire as a WINCON dig).
    # Budew (235): opts into the pending general `open-the-item-lock-starter` via an `item_lock` TAG,
    #   not a Role (proposal deck-genie-20260709). Rosa's (1240): `energy_accel` TAG -> `use-acceleration`
    #   (NOT the `accel_source` Role — it would mis-boost the comeback accel at setup). Both pending.
    # Munkidori / Fezandipiti / Risky Ruins / Crushing Hammer: driven by deck Hypotheses / infra / tags
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
    Hypothesis(
        id="hold-evolution-until-attacker-ready",
        rationale="Delay evolving Drakloak into Dragapult ex until the body carries its 2 FP energy for "
                  "Phantom Dive — keep using Drakloak's Recon Directive (dig) each turn meanwhile, so the "
                  "benched Drakloaks draw the whole time and we don't strand an energyless Dragapult while "
                  "burning the Recon turns. This must CANCEL, not merely dent, the general evolve pull: the "
                  "premature evolve carries `evolve-into-wincon` (+40) PLUS `evolve-the-energized-body-first` "
                  "(+5 when the body holds 1 energy) = +45, so at the old seed −18 the evolve still scored "
                  "+27 and BEAT the +18 Recon dig (`use-the-draw-engine-ability`) — measured, the agent "
                  "evolved anyway and lost the draw engine. −46 nets the unready evolve to ≈−1, below End(0) "
                  "and well below the +18 dig / a real attach, so decide() keeps digging. The same-turn case "
                  "is NOT suppressed: when a 2nd energy is in hand the Turn Planner drives evolve→attach→"
                  "Phantom Dive itself (verified, planner owns the pick). CARVE-OUT: evolve now if my Active "
                  "is in KO danger (`active_doomed`) — secure the 320-HP body / don't lose the line piece. "
                  "Seed; ladder-tuned.",
        when=lambda c: c.option_type == _EVOLVE and c.card_id == DRAGAPULT_EX
        and c.evolve_body_energy is not None and c.evolve_body_energy < 2
        and not c.board.active_doomed,
        weight=-46, status="assumed"),
    Hypothesis(
        id="play-risky-ruins-when-net-positive",
        rationale="Play Risky Ruins (SYMMETRIC bench-chip Stadium: 20 damage to any Basic non-{D} a player "
                  "benches) only when net-positive for US: place ours to chip the opponent ONLY once our "
                  "win-condition is in play (`board.wincon_in_play`). Before the payoff lands we are the "
                  "bench-heavier side still laying our fragile 70-HP Dreepy line, so the symmetric chip damages "
                  "US more (f24, CRITICAL: turn 2 vs a thin Cinderace/Mega Starmie set-up with ~no future "
                  "bench-entries, Risky Ruins only bled our own developing spread). The OPPONENT's Stadium being "
                  "up is a second, INDEPENDENT reason (replacing it denies them regardless of the chip). The "
                  "engine enforces 'different from the Stadium in play', so this never re-plays our own Ruins. "
                  "`wincon_in_play` is the sound board-only floor; the full opp-aware net-value (their remaining "
                  "benchable non-{D} basics vs ours, via the Read) and the skip-vs-{D}-decks refinement are deferred.",
        when=lambda c: c.option_type == _PLAY and c.card_id == RISKY_RUINS
        and ((c.board.stadium_in_play is None and c.board.wincon_in_play)
             or c.board.opp_stadium_in_play),
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
