"""mega_lucario — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/mega_lucario/STRATEGY.md (the grilled playing doctrine, deck-genie 2026-06-29;
re-baselined vs the merged general layer 2026-07-02, STRATEGY.md §5b).

Flexible Fighting multi-attacker. Win-condition: Mega Lucario ex (Riolu -> Mega ex, single hop,
340 HP / 3 prizes) — alternate Mega Brave (FF 270) with Aura Jab (F 130 + load up to 3 Basic {F}
from discard onto the Bench, the deck's sole energy engine). The Solrock<->Lunatone pair is a
self-contained draw engine + early 70 attacker + discard-fuel source; Hariyama is the prize-trade
star (210 for 1 prize) + a free gust on evolve (Heave-Ho Catcher).

Most of the doctrine is COVERED by the General Strategy (STRATEGY.md §5/§5b), including the parts
that LOOK deck-specific:
  - Aura-Jab-vs-Mega-Brave choice   -> the Tactical energy-recover credit + self-lock cost
    (AttackStat.recoverN / nextTurnSameAttackLock; pilot._tactical)
  - Aura Jab's bench-load targeting -> ATTACH_FROM `concentrate-accel-on-one-line-body` (2nd Mega
    first) + `spread-attach-to-the-needy` (then Hariyama)
  - dual-Mega retreat-swap          -> `swap-out-the-locked-attacker` (Board.active_best_attack_locked)
    + `promote-the-ready-wincon` at the SWITCH target pick
  - prize-trade interleaving        -> `interpose-the-cheap-attacker-to-preserve-the-wincon` +
    `dont-promote-into-their-prize-reach` at TO_ACTIVE
  - Heave-Ho's TARGET pick          -> the context-keyed gust target tacticals (KO / stall / keystone)
This file holds only the deck overlay: Roles, the Line, params, and the genuinely deck-bound
Hypotheses. Pure data: no engine, no control flow. Weights are seeds (status="assumed") —
ladder-tuned (ADR-0009).
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
_EVOLVE = 9         # OptionType.EVOLVE — evolve a Pokémon in play
_ABILITY = 10       # OptionType.ABILITY — use an in-play Ability (Lunar Cycle at the MAIN menu)
_PLAY = 7           # OptionType.PLAY — play a card from hand (the Stadium plays)
_ACTIVATE = 43      # SelectContext.ACTIVATE — "use the Ability?" (YES/NO; select.contextCard = owner)
_YES = 1            # OptionType.YES — the affirmative at an ACTIVATE / coin-toss select
_FIGHTING = 6       # EnergyType.FIGHTING — the deck's only Energy type

# Per-deck Role overlay on the universal Function Tags (sparse — only deck-intentional cards).
# Roles drive deck Hypotheses + the universal role-keyed general rules (win_condition exemptions,
# accel_source promote/bench rules etc.).
ROLES = {
    MEGA_LUCARIO_EX: ["win_condition", "primary_attacker", "accel_source"],
    #                  accel_source: Aura Jab IS the deck's energy engine (attach 3 F from discard
    #                  to the Bench) -> `develop-the-accel-recipient` endorses benching the 2nd
    #                  Riolu while a Mega is Active; `promote-the-accelerator-for-the-ko` applies.
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
                  "the engine edges the line piece early, per the fetch-priority ruling. The payoff "
                  "(Mega Lucario ex) still wins via the general `fetch-the-wincon` (+30) at Ultra "
                  "Ball, the only tutor that reaches it.",
        when=lambda c: c.plan == Plan.SETUP and c.select_context == _TO_HAND and "engine" in c.roles,
        weight=20, status="assumed"),
    Hypothesis(
        id="spring-heave-ho-when-it-pays",
        rationale="Evolve Makuhita into Hariyama the turn its Heave-Ho Catcher gust PAYS: a benched "
                  "body my Active can KO after the drag (`gust_best_ko_prizes > 0` — the drag-and-KO, "
                  "free and it doesn't spend Boss's), or an energyless high-retreat body to strand "
                  "(`stall_target_exists` — the TEMPO gust; free, so it fires WITHOUT the Boss's "
                  "doctrine's KO/doomed gates, per the Phase-A ruling). Both signals are energyless-"
                  "or-KO-able targets only, so it never endorses dragging up a powered attacker we "
                  "can't KO. The evolve does NOT end the turn (Mega-era rules), so the KO lands the "
                  "same turn; the WHICH-target pick at the resulting opponent-bench SWITCH select is "
                  "the general gust target tacticals (KO > keystone-strand > stall). Holding "
                  "Hariyama-in-hand + Makuhita-benched is a sprung trap — this rule is the spring.",
        when=lambda c: c.option_type == _EVOLVE and c.card_id == HARIYAMA
        and (c.board.gust_best_ko_prizes > 0 or c.board.stall_target_exists),
        weight=25, status="assumed"),
    Hypothesis(
        id="heave-ho-decline-without-payoff",
        rationale="At Heave-Ho Catcher's \"use the Ability?\" select (ACTIVATE with "
                  "select.contextCard = the just-evolved Hariyama), DECLINE when the gust has no "
                  "payoff — no benched body my Active can KO after the drag AND no energyless "
                  "high-retreat body to strand. Every remaining drag-up candidate is then a powered "
                  "body we can't KO, and gusting one up is a FREE PROMOTE for the opponent (the "
                  "Phase-A anti-pattern: never gust up a powered attacker you can't KO). The Pilot's "
                  "tie-break otherwise picks the first option (YES), so the decline must be explicit. "
                  "The engine-verified probe (2026-07-02) pinned the select shape: ACTIVATE(43), "
                  "bare YES/NO options, owner only on contextCard.",
        when=lambda c: c.select_context == _ACTIVATE and c.context_card_id == HARIYAMA
        and c.option_type == _YES
        and not (c.board.gust_best_ko_prizes > 0 or c.board.stall_target_exists),
        weight=-40, status="assumed"),
    Hypothesis(
        id="heave-ho-gust-when-it-pays",
        rationale="The affirmative half: at Heave-Ho's ACTIVATE, USE the free gust when it pays — a "
                  "KO-able benched target (`gust_best_ko_prizes > 0`, the drag-and-KO) or a strandable "
                  "energyless body (`stall_target_exists`, the tempo gust the free Heave-Ho is allowed "
                  "that Boss's isn't). Explicit rather than relying on the YES-first tie-break, and "
                  "legible in the trace; the WHICH-target pick at the following opponent-bench SWITCH "
                  "select is the general gust target tacticals.",
        when=lambda c: c.select_context == _ACTIVATE and c.context_card_id == HARIYAMA
        and c.option_type == _YES
        and (c.board.gust_best_ko_prizes > 0 or c.board.stall_target_exists),
        weight=15, status="assumed"),
    # (dont-cosmic-beam-without-lunatone RETIRED 2026-07-02: the oracle now models the bench-partner
    # condition itself — AttackStat.requiresBench + the live `atk_bench_names` context zero the
    # attack's SCORED damage, and the phantom-KO vs a <=70-HP Active with it. Covered-as-is.)
    Hypothesis(
        id="fire-lunar-cycle",
        rationale="Lunar Cycle (Lunatone's Ability at the MAIN menu: with Solrock in play, discard a "
                  "Basic {F} from hand → draw 3) is the deck's native draw engine — fire it "
                  "AGGRESSIVELY: the discarded F is Aura Jab fuel, not waste, and a free +3 cards "
                  "beats almost any other use of the pre-attack window. Nothing endorses an ABILITY "
                  "option generically (it ties with END at 0 and loses to any attack), so the deck "
                  "says it out loud; the positive score also sequences it TIER-0 (free informative "
                  "development, before the Supporter / the attach / the attack). Stands down exactly "
                  "where the last-F guard below fires, so the pair never double-counts.",
        when=lambda c: c.option_type == _ABILITY and c.card_id == LUNATONE
        and not (c.board.hand_basic_energy.get(_FIGHTING, 0) == 1
                 and not c.board.energy_attached and c.board.energy_placeable),
        weight=15, status="assumed"),
    Hypothesis(
        id="dont-lunar-cycle-away-the-last-attachable-f",
        rationale="The Lunar Cycle discipline (Phase-A §3 Lunatone): the turn's manual attach to the "
                  "wincon line comes FIRST — never pay the Ability's F-discard with the ONLY Basic "
                  "{F} in hand while this turn's attach is still pending and a body can absorb it "
                  "(`energy_placeable`). Self-sequencing: the attach (tier 2) resolves first, "
                  "`energy_attached` flips, this guard stands down, and Lunar Cycle still fires the "
                  "same turn on the surplus — the doctrine's 'hold that F back', not a blanket "
                  "decline. Surfaced by the T6' probe (the always-YES default would have paid the "
                  "stranding discard).",
        when=lambda c: c.option_type == _ABILITY and c.card_id == LUNATONE
        and c.board.hand_basic_energy.get(_FIGHTING, 0) == 1
        and not c.board.energy_attached and c.board.energy_placeable,
        weight=-30, status="assumed"),
    Hypothesis(
        id="gravity-mountain-vs-stage2",
        rationale="Gravity Mountain (−30 HP to every Stage 2, both sides) NEVER touches our board — "
                  "the whole deck is Basics + single-hop Stage 1s (engine stage flags, Phase-A §1) — "
                  "so against a Stage-2 board it is pure one-sided tech: play it when the opponent "
                  "has a Stage 2 in play (`opp_has_stage2`), where the −30 crosses our breakpoints "
                  "(Mega Brave 270 reaches a 300-HP Stage 2, Wild Press 210 a 240). A Stadium play "
                  "is free (no Supporter slot), so a modest weight just lifts it above idle options.",
        when=lambda c: c.option_type == _PLAY and c.card_id == GRAVITY_MOUNTAIN
        and c.board.opp_has_stage2,
        weight=15, status="assumed"),
    Hypothesis(
        id="watchtower-vs-colorless-abilities",
        rationale="Team Rocket's Watchtower turns off {C} Abilities BOTH sides — proactive tech only "
                  "when the opponent actually has a Colorless Pokémon with an Ability in play "
                  "(`opp_has_colorless_ability`), and NEVER while our own Meowth ex (a {C} ability "
                  "body) still waits in hand: its Last-Ditch Catch triggers on the bench-drop, and "
                  "under our own Watchtower it would fetch nothing (Phase-A §3 sequencing — Meowth "
                  "BEFORE Watchtower). Once Meowth has dropped (or was never drawn), the lock is "
                  "pure opponent-facing value.",
        when=lambda c: c.option_type == _PLAY and c.card_id == WATCHTOWER
        and c.board.opp_has_colorless_ability and MEOWTH_EX not in c.board.hand_ids,
        weight=15, status="assumed"),
]

STRATEGY = Strategy(
    name="mega_lucario",
    # readiness engine-derived: online at 1 F (Aura Jab 130), not the FF of Mega Brave.
    lines=[Line(path=[RIOLU, MEGA_LUCARIO_EX], payoff=MEGA_LUCARIO_EX, role="win_condition")],
    roles=ROLES,
    params={"setup_energy_target": 2,    # FF — toward the first Mega Brave (build-active-wincon target)
            "search_budget": 0,          # 0 = Tier-0 closed-form combat; >0 = Tier-1 Search (ADR-0019)
            "preferred_start": "first",  # setup-heavy evolution deck: take the develop turn
                                         # (general `honor-preferred-start` reads this at the coin toss)
            "my_archetype": "Hariyama / Mega Lucario ex / Solrock"},  # Posture favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
