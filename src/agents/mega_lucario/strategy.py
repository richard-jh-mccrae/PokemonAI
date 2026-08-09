"""mega_lucario — the deck overlay ONLY: Roles, the Lines, params and the genuinely deck-bound
Hypotheses. Pure data, no control flow. Weights are seeds, ladder-tuned (ADR-0009).

Doctrine: src/agents/mega_lucario/STRATEGY.md. Architecture: docs/agent-architecture.md.
Flexible Fighting multi-attacker. Riolu -> Mega Lucario ex is a SINGLE hop (there is no Lucario in
this set), alternating Mega Brave with Aura Jab, whose bench-load is the deck's sole energy engine.
Solrock<->Lunatone is a co-dependent draw engine; Hariyama is the 210-for-one-prize trade star with a
free gust on evolve.

The Aura-Jab-vs-Mega-Brave choice, Aura Jab's bench-load targeting, the dual-Mega retreat-swap,
prize-trade interleaving and Heave-Ho's target pick all LOOK deck-specific and are all covered by the
general layer (ADR-0069 attach marginal, ADR-0100 promote/retreat equation, gust target tacticals).
"""
from common.strategy import Hypothesis, Line, Plan, Strategy

# Card ids — mega_lucario/deck.csv.
RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA, MEOWTH_EX = 676, 675, 673, 674, 1071
FIGHTING_ENERGY = 6
ULTRA_BALL, FIGHTING_GONG, POKE_PAD, PREMIUM_POWER_PRO, SWITCH = 1121, 1142, 1152, 1141, 1123
LILLIES, JUDGE, BOSS_ORDERS = 1227, 1213, 1182
AIR_BALLOON = 1174
# Deliberately id-LESS: Gravity Mountain, Unfair Stamp, Black Belt's, Petrel and Wally's are in the
# deck but reached through a tag / `card_effects.json` clause, so nothing deck-side keys off an id.

_TO_HAND = 7        # SelectContext.TO_HAND
_EVOLVE = 9         # OptionType.EVOLVE
_ABILITY = 10       # OptionType.ABILITY
_PLAY = 7           # OptionType.PLAY
_ACTIVATE = 43      # SelectContext.ACTIVATE — YES/NO, contextCard = the owner
_YES = 1            # OptionType.YES
_FIGHTING = 6       # EnergyType.FIGHTING
_ATTACH = 8         # OptionType.ATTACH
_SETUP_ACTIVE = 1   # SelectContext.SETUP_ACTIVE_POKEMON
_BENCH = 5          # AreaType.BENCH (inPlayArea)

# Co-dependent one-of-each engine: Cosmic Beam needs a benched Lunatone, Lunar Cycle needs Solrock in
# play. Neither is worth investing in without its partner in play OR reachable.
_ENGINE_IDS = {SOLROCK, LUNATONE}
_ATTACKER_ROLES = {"secondary_attacker", "primary_attacker", "win_condition",
                   "win_condition_base", "accel_source"}


def _partner(cid):
    return LUNATONE if cid == SOLROCK else (SOLROCK if cid == LUNATONE else None)


def _reachable(board, cid):
    """True iff `cid` is still gettable THIS game: in play / hand / this search's revealed pool (an
    EXACT within-frame test), else the sound deck oracle when no pool is revealed."""
    if cid in board.in_play_ids or cid in board.hand_ids:
        return True
    sd = board.search_deck_ids
    return (cid in sd) if sd is not None else (not board.deck_definitely_empty_of(cid))

# Sparse Role overlay on the universal Function Tags — only deck-intentional cards. Roles drive deck
# Hypotheses plus the universal role-keyed general rules.
ROLES = {
    # accel_source because Aura Jab IS the energy engine (3 Basic {F} from discard to the Bench).
    MEGA_LUCARIO_EX: ["win_condition", "primary_attacker", "accel_source"],
    RIOLU:    ["win_condition_base"],
    SOLROCK:  ["secondary_attacker", "engine"],
    LUNATONE: ["engine"],
    HARIYAMA: ["secondary_attacker", "gust"],
    MAKUHITA: ["evolution_base"],
    BOSS_ORDERS: ["gust"],
    AIR_BALLOON: ["retreat_tool"],
    # Deliberately role-LESS: Meowth ex rides the `supporter_tutor` TAG — a `tutor` Role misfired as a
    # WINCON dig. Black Belt's / Wally's / Petrel / Unfair Stamp ride tag/CardStat-keyed general rules.
}

HYPOTHESES = [
    # Solrock<->Lunatone pairing doctrine: start the attacker, power the attacker not the engine, skip
    # a partnerless Solrock, and fetch toward EXACTLY one of each in play.

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
    # `_attach_value`'s equation (ADR-0069) reads `partners=` below, so deleting that declaration
    # silently un-retires the gap the equation closed.

    # The one frame where neither the rungs nor the decider fires is Issue #443, pre-existing.
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
                  "-piece` (the _TO_HAND/search side). The soft −25 keeps the "
                  "redundant bench-play below any real develop/dig, but never hard-vetoes it (a lone "
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
    # RETIRED 2026-08-06, Issue #424: `gravity-mountain-vs-stage2` — `_boost_lethal_tactical` COMPUTES
    # the breakpoint crossing the flat +15 could only gesture at, differenced vs the Stadium in play.

    # `Board.opp_has_colorless_ability` is deliberately unused here — this deck cut the card that
    # read it; the general signal remains for any deck that runs one.
]

STRATEGY = Strategy(
    name="mega_lucario",
    # No Ready() override: readiness is engine-derived at one {F} (Aura Jab 130), not Mega Brave's {F}{F}.
    lines=[Line(path=[RIOLU, MEGA_LUCARIO_EX], payoff=MEGA_LUCARIO_EX, role="win_condition"),
           # A NON-wincon Line (ADR-0048), so the win-condition machinery ignores it — only FETCH
           # recognition and `develop-the-cheap-prize-wall-line` read it.
           Line(path=[MAKUHITA, HARIYAMA], payoff=HARIYAMA, role="secondary_attacker")],
    roles=ROLES,
    # Deck-declared so the GENERAL attach oracle zeroes a partnerless Solrock/Lunatone (attach Ruling
    # 6). SOLE expression of that fact since Issue #425 retired the rungs that duplicated it.
    partners={SOLROCK: [LUNATONE], LUNATONE: [SOLROCK]},
    # The COMPLETE pregame ACTIVE ranking, best first (ADR-0079). Lunatone is the DRAW ENGINE and
    # belongs benched; Meowth ex is last (2 prizes, and opening it forfeits Last-Ditch Catch).
    starter_priority=[SOLROCK, RIOLU, MAKUHITA, LUNATONE, MEOWTH_EX],
    params={"setup_energy_target": 2,    # {F}{F} — toward the first Mega Brave
            "search_budget": 0,           # INERT since ADR-0064 deleted Tier-6 escalation, its only
                                          # consumer; held at 0 to keep the manifest Tier-0 (test-pinned).
            "preferred_start": "first",  # setup-heavy evolution deck: take the develop turn
            "reactivity": "solitaire",   # UNCONSUMED since Issue #386 deleted its one reader (the
                                         # planner's forgo-KO gate). A declaration, not a live lever.
            "my_archetype": "Hariyama / Mega Lucario ex / Solrock"},  # Posture favorability key (ADR-0026)
    hypotheses=HYPOTHESES,
)
