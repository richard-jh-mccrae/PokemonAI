"""`_finish_turn_last`: the tiering that sequences a turn's chosen options — informative plays first, the
turn-ending attack last. Structural, deliberately NOT scored."""
from __future__ import annotations


from common.deciders.facts import Board
from common.option_equivalence import canonical_keys
from common.strategy.context import (KO_SCORE, _ACTIVE, _ATTACH, _ATTACK, _END, _EVOLVE, _MAIN, _PLAY, _RETREAT,
                                     _SETUP_BENCH)


# `_finish_turn_last`'s bands (ADR-0095 decision 1, Issue #261 item 2f). NAMED because a renumbering
# expressed in bare integers has invisible missed occurrences.
_TIER_INFORMATIVE = 0   # free AND informative: digs, Bench fill, benched evolve; plus lethal/winning

_TIER_COMMIT_FREE = 1   # free but COMMITTING: a free PLAY spending a card at a target, revealing nothing.
                        # NOT a Tool — a Tool is an `_ATTACH`, so it takes _TIER_COMMITMENT instead.

_TIER_SUPPORTER = 2     # the one-per-turn Supporter (non-shuffle)

_TIER_COMMITMENT = 3    # blind / costly: the Energy attach, a `cost_discard` search

_TIER_SHUFFLE = 4       # a hand-SHUFFLE Supporter — it nukes the hand, so attach before it

_TIER_ENDER = 5         # the turn-ENDING attack, plus Retreat / End / non-beneficial options

#: Tags making a PLAY *informative* (ADR-0095 decision 1). Deliberately NOT `_ENGINE_KEEP_TAGS`, which
#: holds the same strings today but asks "is this a draw ENGINE worth keeping" — they may diverge.
_INFORMATIVE_TAGS = frozenset({"draw", "search", "dig"})


