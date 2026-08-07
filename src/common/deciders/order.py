"""`_finish_turn_last`: the tiering that makes the turn's chosen options happen in a SOUND order — informative plays
first, the attack last.

The attack ENDS the turn, so a development played after it never happens. Ordering is not a value question and is
deliberately not scored: the tiers are structural."""
from __future__ import annotations


from common.deciders.facts import Board
from common.option_equivalence import canonical_keys
from common.strategy.context import (KO_SCORE, _ACTIVE, _ATTACH, _ATTACK, _END, _EVOLVE, _MAIN, _PLAY, _RETREAT,
                                     _SETUP_BENCH)


# ── `_finish_turn_last`'s tiers, NAMED (ADR-0095 decision 1, Issue #261 item 2f) ──────────────────
# The sequencer's bands, as constants rather than the literals its docstring used to narrate. Named
# because the free band GAINED a boundary and every later number shifted by one: a renumbering
# expressed in bare integers is exactly the edit whose one missed occurrence is invisible (the
# `deferred` marking below compares against the LAST tier, and it was a literal `4`).
_TIER_INFORMATIVE = 0   # free AND informative: the digs, the Bench fill, the benched evolve — plus the
                        # lethal/winning special cases, which out-score everything else in the band

_TIER_COMMIT_FREE = 1   # free but COMMITTING: an endorsed free PLAY that spends a card at a target and
                        # reveals nothing (a Hammer, a Switch, a Stadium, a non-KO gust Item).
                        # ADR-0095's boundary. NOT a Tool — a Tool is an `_ATTACH`, so it takes the
                        # blind-commitment tier below and never meets this branch.

_TIER_SUPPORTER = 2     # the one-per-turn Supporter (non-shuffle)

_TIER_COMMITMENT = 3    # the blind / costly commitments: the Energy attach, a `cost_discard` search

_TIER_SHUFFLE = 4       # a hand-SHUFFLE Supporter — it nukes the hand, so attach before it

_TIER_ENDER = 5         # the turn-ENDING attack, plus Retreat / End / non-beneficial options

#: Behavioural Function Tags that make a PLAY *informative* — it ENLARGES the information set, so it
#: weakly dominates a commitment and sequences ahead of one (ADR-0095 decision 1; the classification
#: is keyed off a tag, never a card name). `dig:N` riders always accompany a bare `dig`/`draw` in
#: `card_functions.json`, so a plain intersection is enough.
#:
#: Deliberately NOT `_ENGINE_KEEP_TAGS`, which holds the same three strings today and asks a different
#: question — *"is this card a draw ENGINE worth keeping over filler"* (a discard-context keep floor).
#: The two may legitimately diverge: a future `reveal`-shaped tag would be informative without being
#: an engine. Sharing one name would make that divergence an edit nobody knows to make.
_INFORMATIVE_TAGS = frozenset({"draw", "search", "dig"})


