"""mega_lucario — Strategy (declarative doctrine). See docs/agent-architecture.md and
src/agents/mega_lucario/STRATEGY.md (the grilled playing doctrine, deck-genie 2026-06-29;
re-baselined vs the merged general layer 2026-07-02, STRATEGY.md §5b; trainer-swap re-run
2026-07-03, STRATEGY.md §9 T9').

Trainer-swap 2026-07-03 (Pokémon core unchanged): OUT Maximum Belt (ACE SPEC) + Team Rocket's
Watchtower; IN Unfair Stamp (ACE SPEC Item), Black Belt's Training (+40 vs ex), Team Rocket's Petrel
(Trainer tutor), Wally's Compassion (Mega clutch-heal). All four are COVERED by the general layer
(damage-boost model / clutch_heal heal doctrine / general search / aceSpec+shuffle guards) — no new
deck rule. Meowth ex was RE-MODELED general (`supporter_tutor` tag + `bench-the-supporter-tutor`),
replacing the mis-assigned `tutor` Role that made the Pilot bench the 2-prize ex for a wincon dig.

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
AIR_BALLOON, GRAVITY_MOUNTAIN = 1174, 1252
# Trainer-swap 2026-07-03 — all covers-as-is (general layer), so no const keys off them:
#   UNFAIR_STAMP=1080 (ACE SPEC, aceSpec+hand_disruption guards), BLACK_BELTS=1211 (damage-boost model),
#   PETREL=1219 (general search), WALLYS=1229 (clutch_heal heal doctrine).
# REMOVED from the deck: MAX_BELT=1158, WATCHTOWER=1256.

_TO_HAND = 7        # SelectContext.TO_HAND — a search: choose which card to take into hand
_EVOLVE = 9         # OptionType.EVOLVE — evolve a Pokémon in play
_ABILITY = 10       # OptionType.ABILITY — use an in-play Ability (Lunar Cycle at the MAIN menu)
_PLAY = 7           # OptionType.PLAY — play a card from hand (the Stadium plays)
_ACTIVATE = 43      # SelectContext.ACTIVATE — "use the Ability?" (YES/NO; select.contextCard = owner)
_YES = 1            # OptionType.YES — the affirmative at an ACTIVATE / coin-toss select
_FIGHTING = 6       # EnergyType.FIGHTING — the deck's only Energy type
_ATTACH = 8         # OptionType.ATTACH — the turn's manual Energy attach
_ATTACH_FROM = 21   # SelectContext.ATTACH_FROM — Aura Jab's bench-load recipient pick
_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON — the pregame Active pick
_BENCH = 5          # AreaType.BENCH — the attach target's area (inPlayArea)

# The co-dependent one-of-each engine (STRATEGY.md §0): Solrock = the 70 attacker (Cosmic Beam needs a
# benched Lunatone), Lunatone = the benched draw engine (Lunar Cycle needs Solrock in play). Neither is
# worth investing in without its partner in play OR reachable. Drives the 7-seat pairing doctrine below.
_ENGINE_IDS = {SOLROCK, LUNATONE}
_ATTACKER_ROLES = {"secondary_attacker", "primary_attacker", "win_condition",
                   "win_condition_base", "accel_source"}


def _partner(cid):
    """The one-of-each engine partner of a Solrock/Lunatone (None for any other card)."""
    return LUNATONE if cid == SOLROCK else (SOLROCK if cid == LUNATONE else None)


def _reachable(board, cid):
    """True iff card `cid` is still gettable THIS game: in play / hand / the current search's revealed
    pool (`search_deck_ids`, an exact within-frame test), else the sound deck oracle
    (`not deck_definitely_empty_of`) when no search pool is revealed."""
    if cid in board.in_play_ids or cid in board.hand_ids:
        return True
    sd = board.search_deck_ids
    return (cid in sd) if sd is not None else (not board.deck_definitely_empty_of(cid))

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
    # MEOWTH_EX: no Role. Its Last-Ditch Supporter tutor is driven by the general `supporter_tutor`
    # TAG + `bench-the-supporter-tutor` rule (2026-07-03 re-model). The old `tutor` Role MISFIRED —
    # `play-a-tutor-for-the-unfound-wincon` (+25) read it as a WINCON dig, benching the 2-prize ex in
    # setup for the wrong reason (Last-Ditch fetches a SUPPORTER, not the wincon). See STRATEGY.md §3.
    BOSS_ORDERS: ["gust"],                         # the `gust` TAG drives the shipped general doctrine
    AIR_BALLOON: ["retreat_tool"],
    # Black Belt's / Wally's / Petrel / Unfair Stamp: NO Role — covered by tag/CardStat-keyed general
    # rules (damage-boost model / clutch_heal doctrine / general search / aceSpec guards).
}

HYPOTHESES = [
    # ── Solrock ↔ Lunatone one-of-each pairing doctrine (7 corrections, 4 CRITICAL) ─────────────────
    # The pair is a co-dependent engine (Solrock = attacker/Cosmic-Beam-needs-Lunatone; Lunatone = draw
    # engine/needs-Solrock). Fix every seat: start the attacker, power the attacker not the engine, skip
    # a partnerless Solrock, and fetch toward EXACTLY one of each in play. Replaces `fetch-the-engine-
    # first` (its `not line_ready` gate + blanket-engine grab caused f41/f12/f26).
    # (start-solrock-over-lunatone RETIRED 2026-07-28 — FOLDED into the deck's `starter_priority`
    #  declaration below + the general `open-the-declared-starter` (baseline_opening, +40), ADR-0079.
    #  It was gated on `card_id == SOLROCK` — the card-id reflex, shipped. The whole ml f1 finding
    #  ("both score 0, so the option-index tie-break opened Lunatone") is now the ORDER of the
    #  declaration: Solrock outranks Lunatone, and the general rule reads only the resolved
    #  `board.top_starter_id`, never an id. The +12 could only lift Solrock above a 0-scoring field;
    #  the ranking additionally orders Riolu, Makuhita and Meowth ex, which the rung never could.)
    # (dont-attach-to-the-engine RETIRED 2026-07-10 — FOLDED into the general
    #  `dont-fund-the-non-attacking-body` (baseline_energy, −12), which reads the same engine-only Role
    #  universally AND covers the ATTACH_FROM seam this rule was blind to (ml f121, CRITICAL: Aura Jab's
    #  bench-load put Energy on Lunatone). Keeping both would stack to −24 and push a LONE Lunatone below
    #  End — the exact calibration this rule's own rationale protected.)
    Hypothesis(
        id="attach-solrock-over-line-base",
        rationale="At a benched attach, prefer powering Solrock (the bridge attacker: secondary_attacker "
                  "+ engine) over holding a bare Riolu Line base: once `dont-fund-the-non-attacking-body` "
                  "demotes Lunatone, Solrock and Riolu tie and the decide()-only `attach_to_needy_line` "
                  "tie-break (Line base first) would pick Riolu (ml f11 flips to Riolu without this). "
                  "Power Solrock now (Cosmic Beam online), hold Riolu unevolved. +3 only breaks the "
                  "benched Solrock-vs-base tie; negligible against a real Active target. Gated on "
                  "`attach_is_energy` — it must not break the tie for a Pokémon Tool (ml f87, CRITICAL: "
                  "it tipped Air Balloon onto the benched Solrock).",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy
        and c.attach_target_area == _BENCH
        and "secondary_attacker" in c.attach_target_roles and "engine" in c.attach_target_roles,
        weight=3, status="assumed"),
    Hypothesis(
        id="aurajab-skip-partnerless-solrock",
        rationale="At Aura Jab's ATTACH_FROM bench-load, SKIP a partnerless Solrock — with no Lunatone in "
                  "play, Cosmic Beam does NOTHING, so loading discard-{F} onto it is inert (ml f87: "
                  "CRITICAL, all bench targets tied at `spread-attach-to-the-needy` +15 → index picked "
                  "Solrock). Load the Riolu→Mega line instead. −20 nets the inert Solrock below the line.",
        when=lambda c: c.select_context == _ATTACH_FROM and c.card_id == SOLROCK
        and LUNATONE not in c.board.in_play_ids,
        weight=-20, status="assumed"),
    Hypothesis(
        id="aurajab-load-the-wincon-line",
        rationale="At Aura Jab's ATTACH_FROM, prefer loading the win-condition Line pre-evo "
                  "(Riolu→Mega Lucario ex): `concentrate-accel-on-one-line-body` did not resolve to the "
                  "bare 0-Energy Riolu here (ml f87), so the deck states the line preference. +10 lands "
                  "the load on the Riolu line over an off-line body.",
        when=lambda c: c.select_context == _ATTACH_FROM and c.card_is_line_preevo,
        weight=10, status="assumed"),
    Hypothesis(
        id="fetch-the-missing-engine-half",
        rationale="At a search, fetch the MISSING half of the Solrock↔Lunatone engine — an engine piece "
                  "NOT already in play whose one-of-each partner is still reachable (in play / hand / this "
                  "search's revealed pool, else the sound deck oracle). Completes the co-dependent draw "
                  "engine (ml f41: benched lone Lunatone → fetch Solrock; all options scored 0 → index "
                  "missed it). Fires even when `line_ready` (the Mega is online but the engine still wants "
                  "completing) — the gap `fetch-the-engine-first` (`not line_ready`-gated) left. Replaces "
                  "it: role/quantity-aware, not blanket-engine. +22 clears the general line-piece stack "
                  "`prefer-wincon-line-piece` (+18) + `develop-the-cheap-prize-wall-line` (+3, ADR-0048) = "
                  "21, so completing the deck's whole draw engine outranks fetching a redundant Line "
                  "pre-evo (ml f39, CRITICAL: grab the Solrock that turns Lunar Cycle on, with an "
                  "energized Mega already benched, over a spare Riolu).",
        when=lambda c: c.select_context == _TO_HAND and c.card_id in _ENGINE_IDS
        and c.card_id not in c.board.in_play_ids and _reachable(c.board, _partner(c.card_id)),
        weight=22, status="assumed"),
    Hypothesis(
        id="dont-fetch-the-redundant-piece",
        rationale="Don't tutor a piece we ALREADY have in play — a redundant `engine` (a 2nd Solrock when "
                  "one is down, ml f12: CRITICAL) or a redundant win-condition base (an in-play Riolu, "
                  "whose `prefer-wincon-line-piece` +18 would otherwise out-grab the needed Makuhita in "
                  "f12/f26). We only ever need one of each engine half in play. −22 cancels the engine "
                  "+20 and the line-piece +18 so the missing piece (Makuhita) wins. NOTE: extending "
                  "'don't-fetch-redundant' to `win_condition_base` (Riolu) implements the human's explicit "
                  "one-of-each-in-play read; it mildly tensions with a dual-Mega 'fetch a 2nd Riolu' plan "
                  "(flagged to the user).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_redundant
        and bool({"engine", "win_condition", "win_condition_base"} & set(c.roles)),
        weight=-22, status="assumed"),
    Hypothesis(
        id="dont-fetch-the-inert-engine-piece",
        rationale="Don't tutor an INERT engine half — an engine piece not in play whose one-of-each "
                  "partner is UNREACHABLE (not in play / hand / this search's pool; e.g. both Lunatone "
                  "prized, ml f26: CRITICAL). A Solrock with no Lunatone reachable is a dead 70-attacker; "
                  "fetch the Makuhita (its Hariyama in hand) instead. −20 nets it below the live grab. "
                  "Requires the `search_deck_ids` reachability signal — the single-frame oracle can't see "
                  "the prized Lunatone. Mutually exclusive with `dont-fetch-the-redundant-piece` "
                  "(redundant = in play; inert = not in play + partner unreachable).",
        when=lambda c: c.select_context == _TO_HAND and c.card_id in _ENGINE_IDS
        and c.card_id not in c.board.in_play_ids and not _reachable(c.board, _partner(c.card_id)),
        weight=-20, status="assumed"),
    Hypothesis(
        id="dont-bench-a-redundant-engine-piece",
        rationale="Don't PLAY (bench from hand) a redundant engine half — a 2nd Solrock (or 2nd Lunatone) "
                  "when the Solrock<->Lunatone engine is ALREADY complete in play (both halves down). One "
                  "of each is all the co-dependent engine needs (Lunar Cycle needs one Solrock in play; "
                  "Cosmic Beam attacks from the Active), so a duplicate does nothing extra and clogs the "
                  "scarce Bench the Makuhita->Hariyama finisher line wants (ml 85709280 f51/m1, CRITICAL: "
                  "played a 2nd Solrock into the last Bench slot — 'we dont need two Solrocks down, reserve "
                  "this spot for a Makuhita'). This is the PLAY-side complement of `dont-fetch-the-redundant"
                  "-piece` (the _TO_HAND/search side). Soft −25 cancels `pre-position-attacker` (+25) so the "
                  "redundant bench-play drops below any real develop/dig, but never hard-vetoes it (a lone "
                  "surviving backup can still be benched if nothing better exists).",
        when=lambda c: c.option_type == _PLAY and c.card_id in _ENGINE_IDS
        and c.card_id in c.board.in_play_ids
        and _partner(c.card_id) in c.board.in_play_ids,
        weight=-25, status="assumed"),
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
        id="grab-lunar-cycle-fuel",
        rationale="At a search, take FIGHTING GONG when the Solrock↔Lunatone engine is online but has no "
                  "fuel — Lunar Cycle costs a Basic {F} DISCARDED FROM HAND, and with the hand empty the "
                  "engine is inert. Gong is an Item (playable the same turn) that fetches exactly that "
                  "Basic {F}, so it converts one search into: fetch {F} → discard it → draw 3. The "
                  "general layer cannot see this: it has no notion that an Ability's cost is paid from "
                  "hand. ml f71 — Team Rocket's Petrel resolved on a DEAD hand (0 cards) and the grab "
                  "rungs offered nothing but a Lillie's it could not play (the Supporter was already "
                  "spent, `grab-what-i-can-play-this-turn`), so the option index took a Premium Power "
                  "Pro. +8 clears the 0-scoring Items without ever outranking a real need "
                  "(`fetch-energy-when-starved` +35, `fetch-the-wincon` +30).",
        when=lambda c: c.select_context == _TO_HAND and c.card_id == FIGHTING_GONG
        and LUNATONE in c.board.in_play_ids and SOLROCK in c.board.in_play_ids
        and not c.board.hand_basic_energy.get(_FIGHTING, 0),
        weight=8, status="assumed"),
    Hypothesis(
        id="dont-lunar-cycle-away-the-last-attachable-f",
        rationale="The Lunar Cycle discipline (Phase-A §3 Lunatone): the turn's manual attach to the "
                  "wincon line comes FIRST — never pay the Ability's F-discard with the ONLY Basic "
                  "{F} in hand while this turn's attach is still pending and a body can absorb it "
                  "(`energy_placeable`). Self-sequencing: the attach (tier 2) resolves first, "
                  "`energy_attached` flips, this guard stands down, and Lunar Cycle still fires the "
                  "same turn on the surplus — the doctrine's 'hold that F back', not a blanket "
                  "decline. Surfaced by the T6' probe (the always-YES default would have paid the "
                  "stranding discard). STANDS DOWN when the single {F} IS the whole attach (no surplus "
                  "to cycle) AND the engine is online AND the Active is a weak pre-evo: then attaching "
                  "the lone {F} kills the cycle rather than deferring it, and its 30 chip doesn't change "
                  "tempo — the discarded {F} is Aura-Jab-recoverable, so draw-3 acceleration wins (ml "
                  "85058574 f16). Still fires for a real-attacker Active or an offline engine.",
        when=lambda c: c.option_type == _ABILITY and c.card_id == LUNATONE
        and c.board.hand_basic_energy.get(_FIGHTING, 0) == 1
        and not c.board.energy_attached and c.board.energy_placeable
        and not (LUNATONE in c.board.in_play_ids and SOLROCK in c.board.in_play_ids
                 and (c.board.active_is_weak_preevo
                      or (c.board.my_hand_size <= 1
                      and (not c.board.active_attack_provable or c.board.active_doomed)
                      and not c.board.active_arm_available))),
        # ^ ALSO stands down on a DEAD-HAND famine (engine online, hand ≤ 1, and the lone {F} can't arm a
        #   this-turn Active attack): draw 3 beats sinking the last card into a premature bench attach —
        #   the discarded {F} is Aura-Jab-recoverable (ml f42 Makuhita-active / f54 Lunatone-active).
        weight=-30, status="assumed"),
    Hypothesis(
        id="lunar-cycle-the-weak-preevo-last-f",
        rationale="The other side of the last-{F} coin (ml 85058574 f16): when the Solrock↔Lunatone engine "
                  "is ONLINE and the Active is a weak pre-evo (Riolu's 30 chip vs Mega Lucario ex 130/270), "
                  "spend the lone Basic {F} on Lunar Cycle (draw 3) rather than an attach that only powers a "
                  "tempo-neutral chip. Standing the −30 guard down is necessary but not sufficient — Lunar "
                  "Cycle at 0 still sits below the attaches (`power-up-attacker` +15). This positive rung "
                  "carries it past them; the discarded {F} is Aura-Jab-recoverable and the deck is {F}-rich, "
                  "so the acceleration is not a stranded loss. Fires on the EXACT complement of the guard's "
                  "stand-down, so the two are mutually exclusive by construction. SEED; ladder-tuned.",
        when=lambda c: c.option_type == _ABILITY and c.card_id == LUNATONE
        and c.board.hand_basic_energy.get(_FIGHTING, 0) == 1
        and not c.board.energy_attached
        and LUNATONE in c.board.in_play_ids and SOLROCK in c.board.in_play_ids
        and (c.board.active_is_weak_preevo
             or (c.board.my_hand_size <= 1
                      and (not c.board.active_attack_provable or c.board.active_doomed)
                      and not c.board.active_arm_available)),
        # ^ fires on the SAME broadened condition as the guard's stand-down (weak pre-evo OR dead-hand
        #   famine), so the two stay mutually exclusive. +30 (was +20) clears `concentrate-energy-on-wincon`
        #   (+25) landing on the benched-Mega attach in the famine case (ml f42/f54); the weak-preevo case's
        #   weaker Riolu-active competitor is unaffected.
        weight=30, status="assumed"),
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
    # (watchtower-vs-colorless-abilities REMOVED 2026-07-03 — Team Rocket's Watchtower was cut from the
    # deck. The general Board.opp_has_colorless_ability signal remains for any deck that runs it.)
]

STRATEGY = Strategy(
    name="mega_lucario",
    # readiness engine-derived: online at 1 F (Aura Jab 130), not the FF of Mega Brave.
    lines=[Line(path=[RIOLU, MEGA_LUCARIO_EX], payoff=MEGA_LUCARIO_EX, role="win_condition"),
           # Cheap prize-wall secondary attacker (ADR-0048): Hariyama = 210-for-1-prize. A NON-wincon Line
           # (role="secondary_attacker"), so the win-condition machinery ignores it — only the broadened
           # FETCH recognition + `develop-the-cheap-prize-wall-line` read it (kill-switched, default on).
           Line(path=[MAKUHITA, HARIYAMA], payoff=HARIYAMA, role="secondary_attacker")],
    roles=ROLES,
    # The co-dependent one-of-each engine (STRATEGY.md §0): each half is a dead attach target without
    # its partner in play. Deck-declared so the GENERAL attach oracle zeroes a partnerless Solrock /
    # Lunatone (attach Ruling 6) — the value-side complement of the `skip-partnerless-solrock` rung.
    partners={SOLROCK: [LUNATONE], LUNATONE: [SOLROCK]},
    # Who takes the ACTIVE Spot at the pregame pick, best first — the COMPLETE ranking of this deck's
    # startable bodies (ADR-0079). Read by the general `open-the-declared-starter`; the ids live here,
    # never in a trigger. Transcribed from the doctrine it replaces:
    #   Solrock (110 HP, Cosmic Beam 70 for one {F}) — the attacker half of the pair; was
    #     `start-solrock-over-lunatone` (+12, ml f1 CRITICAL).
    #   Riolu (80 HP, Accelerating Stab {F} 30) — ONE hop from Mega Lucario ex (340 HP, Aura Jab 130)
    #     and it can attack now. The constraint ADR-0079 is written around: open-Riolu must survive,
    #     and it does here as a LINE-SHAPE read, not a card-id gate.
    #   Makuhita (80 HP, {F} 10) — the secondary-line base; a body, not a plan.
    #   Lunatone (110 HP) — the DRAW ENGINE. Belongs on the Bench powering Lunar Cycle; was
    #     `dont-open-with-the-engine` (−12).
    #   Meowth ex (170 HP, 2 prizes) — last. A multi-prize liability in the most-exposed slot, and
    #     opening it forfeits Last-Ditch Catch (triggers only on an in-game bench-from-hand). Was
    #     `dont-open-multiprize-active` (−15); the residual-blunder audit caught it opening ~4/25 games.
    # A forced single pick still places whatever is offered when nothing better is (minCount 1).
    starter_priority=[SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX],
    params={"setup_energy_target": 2,    # FF — toward the first Mega Brave (build-active-wincon target)
            "search_budget": 0,           # inert since ADR-0064 removed the Tier-6 escalation (its only
                                          # functional consumer). Tier-1 engine sims (planner_engine_rank,
                                          # lethal_verify, lethal_family) run UNBUDGETED at 0. Kept at 0 to
                                          # hold the submission manifest at Tier-0 (test-pinned).
            "preferred_start": "first",  # setup-heavy evolution deck: take the develop turn
                                         # (general `honor-preferred-start` reads this at the coin toss)
            "reactivity": "solitaire",   # deck-personality (learnthetcg): a linear evolution-beatdown
                                         # prioritises its OWN setup; don't over-play-around the opponent.
                                         # WIRED: `_forgo_ko` (planner.py:860) reads this — a solitaire
                                         # deck skips the develop/END over-reaction lines and races its own
                                         # plan (the line-1 alt-attack exemption keeps Aura Jab reachable).
                                         # NB the rung is only reached when `forgo_ko` is ON (defaults OFF).
            "my_archetype": "Hariyama / Mega Lucario ex / Solrock"},  # Posture favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