class OrderMixin:
    """The turn's sequencing: which chosen option goes first."""

    def _score_order(self, obs: dict, options: list, traces: list) -> list:
        """The menu ranked for `chosen`, canonically (ADR-0103, Issue #254). Unconditional — no OFF branch."""
        canon = canonical_keys(options, obs)
        return sorted(range(len(options)), key=lambda i: self._order_key(traces[i], canon[i], i))

    @staticmethod
    def _order_key(trace, canon: str, index: int) -> tuple:
        """ONE definition of "which option goes first" (ADR-0103 decision 5) — `_score_order` sorts with
        it, `_greedy_grab` takes its `min`. Two spellings is how a leg reaches one site and not the other."""
        return (-trace.score, not trace.attach_to_needy_line, canon, index)

    def _prefer_soonest_arming_evolve(self, order: list, options: list, traces: list) -> list:
        """Break an EXACT tie between EVOLVE options toward the body that arms soonest (ADR-0070
        amendment M, Issue #167). Tied evolves need NOT be adjacent, so permute them within their own slots."""
        def arm(i):
            w = getattr(traces[i], "evolve_working", None)
            return (w or {}).get("result", {}).get("arm") if w else None

        def is_evolve(i):
            return options[i].get("type") == _EVOLVE and arm(i) is not None

        out, n = list(order), len(order)
        i = 0
        while i < n:
            j = i
            while j + 1 < n and traces[out[j + 1]].score == traces[out[i]].score:
                j += 1
            slots = [k for k in range(i, j + 1) if is_evolve(out[k])]
            if len(slots) > 1:
                for slot, opt in zip(slots, sorted((out[k] for k in slots), key=arm)):
                    out[slot] = opt
            i = j + 1
        return out

    def _never_pre_bench(self, select: dict, chosen: list) -> list:
        """NEVER bench during Set Up (ADR-0086 decision 9, Issue #197) — deferring to my own turn 1 is
        weakly dominant. A filter, not a price. `_SETUP_BENCH` only; the Set-Up ACTIVE choice is untouched."""
        if select.get("context") != _SETUP_BENCH:
            return chosen
        return []

    def _empty_bench_forced(self, obs: dict, select: dict, board: Board, options: list,
                            order: list) -> list:
        """The post-setup EMPTY-BENCH guard (ADR-0086 decision 7): nothing to promote means one KO ends
        the match, so a deploy is TAKEN, not ranked. A filter — `_LINE_CAP`'s band bars it from being a score."""
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
        """Does PLAYING this card ENLARGE the information set? — ADR-0095 decision 1's classification.
        Untagged defaults to COMMITTING: a mis-classified dig costs ordering, a commitment costs a card."""
        if cid is None:
            return False
        st = self.stats.get(cid) if self.stats else None
        if st is not None and getattr(st, "is_pokemon", False):
            return True
        tags = self.functions.tags(cid) if self.functions else ()
        return bool(_INFORMATIVE_TAGS & set(tags))

    def _finish_turn_last(self, obs: dict, board: Board, options: list, traces: list, order: list,
                          max_count: int, select_context: int | None) -> list:
        """Sequence the turn's commitments LAST, into the `_TIER_*` bands (ADR-0095 decision 1, ADR-0131).
        Single-pick MAIN menus only; stable within a tier, so score order survives."""
        if max_count != 1 or len(order) < 2 or select_context != _MAIN:
            return order
        ko_available = any(options[i].get("type") == _ATTACK and traces[i].tactical >= KO_SCORE
                           for i in order)

        def _wins_now(i: int) -> bool:
            """A KO of the opp ACTIVE taking my LAST prize — nothing to develop for, so it goes first.
            Gated on `active_can_ko`: a bench SNIPE credits the Active's prize value and must not qualify."""
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

        # The KO-enabling-gust and wall-retreat tiers were DELETED by POC-T4/5 (Issue #386, ADR-0131).
        # The gust hole is TOTAL and unfilled — filed with its corpus frames in `tests/strategy/poc_t4_flips.py`.

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
            if t in (_ATTACH, _PLAY, _RETREAT) and traces[i].tactical >= KO_SCORE:
                return _TIER_INFORMATIVE   # unlocks a KO — take the win, don't dig first (REQ-GUST-0001)
            if t == _ATTACK and _wins_now(i):
                return _TIER_INFORMATIVE
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return _TIER_ENDER
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return _TIER_ENDER                                   # would forfeit an available KO
            if t == _PLAY and _is_gust_card(i) and board.active_can_ko:
                return _TIER_ENDER   # a gust SWAPS the defender: never ahead of a KO of the Active it forfeits
            if (t == _EVOLVE and o.get("inPlayArea") != _ACTIVE      # free development. `>= 0` not `> 0`: a
                    and traces[i].score >= 0):                       # same-line bench evolve nets exactly 0.0
                return _TIER_INFORMATIVE                             # (the LINE payoff is pre-credited, #167)
            # ADR-0131 decision 1: a free informative PLAY reaches the top band at score ZERO. `not fired`
            # is the load-bearing fence — 0 means *nothing priced it*, never *a rung NEUTRALISED it*.
            if (t == _PLAY and traces[i].score == 0 and not traces[i].fired
                    and not _cost_discard(i) and self._informative_card(traces[i].card_id)):
                return _TIER_INFORMATIVE
            if traces[i].score <= 0:                                 # only an endorsed action sequences early;
                return _TIER_ENDER                                   # a zero-priced ATTACH is attach-anyway,
                                                                     # the class ADR-0069 refused a floor for
            if t == _PLAY and _is_shuffle_refresh(i):                # hand-nuke: AFTER the Energy attach, so
                return _TIER_SHUFFLE                                 # held Energy placed before the shuffle
            if t == _PLAY and _is_supporter(i):                      # one-per-turn Supporter: after the
                return _TIER_SUPPORTER                               # free Item digs, before the blind attach
            if t == _ATTACH or (t == _PLAY and _cost_discard(i)):    # blind/costly commitment: after free dev.
                return _TIER_COMMITMENT                              # THIS is `attach-energy-last` (ADR-0069
                                                                     # §7), as an ORDERING with no score
            if t == _PLAY and not self._informative_card(traces[i].card_id):  # ADR-0095 d1: an endorsed free
                return _TIER_COMMIT_FREE                             # PLAY that commits a card and reveals
                                                                     # nothing sequences behind the digs
            return _TIER_INFORMATIVE

        if any(_tier(i) < _TIER_ENDER for i in order):               # legibility: mark the held-back attacks
            for i in order:
                if options[i].get("type") == _ATTACK and _tier(i) == _TIER_ENDER:
                    traces[i].deferred = True
        return sorted(order, key=_tier)                             # stable -> within a tier, score order