class OrderMixin:
    """The turn's sequencing: which chosen option goes first."""

    def _score_order(self, obs: dict, options: list, traces: list) -> list:
        """The menu ranked for `chosen`, **canonically** (ADR-0103, Issue #254).

        Primary key = score; the secondary key breaks an EXACT tie toward an attach feeding a needy
        Line body (ep82867148 f87) — a decide()-only ordering nicety, W-route-invisible, never in the
        weight fit. What is new is the THIRD key, and what it replaces.

        A tie used to fall through to the engine's menu index, and the index is the one thing about
        an option that is not a board fact. After an identical first step onto interchangeable bodies
        the resulting boards are isomorphic but their menus are *permutations* of each other, so one
        tie resolved toward a different body on each: `_engine_leaf_value`'s within-turn rollout
        re-runs this very policy on each intermediate SearchState, which is how it reached a KO from
        bench 0 and missed the isomorphic line from bench 1 — `81903490|0|decision|49` scored
        1167.0 / 95.4 / 95.4 on three byte-identical Riolu, reproducibly. ADR-0091 corrected that
        *reading* (`fan_out` gives the class its demonstrated maximum) and filed the cause as
        Issue #254; this is the cause.

        So the tie breaks on the option's **Option Equivalence Class identity** — the ADR-0091
        fingerprint, a pure function of the board — and only then on the index, which now decides
        just between options that share a key: either the same decision (interchangeable by
        definition) or unfingerprintable (no canonical identity exists, so menu order is the honest
        answer). One consequence stated rather than hidden: this changes which of several EXACTLY
        tied options is picked in live play too, and deliberately — a policy that is invariant only
        inside the sim would be simulating something other than itself, which is the drift the
        composer's whole authority to decide the MAIN menu rests on not having.

        Unconditional, like `_prefer_soonest_arming_evolve` below (the same defect one layer up, the
        same fix): it deletes an inconsistency rather than adding a value term, so there is no OFF
        branch worth carrying. The `leaf_option_equivalence` kill-switch that used to carry the
        develop rung's narrower class-collapse contract is DELETED with that rung (POC-T4/5): the
        composer applies ADR-0091 unconditionally, which is the same reading this key already took.

        Measured 2026-08-02 over 300 corpus frames (2193 options, mean 7.3/frame): the fingerprinting
        costs **0.031 ms per decision**, ~3% of the ~0.95 ms whole-Board build
        (`test_leaf_profile.py`'s own reference figure). Recorded because it runs on every live
        decision AND every rollout step, unflagged."""
        canon = canonical_keys(options, obs)
        return sorted(range(len(options)), key=lambda i: self._order_key(traces[i], canon[i], i))

    @staticmethod
    def _order_key(trace, canon: str, index: int) -> tuple:
        """ONE definition of "which of these options goes first" (ADR-0103 decision 5).

        `_score_order` sorts a whole menu with it; `_greedy_grab` takes the `min` of it repeatedly
        over re-scored traces. Written once because two spellings of one ordering is how a key added
        to one site silently fails to reach the other — the half-application `_option_equivalence`'s
        own docstring exists to prevent, and the first draft of this change had already committed it
        (the needy-Line leg was in the sort and absent from the grab).

        Ascending, so every leg is negated where it should rank high: score DESC, the needy-Line
        attach first, then the board-derived canonical identity, then the menu index — which now
        separates only options that key EQUAL on everything above it."""
        return (-trace.score, not trace.attach_to_needy_line, canon, index)

    def _prefer_soonest_arming_evolve(self, order: list, options: list, traces: list) -> list:
        """Break an EXACT tie between EVOLVE options toward the body that arms soonest — i.e. put the
        evolution where the Energy already is (ADR-0070 amendment M, #167).

        `evolve-the-energized-body-first` was one of the five rungs the 1b swap retired, on the
        premise that `evolve_value` subsumes it. It does not, and the reason is structural rather
        than a missing read: `deploy = result.deploy() - body.deploy()` cancels **per slot**, because
        the body and its result share that slot's Energy, arm and ko. So an energised Staryu cancels
        2-against-2 and a bare one cancels 3-against-3 — both exactly 0.0 — and the tie then broke by
        raw option INDEX. Measured on 81905522|0|decision|64: the equation reads the post-attach board
        correctly (bench0's arm drops 3 -> 2), and the delta erases what it read. The consequence was
        the Energy and the evolution landing on DIFFERENT bodies, stranding an Energy on a Staryu that
        must still evolve before it can attack.

        So consult the one term that does not cancel — the RESULT's arm clock — and only where it can
        change nothing else: a run must be **all EVOLVE options at an identical score** before it is
        reordered, so an evolve can never be promoted past a tied non-evolve. Ordering only; no score
        moves, so f35's hold, the attach-anyway floor and the free-development exemption are all
        untouched. The arm clock is already in `evolve_working["result"]`, so a trace reader can see
        why one body won.

        Tied evolves need NOT be adjacent: on 81905522|0|decision|64 the equal-score run is
        ``[2, 0, 1, 6]`` with a non-evolve sitting BETWEEN the two evolves, so a consecutive-run
        implementation never forms a run and never fires. This permutes the evolves *within the
        positions they already occupy*, leaving every non-evolve exactly where it was — which is what
        keeps "an evolve is never promoted past a tied non-evolve" true while still ordering the
        evolves against each other."""
        def arm(i):
            w = getattr(traces[i], "evolve_working", None)
            return (w or {}).get("result", {}).get("arm") if w else None

        def is_evolve(i):
            return options[i].get("type") == _EVOLVE and arm(i) is not None

        out, n = list(order), len(order)
        i = 0
        while i < n:
            j = i                           # the maximal run of options sharing one score
            while j + 1 < n and traces[out[j + 1]].score == traces[out[i]].score:
                j += 1
            slots = [k for k in range(i, j + 1) if is_evolve(out[k])]
            if len(slots) > 1:              # permute ONLY the evolves, into their own slots
                for slot, opt in zip(slots, sorted((out[k] for k in slots), key=arm)):
                    out[slot] = opt
            i = j + 1
        return out

    def _never_pre_bench(self, select: dict, chosen: list) -> list:
        """NEVER place a Pokémon on the Bench during Set Up (ADR-0086 decision 9). A sound rule read
        off the rulebook, not a price — so it filters the pick rather than scoring it, like decision
        7's empty-Bench guard.

        Deferring to my own first turn is WEAKLY DOMINANT: never worse, sometimes better. Three facts
        make it safe, each checked at source rather than recalled:

        1. **The placement is optional.** "Put **up to** 5 more Basic Pokémon face down on your Bench"
           (`docs/rulebook.txt` L97) — which is why the select carries `minCount 0` and this can be a
           filter at all.
        2. **No ATTACK reaches me first, in either seat.** Going first, my turn 1 precedes any
           opponent action at all; going second, their turn 1 cannot attack (`docs/rules.md` §2,
           rulebook L152), so their turn 2 is the first legal attack — after my turn 1 either way.
        3. **No ABILITY damage reaches me either**, which is the leg that makes 2 sufficient rather
           than merely suggestive. Only Basics can be in play on turn 1, because neither player may
           evolve on their own first turn (`docs/rules.md` §4, rulebook L123-128) — and of the 21
           damage-counter Abilities in `data/EN_Card_Data.csv`, ZERO are on a Basic. Dusknoir's 130,
           Froslass's checkup counters and Tyranitar's Sand Stream are all evolutions.

        And the Basics I keep in hand cannot be stripped in the meantime: the player going first
        cannot play a Supporter (rulebook L133), so no Judge or Iono shuffles them away.

        What deferring BUYS: the pregame placement wastes every bench-drop Ability, since "once during
        your turn" is unsatisfiable before the game starts — Meowth ex's Last-Ditch Catch is the case
        that opened Issue #197. Benching the same body on turn 1 fires it. Going second it also buys
        information: I draw a card and see their committed board before spending any of my own.

        This SUBSUMES three Set-Up special cases that were separately bolted onto the equation — the
        exposure fallback's pregame branch, the redundancy charge keyed on `setup_placed_ids`, and
        the `_SETUP_BENCH` half of the since-deleted `bench-fill-a-basic`. Three approximations of
        one rule.

        Scoped to `_SETUP_BENCH` only. The Set-Up ACTIVE choice is untouched (a Basic there is
        mandatory), and every in-game bench play is still the Deploy Marginal's to price."""
        if select.get("context") != _SETUP_BENCH:
            return chosen
        return []

    def _empty_bench_forced(self, obs: dict, select: dict, board: Board, options: list,
                            order: list) -> list:
        """The post-setup EMPTY-BENCH guard (ADR-0086 decision 7): with nothing to promote, a single
        Knock-Out ends the match on the spot (`docs/rules.md` §7 case 2), so a legal Pokémon deploy is
        TAKEN rather than ranked.

        A FILTER on the option order, never a score, and since Issue #261 item 2d the ONLY mechanism
        scoring or ordering this fact besides `_predicted_loss` — `keep-a-bench` (+60) scored the same
        play "so the two agree", and ADR-0096 decision 2 deleted it as the redundant third guard.
        `_LINE_CAP`'s band invariant is why this cannot be a weight at all: max positional (readiness
        300 + survival 50 + threat 100 + value 40 + line 100) = 590 < 1000 = KO_SCORE, deliberately,
        so no positional term can outrank a real prize — and a loss-avoidance value cannot be
        simultaneously bounded under that band AND un-outbiddable. A filter is the only shape that is
        both.

        It ranks WHICH body, never WHETHER: the surviving order is the Deploy Marginal's, restricted
        to the deploys.

        **Post-setup only.** Verified at source (`docs/rules.md` §2): the player going first cannot
        attack on turn 1 and the player going second acts only after that turn, so in either seat my
        first turn precedes the first legal attack — declining a pregame placement cannot lose the
        game before I can bench. Scoping it here keeps the guard a statement about a REACHABLE loss:
        at Set Up no Knock Out is legal yet, so there is nothing to be forced by.

        The converse is what makes the scoping mandatory: an unscoped guard fires at `_SETUP_BENCH`
        on `setup_bench_decline_f3` (bench empty, Meowth ex the sole option) and forces exactly the
        placement decision 3 derives us out of, burning Last-Ditch Catch — which can be had one turn
        later, from hand, WITH the fetch.

        OPEN (2026-07-30): the same reasoning is being asked of this filter's own trigger — whether an
        empty Bench should force a body unconditionally, or only when the Active is DOOMED. Not
        changed here, and deliberately: the filter guards a LOSS, and gating a loss-guard on a
        prediction trades a bounded cost for an unbounded one. See
        `docs/plans/deploy-decider-swap-review.md`.

        Silent unless it has something to force, so an empty Bench with no legal body on the menu
        leaves the order untouched."""
        if select.get("context") != _MAIN or int(board.my_bench or 0) > 0 or not self.stats:
            return order
        deploys = [i for i in order
                   if options[i].get("type") == _PLAY
                   and getattr(self.stats.get(self._option_card_id(obs, select, options[i])),
                               "is_pokemon", False)]
        if not deploys:
            return order
        seen = set(deploys)
        return deploys + [i for i in order if i not in seen]

    def _informative_card(self, cid) -> bool:
        """Does PLAYING this card ENLARGE the information set? — ADR-0095 decision 1's classification,
        and the boundary `_finish_turn_last` splits its free band on.

        Two ways in, both card FACTS rather than card names. The first is the behavioural Function
        Tag the ADR specifies — `_INFORMATIVE_TAGS`, draw / search / dig. The second is a CardStat
        fact rather than a tag, and is called out as such: the card being a Pokémon, i.e. a Bench
        fill, which the ADR's own list names as informative and which tier 0's docstring has always
        carried (*"fill the Bench, play a Pokémon"*). There is no `bench_fill`-shaped tag on every
        Basic and inventing one to satisfy the letter of "keyed off a tag" would put a second,
        hand-maintained copy of `is_pokemon` in `card_functions.json`.

        **Untagged defaults to COMMITTING**, per the ADR, and the asymmetry is the reason: a
        mis-classified commitment sequencing EARLY spends a card before the dig that would have
        re-aimed it, while a mis-classified dig sequencing one band LATE costs nothing but ordering —
        the engine re-presents the menu either way. Unknown stats, unknown functions and a `None` card
        id therefore all read as committing.

        A method rather than a closure inside the sequencer: the fail direction above is the part
        most worth a test, and it is only decidable per CARD (`test_information_before_commitment.py`
        walks the four classes through here). A predicate reachable only via a full menu would be
        pinned by whichever cards a fixture happened to hold."""
        if cid is None:
            return False
        st = self.stats.get(cid) if self.stats else None
        if st is not None and getattr(st, "is_pokemon", False):
            return True
        tags = self.functions.tags(cid) if self.functions else ()
        return bool(_INFORMATIVE_TAGS & set(tags))

    def _finish_turn_last(self, obs: dict, board: Board, options: list, traces: list, order: list,
                          max_count: int, select_context: int | None) -> list:
        """Sequence the turn's commitments LAST. The engine re-presents the open turn menu after each
        non-ending action, so the whole turn still happens — which means you should take the most
        informative, reversible actions first and the irreversible ones last:

          tier 0  free and INFORMATIVE — a draw / search / dig, fill the Bench, evolve a benched
                  Pokémon, play a Pokémon (and an attach / gust that UNLOCKS a KO — take the win). A
                  GAME-WINNING attack (a KO that takes my last prize) also sits here: when this action
                  wins the match there is nothing to develop FOR, so take it immediately rather than
                  dig/develop first (a non-winning KO still develops-first — the whole point of
                  attack-last is intact; ep83037962 f78).
                  Free, and reveals a better target before you commit.
          tier 1  free but COMMITTING — an endorsed free PLAY that spends a card at a target and
                  reveals nothing: a Crushing Hammer, a Switch, a Stadium, a non-KO gust Item. (Not
                  a Tool: a Tool is an `_ATTACH` and lands in tier 3.)
          tier 2  your one-per-turn SUPPORTER (non-shuffle) — informative (draws / searches / tutors),
                  so commit it AFTER the free Item digs (a Pokégear may upgrade which Supporter you
                  play) but before the blind attach. A KO-enabling gust Supporter stays in tier 0.
          tier 3  the blind / costly COMMITMENTS — the Energy attach, and a discard-COST search
                  (`cost_discard`, e.g. Ultra Ball: pays 2 cards from hand).
          tier 4  a hand-SHUFFLE Supporter (`shuffle_hand`, e.g. Lillie's / Harlequin) — it nukes the
                  hand, so attach your held Energy (tier 3) FIRST, then shuffle the dregs away.
          tier 5  the turn-ENDING attack, plus Retreat / End / non-beneficial options.

        **Tiers 0 and 1 are ADR-0095 decision 1's boundary, and T2 (Issue #261 item 2f) is where it
        lands.** The free band used to be ONE tier, so this method stated the doctrine as its own
        purpose while `_tier` ended on a bare `return 0` and conflated *free* with *informative*:

            Pokegear 3.0     free, INFORMATIVE   -> tier 0
            Crushing Hammer  free, COMMITTING    -> tier 0     <- same band; score decides

        Arm deny, the Hammer out-scores the Pokégear, and the Hammer sequences first — which is
        `82225643|1|decision|11`, where the human ruled *"Collect information before committing. Do
        PokeGear first. Then, most likely, you'll also play Hammer and Ignition Energy in this same
        turn."* All three plays are legal in one turn (`docs/rules.md` §3: Items unlimited), so it was
        never a selection; it was an ORDERING, and no score could express it. This is also why the
        boundary is STRUCTURAL and cannot be left to the POC's differencing: digging first and digging
        second reach the **same end state**, so no function of that state separates them (ADR-0095
        decision 3; `sound_rules.information-before-commitment`).

        Scoped to `_PLAY`, which is where the defect was diagnosed — an Evolve or an Ability commits no
        card from hand at a target, and widening the boundary to them would re-sequence bands the ADR
        did not measure.

        An option is sequenced early only when a Hypothesis endorses it (score > 0). A knockout is
        never forfeited: an Evolve of the Active drops to the last tier when a KO is on the menu, and
        the KO attack outscores everything else there. Stable within a tier (keeps the score order).
        Only at a single-pick MAIN menu; every other context (snipe, search, mulligan) is untouched."""
        if max_count != 1 or len(order) < 2 or select_context != _MAIN:
            return order
        ko_available = any(options[i].get("type") == _ATTACK and traces[i].tactical >= KO_SCORE
                           for i in order)

        def _wins_now(i: int) -> bool:
            """This ATTACK is a KO of the opponent's ACTIVE that takes my LAST prize — it wins the
            match, so it goes first (nothing to develop for). Conservative: gated on `active_can_ko`
            (my Active actually KOs the opp Active this turn), so a KO-class score coming ONLY from a
            bench SNIPE (which credits the opp Active's prize value for a lower-prize benched KO — the
            ep83661649 f54 bug: a 1-prize Staryu snipe read as a 3-prize Active KO) falls back to
            develop-first. The snipe-KO is still taken this turn, just AFTER the beneficial attach —
            no prize forfeited, and the attach toward Nebula Beam lands (attack-last)."""
            if options[i].get("type") != _ATTACK or traces[i].tactical < KO_SCORE:
                return False
            return (board.my_prizes_remaining > 0 and board.active_can_ko
                    and self._prize_value(self._opp_active(obs)) >= board.my_prizes_remaining)

        def _cost_discard(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "cost_discard" in self.functions.tags(cid)

        def _is_gust_card(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "gust" in self.functions.tags(cid)

        # ── two tiers DELETED here, and the deletion is a LOSS being recorded, not a cleanup ────────
        # `_gust_enables_ko` (`gust-for-the-ko` / `gust-for-the-loaded-equal-ko`) and
        # `_retreat_walls_the_line` (`retreat-to-wall-the-line`) each triggered off a rung ID. POC-T4/5
        # (Issue #386) deleted all three rungs, so from that merge both closures returned False on every
        # board and their `_tier` branches were UNREACHABLE — while still reading as live, and while
        # `baseline/__init__.py` asserted in prose that *"`_finish_turn_last`'s tiers SURVIVE and are
        # still where the ordering claim lives."* For these two it was already false when written.
        #
        # **A retired id sitting in a live string literal reads as LIVE to every instrument.** Nothing
        # went red, because nothing anywhere compares a matched id against the shipped roster — the same
        # masking that hid the stale halves of `planner._CLASS_B_SPEND_IDS`. `tests/strategy/
        # test_rung_id_literals_are_live.py` is the interlock that now makes this class impossible: any
        # id a production module matches on must be one some Strategy actually ships.
        #
        # DELETED rather than re-expressed, because re-expressing needs a measurement this merge has no
        # standing to make, and one of the two cannot be re-expressed yet at all:
        #   * the GUST tier has no seam to move to. `CLAUSE_WRITES['gust']` is non-empty, so `_covers`
        #     refuses the transition (Issue #300) and the composer cannot price a gust either. Rung,
        #     tier and leaf are all silent on it — the hole is total, and it is already filed with its
        #     two corpus frames in `tests/strategy/poc_t4_flips.py`.
        #   * the RETREAT tier's claim (*"the wall retreat is STEP 1, ahead of a free evolve"*) IS what
        #     the composer scores in-sequence, on the 63.4% of MAIN frames it decides (ADR-0131). On the
        #     rest the retreat now falls to `_TIER_ENDER` with every other retreat. A narrowing, not a
        #     break — and the maneuver's other half is untouched: `Board.can_wall_line_with_disruptor`
        #     still feeds the live `feed-the-line-for-disruptor-lock`, the ATTACH that funds the retreat.

        def _is_supporter(i: int) -> bool:
            cid = traces[i].card_id
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            return bool(st and st.is_supporter)

        def _is_shuffle_refresh(i: int) -> bool:                     # a hand-nuke Supporter (shuffle_hand)
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "shuffle_hand" in self.functions.tags(cid)

        def _tier(i: int) -> int:
            o = options[i]
            t = o.get("type")
            if t in (_ATTACH, _PLAY, _RETREAT) and traces[i].tactical >= KO_SCORE:  # a lethal play/attach
                return _TIER_INFORMATIVE   # unlocks a KO, or a gust/retreat-to-lethal swap — take the win,
                                           # don't dig first (REQ-GUST-0001). It shares the top band with the
                                           # digs and out-scores them by a KO_SCORE margin, so "strictly
                                           # first" needs no tier of its own.
            # (the KO-enabling-gust and wall-retreat tiers stood HERE until this merge — see the note
            #  above the helpers for what they claimed and why re-expressing them is a separate build)
            if t == _ATTACK and _wins_now(i):                        # a game-winning KO: take the win now,
                return _TIER_INFORMATIVE                             # don't dig/develop first (ep83037962 f78)
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return _TIER_ENDER
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return _TIER_ENDER                                   # would forfeit an available KO
            if t == _PLAY and _is_gust_card(i) and board.active_can_ko:
                return _TIER_ENDER                                   # a gust SWAPS the defender: never ahead of
                                                                     # a KO of the ACTIVE it would forfeit
                                                                     # (ep83456015 f38: 3-prize Nebula ≻ gust).
                                                                     # The old test was ANY menu KO — but a KO
                                                                     # coming from a bench SPREAD is not
                                                                     # forfeited by swapping the defender, and it
                                                                     # buried Boss's Orders (+50, the top-scored
                                                                     # option) below a setup Supporter that ate
                                                                     # the one-per-turn slot (dragapult f81)
            if (t == _EVOLVE and o.get("inPlayArea") != _ACTIVE      # FREE DEVELOPMENT, tier 0 already
                    and traces[i].score >= 0):                       # names it: "evolve a benched
                return _TIER_INFORMATIVE                             # Pokémon". A same-line bench evolve
                                                                     # nets to exactly 0.0 — the pre-evo is
                                                                     # pre-credited with the LINE's payoff
                                                                     # (`_line_payoff_stat`), so the deploy
                                                                     # delta CANCELS — and the `score <= 0`
                                                                     # gate below then starved it, ending
                                                                     # turns with bare 70 HP Staryu instead
                                                                     # of 330 HP Mega Starmie ex (#167's
                                                                     # six-frame sitting).
                                                                     # Scoped deliberately: `>= 0` only, so
                                                                     # an evolve the equation prices as a
                                                                     # WEAKENING (f35's -30.36 forfeited
                                                                     # Recon dig) still falls to tier 5; and
                                                                     # BENCHED only, leaving the Active's
                                                                     # KO-forfeit guard above untouched.
                                                                     # This is NOT the `>= 0` loosening
                                                                     # ADR-0070 rejected — that was the whole
                                                                     # sequencer; a zero-priced ATTACH still
                                                                     # drops to the LAST tier below (the
                                                                     # attach-anyway blunder class,
                                                                     # 82749168-21/82867148-34).
            # A FREE INFORMATIVE PLAY reaches the boundary's band at score ZERO — ADR-0131
            # decision 1 (POC-T4/5, Issue #386).
            #
            # `sound_rules.information-before-commitment` is a STANDING ruling that this ordering is
            # *"NOT derivable by the planner — both orders reach the same end state, so no function
            # of that state separates them (ADR-0095 decision 3)"*. The swap deleted
            # `dig-before-commit` (+20) on the premise that a rung asserting a leaf-computable
            # preference is a second opinion — but that premise does not hold for THIS rung, and the
            # whitelist says so in as many words.
            #
            # What broke, measured on ADR-0095's own anchor frame `ms_information_before_commitment
            # _f11`: with the +20 gone the Pokégear 3.0 prices at exactly 0.00, the gate below drops
            # it to `_TIER_ENDER`, and the boundary underneath never runs on it. Crushing Hammer
            # (22.50, COMMITTING) sequences first and the human's ruled dig is not played at all.
            # The boundary was intact the whole time; its input had been removed.
            #
            # This is NOT the `>= 0` loosening ADR-0069 measured and rejected, and FOUR fences keep
            # it from becoming one:
            #
            #   `_PLAY` only        a zero-priced ATTACH still falls to the last tier, which is the
            #                       attach-anyway blunder class (82749168-21, 82867148-34).
            #   `== 0` not `>= 0`   a NEGATIVE score is a decider saying the play is bad.
            #   not `cost_discard`  a costed dig is not free, so weak dominance does not hold.
            #   NOTHING FIRED       the fence that was missing, and the one that matters most. A
            #                       score of 0 has two very different causes: *nothing prices this
            #                       option* (the Pokégear, once `dig-before-commit` was deleted —
            #                       `fired` is empty) and *a rung deliberately NEUTRALISED it* (Mega
            #                       Signal under `dont-tutor-the-held-wincon`, which nets a redundant
            #                       tutor to exactly zero — `fired` names it). The old `score <= 0`
            #                       gate treated both as "not endorsed", and it was right about the
            #                       second. Without this fence the carve-out sequenced a search the
            #                       ladder had just refused FIRST — caught by
            #                       `test_benchless_agent_refreshes_over_a_redundant_wincon_tutor`,
            #                       whose whole subject is a neutralised tutor.
            #
            # What survives all four is exactly the ADR's own case: free, informative, unopposed, and
            # priced at nothing — where taking it cannot cost anything and can improve what follows.
            if (t == _PLAY and traces[i].score == 0 and not traces[i].fired
                    and not _cost_discard(i) and self._informative_card(traces[i].card_id)):
                return _TIER_INFORMATIVE
            if traces[i].score <= 0:                                 # only an endorsed action sequences early
                return _TIER_ENDER                                   # — incl. an attach the decider prices at
                                                                     # ZERO: sequencing that ahead of End is
                                                                     # attach-anyway, the blunder class
                                                                     # ADR-0069 rejected an epsilon floor for
                                                                     # (measured: 82749168-21, 82867148-34)
            if t == _PLAY and _is_shuffle_refresh(i):                # hand-nuke: AFTER the Energy attach, so
                return _TIER_SHUFFLE                                 # held Energy placed before the shuffle
            if t == _PLAY and _is_supporter(i):                      # one-per-turn Supporter: after the
                return _TIER_SUPPORTER                               # free Item digs, before the blind attach
            if t == _ATTACH or (t == _PLAY and _cost_discard(i)):    # blind/costly commitment: after free dev
                return _TIER_COMMITMENT                              # THIS is `attach-energy-last` (ADR-0069
                                                                     # §7): the deleted −5 rung became this
                                                                     # deferral, so attach-late costs an attach
                                                                     # no SCORE — an irreversible commitment is
                                                                     # simply ORDERED after the draw/search that
                                                                     # would reveal a better target. Tier-aware
                                                                     # by construction: it stands DOWN against a
                                                                     # hand-shuffle finisher (tier 4 above), so
                                                                     # development → attach → hand-shuffle →
                                                                     # attack is structural, not a coincidence
                                                                     # of −5 vs −60. Score-invisible, which is
                                                                     # what let the desperation floor stop
                                                                     # depending on out-scoring that −5.
            if t == _PLAY and not self._informative_card(traces[i].card_id):  # ADR-0095 d1: an endorsed free
                return _TIER_COMMIT_FREE                             # PLAY that COMMITS a card at a target and
                                                                     # reveals nothing sequences behind the digs.
                                                                     # Everything above has already claimed the
                                                                     # exclusive/costly plays, so what reaches
                                                                     # here is exactly the free band — which is
                                                                     # the band the ADR says the boundary is
                                                                     # INSIDE. Scoped to `_PLAY`: an Evolve or
                                                                     # an Ability spends no card at a target,
                                                                     # and re-banding those is measurement this
                                                                     # ADR did not do.
            return _TIER_INFORMATIVE

        if any(_tier(i) < _TIER_ENDER for i in order):               # legibility: mark the held-back attacks
            for i in order:
                if options[i].get("type") == _ATTACK and _tier(i) == _TIER_ENDER:  # a winning attack not held
                    traces[i].deferred = True
        return sorted(order, key=_tier)                             # stable -> within a tier, score order
