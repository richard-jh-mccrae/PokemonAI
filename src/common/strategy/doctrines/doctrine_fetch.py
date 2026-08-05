"""DOCTRINE: Fetch (Search) — ADR-0023. One file, end to end.

A fetch presents a *choose-from-deck* select (Ultra Ball / Nest Ball / Mega Signal / Buddy-Buddy
Poffin; tags `search`/`dig`/`bench_fill`/`tutor_*`, NOT raw draw). It is THREE decisions over one
closed-form value primitive `fetch_value(card, board) = importance × still-lacking × available`:
(A) whether to play now, (B) what to grab, (C) what to discard — so the play-reason, the grab, and
the discard agree by construction. The scored sum of the `HYPOTHESES` rungs below IS `fetch_value`
(no monolithic function — the ADR-0008 idiom); `FetchMixin` is the Pilot-side comparator/oracle
(`_grab_value_of`) + greedy multi-pick (`_greedy_grab`) + the deck-knowledge whiff/redundant
signals. See docs/general-strategy.md and docs/adr/0023-fetch-is-a-shared-value-comparator.md.
"""
from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

from common.fetch_closure import (FETCH_DEADNESS_TARGETS as _FETCH_DEADNESS_TARGETS,
                                  FETCH_POKEMON_TARGETS as _FETCH_POKEMON_TARGETS)
from common.option_equivalence import canonical_keys   # ADR-0103: the grab's tie-break is a board
                                                       # fact (the fingerprint), never the menu index
from common.strategy.context import (_ATTACH_TO, _BENCH_MAX, _BENCH_PLACEMENT_CONTEXTS, _CARD,
                                      _DISCARD, _ENGINE_TAGS, _OPENER_TAG,
                                      _PLAY, _SETUP_BENCH, _SUPPORTER, _THIN_BENCH, _TO_ACTIVE, _TO_BENCH,
                                      _TO_HAND, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis

# The two target-class scopes (ADR-0073) live in `fetch_closure`, imported at the top of this file —
# `_FETCH_POKEMON_TARGETS` is the REACH scope `_search_deck_set` ranges over (the scope the retired
# `_FETCH_FILTERS` covered: bench_fill / tutor_mega / tutor_pokemon / rush_evolve), and
# `_FETCH_DEADNESS_TARGETS` is the wider DEADNESS scope `_fetch_deadness_set` ranges over. The
# per-card PREDICATE lives in the card REPRESENTATION — `card_effects.json` FETCH clauses (ADR-0032;
# hypergeometric-fetch-closure WP3), read by `_fetch_target_matches` — so the doctrine never
# re-encodes card knowledge in a private table.

class _Reading(NamedTuple):
    """One of the TWO readings of a fetch clause (ADR-0073), as a single value: the target-class
    scope, the clause-predicate mode, and the memo cache that holds its answers. They are bundled
    because they are co-determined — a deadness answer written into the reach memo is the precise
    unsoundness the ADR's build-time amendment exists to prevent, and passing three loose arguments
    leaves that mismatch constructible."""
    targets: frozenset
    deadness: bool
    cache_attr: str


#: The optimistic reading: what a search can be RELIED ON to pull. Feeds the endorsers.
_REACH = _Reading(_FETCH_POKEMON_TARGETS, False, "_fetch_cache")
#: The pessimistic reading: what a search could find AT ALL. Feeds the whiff veto and deadline gate.
_DEADNESS = _Reading(_FETCH_DEADNESS_TARGETS, True, "_deadness_cache")

# PROBABLE-WHIFF threshold (ADR-0029): `dont-search-a-probable-whiff` fires when best reachable target's
# hypergeometric P(still in deck) < this. Conservative (refuted ep82524455-f6: P~=0.98 stays above bar). SOUND whiff (P=0) is separate/unconditional.
_WHIFF_PROB_THRESHOLD = 0.20

# Tutor-chain grab value (seam C, built 2026-07-19 — plan doc retired; spec Round 9 §3: "a
# tutor's held value = the closure-reachable value, recursively free"). Per-hop discount < 1 buys the
# monotone-decay invariant — a direct target strictly outranks a tutor that merely reaches it at the
# same select, and each extra hop (a play that reveals nothing until resolved) decays further. 2-hop
# cap = the gamble's spec-verified one-turn Petrel → Item → target chain. The FLOOR is the flat
# draw-Supporter band (`grab-a-draw-supporter-in-setup` +10) the chain must out-promise to fire —
# it also silences noise chains (δ² × the +3 color tie-break ≈ 1.7).
_CHAIN_HOP_DISCOUNT = 0.75
_CHAIN_MAX_HOPS = 2
_CHAIN_OPENER_FLOOR = 10.0

# HELD-CARD-RISK exposure bar (hypergeometric-fetch-closure §Round 8 §5): a FREE fetch defers past
# the deadline only when the matched Read prices a live opponent hand-strip — `Board.opp_hand_strip_odds`
# (max `copies_left_odds` over the rep build's `hand_disruption` cards, fail-open 0.0) at least this.
# "More likely than not still in their deck"; a costly fetch defers regardless (its cost is paid NOW).
_STRIP_ODDS_BAR = 0.5


def _is_reusable_energy(stat, tags) -> bool:
    """A reusable (non-discard) Energy card: hp 0 with a real `energyType`, not tagged
    `discard_eot`. The engine reports `energyType == 0` for Trainers AND colourless specials
    (e.g. Ignition), so a typed Basic is `energyType not in (None, 0)`."""
    return bool(stat and stat.hp == 0 and stat.energyType not in (None, 0)
                and "discard_eot" not in tags)


class FetchMixin:
    """The Pilot-side closed-form half of the Fetch doctrine (mixed into `Pilot`). `_grab_value_of`
    IS `fetch_value` — the shared oracle behind grab (B), whether-to-play (A, `_fetch_fills_a_need`),
    and greedy multi-pick (`_greedy_grab`). Reads shared Pilot helpers (`_wincon_set`,
    `_line_preevo_set`, `_weight`, `_option_trace`) + the deck-knowledge `Board.deck_empty_ids`."""

    def _recycle_dead_only(self, me: dict) -> bool:
        """True iff my discard's recycle pool (Pokémon / Basic Energy — Night Stretcher's targets)
        is non-empty and EVERY member is a dead pick: a Pokémon this deck can never deploy from
        hand (`_stranded_evolution_set` — the setup-only Explosiveness opener). Basic Energy is
        never dead (always a future attach); an unknown stat fails OPEN (counted live, never a
        false suppression). The discard-side sibling of `dont-search-an-empty-deck`'s whiff
        oracle; backs `Board.recycle_dead_only` (ep83457493 f33)."""
        pool = live = 0
        stranded = self._stranded_evolution_set()
        for c in (me.get("discard") or []):
            cid = c.get("id") if c else None
            if cid is None:
                continue
            st = self.stats.get(cid) if self.stats else None
            if st is None:
                pool += 1
                live += 1                                # unknown facts: fail-open
            elif getattr(st, "hp", 0):                   # a Pokémon
                pool += 1
                if cid not in stranded:
                    live += 1
            elif getattr(st, "energyType", 0) not in (None, 0):   # a (typed) Energy card
                pool += 1
                live += 1
        return pool > 0 and live == 0

    def _search_signals(self, option: dict, cid, board) -> tuple[bool, bool, bool]:
        """The three deck-knowledge signals for a search/tutor PLAY (see Context): whether it WHIFFS
        (every card it can fetch is provably gone from the deck), whether it is a REDUNDANT
        wincon-tutor (it can fetch ONLY the win-condition, which you can't usefully deploy a second
        of), and whether it is a BASELESS wincon-tutor (it can fetch only the win-condition and there
        is NO base to deploy it onto and it isn't in hand/play — the fetched payoff sits dead). All
        three False off a PLAY / a card with no fetch clause (`_search_deck_set`).

        The wincon-tutor is redundant when a copy is already in HAND (a second is a dead dig) OR the
        win-condition is already IN PLAY with no base to evolve another onto (`not
        wincon_base_deployable` — no Line pre-evolution in play or hand): fetching a second Mega you
        cannot deploy burns the turn while a real need (a Bench body) goes unmet (ep83038055 f40).

        The wincon-tutor is baseless (DISTINCT from redundant — the win-condition is NEITHER in hand
        NOR in play) when its payoff has no immediate pre-evolution to deploy it onto: the fetched
        wincon just sits in hand and THIS tutor cannot fetch the missing base either. The turn-1
        premature-tutor shape (85164605:f6 — tutoring a Mega Starmie ex with no Staryu anywhere);
        the consuming veto (`dont-tutor-the-baseless-wincon-turn-one`) adds the turn / productive-
        alternative narrowing so the SOUND `play-a-tutor-for-the-unfound-wincon` setup case stays."""
        if option.get("type") != _PLAY:
            return False, False, False
        deadness_set = self._fetch_deadness_set(cid)
        fetch_set = self._search_deck_set(cid)
        if not deadness_set and not fetch_set:
            return False, False, False
        # WHIFF reads the DEADNESS set (ADR-0073) — a dig-7 Pokégear over a Supporter-empty deck
        # provably finds nothing, though it is no closure edge. The wincon-tutor questions below stay
        # on the REACH set: they ask what a tutor can be relied on to pull, not what it might touch.
        exhausted = bool(deadness_set) and all(c in board.deck_empty_ids for c in deadness_set)
        wincon = self._wincon_set()
        wincon_only = bool(wincon) and bool(fetch_set) and fetch_set <= wincon
        wincon_undeployable_in_play = board.wincon_in_play and not board.wincon_base_deployable
        redundant = (wincon_only
                     and (board.wincon_in_hand or wincon_undeployable_in_play))
        baseless = (wincon_only and not board.wincon_in_hand
                    and not board.wincon_in_play and not board.wincon_base_deployable)
        return exhausted, redundant, baseless

    def _search_probable_whiff(self, option: dict, cid, board) -> bool:
        """The PROBABILISTIC complement to `_search_signals`' SOUND `search_targets_exhausted`
        (ADR-0029): a search whose every still-REACHABLE fetch target is UNLIKELY to remain in the deck
        — the best reachable target's `Board.deck_contains_probability` is below `_WHIFF_PROB_THRESHOLD`,
        though not provably gone. Mutually exclusive with the sound whiff: it requires a target NOT in
        `deck_empty_ids` (an empty reachable set is the sound guard's certain whiff, left to it). False
        off a PLAY / a non-search / when any target is plausibly present (so a copy that could sit in the
        hidden prizes is never suppressed). Drives the soft `dont-search-a-probable-whiff`."""
        if option.get("type") != _PLAY:
            return False
        fetch_set = self._search_deck_set(cid)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        if not reachable:
            return False                          # all provably gone -> SOUND guard owns this whiff
        best = max(board.deck_contains_probability(c) for c in reachable)
        return best < _WHIFF_PROB_THRESHOLD

    def _search_confirmed_hit(self, obs: dict, option: dict, cid, board) -> bool:
        """The POSITIVE deck-knowledge signal for a search/tutor PLAY (ADR-0029): True iff a card the
        search's fetch clause can pull is PROVABLY still in the deck (`Board.deck_definitely_has` —
        the tracker's exact post-anchor counts) AND fills a real need (positive grab value, the SAME
        rungs the real grab scores — the ADR-0023 shared-oracle invariant). Sound-or-silent, mirroring
        the oracle it reads: False off a PLAY, before the tracker anchors the prizes, or for a card
        with no fetch clause — a positive endorsement is never asserted on a guess."""
        if option.get("type") != _PLAY or not board.deck_known_counts:
            return False
        fetch_set = self._search_deck_set(cid)
        return any(board.deck_definitely_has(c) and self._grab_value_of(obs, board, c) > 0
                   for c in fetch_set)

    def _fetch_target_matches(self, clause: dict, stat, *, deadness: bool = False) -> bool:
        """True iff a card with ``stat`` matches a FETCH clause's target class — the ONE predicate that
        REPLACED the tag-keyed `_FETCH_FILTERS`, shared by the doctrine's two set-builders and the
        gamble closure. Delegates to `common.fetch_closure` (WP7, ADR-0065) so the whole graph — this
        doctrine, the planner gamble outs, the card-worth keep-cost — reads ONE implementation.
        ``deadness`` selects the pessimistic reading (ADR-0073); see `fetch_closure`."""
        from common import fetch_closure
        return fetch_closure.fetch_target_matches(clause, stat, deadness=deadness)

    def _deck_fetch_set(self, cid, reading: _Reading) -> set:
        """The deck card ids ``cid``'s ``zone: deck`` FETCH clauses reach under ONE ``reading``
        (ADR-0073) — the shared body of `_search_deck_set` and `_fetch_deadness_set`. Empty for a card
        with no such clause. Deck-fixed, so memoised per card id, in the reading's OWN cache.

        The reading travels as one value rather than three co-determined arguments: target scope,
        predicate mode and memo cache must agree, and passing them separately makes the mismatch that
        would silently write a deadness answer into the reach memo constructible. That mismatch IS the
        unsoundness this ADR's build-time amendment exists to prevent, so it is made unrepresentable
        rather than merely avoided."""
        if cid is None:
            return set()
        cache = getattr(self, reading.cache_attr)
        if cid not in cache:
            clauses = [cl for cl in (self.effects.clauses(cid) if self.effects else ())
                       if cl.get("kind") == "fetch" and cl.get("zone") == "deck"
                       and cl.get("target") in reading.targets]
            ids: set = set()
            if clauses:
                for tid in set(self.deck):
                    stat = self.stats.get(tid) if self.stats else None
                    if any(self._fetch_target_matches(cl, stat, deadness=reading.deadness)
                           for cl in clauses):
                        ids.add(tid)
            cache[cid] = ids
        return cache[cid]

    def _search_deck_set(self, cid) -> set:
        """The REACH set (ADR-0073): deck card ids the search/tutor ``cid`` can be RELIED ON to pull —
        the POKÉMON targets of its ``zone: deck`` FETCH clauses, `dig`/`trigger` carriers rejected.

        This is the set the ENDORSERS read — `fetch-when-it-fills-a-need`, the deferral deadline
        (`_fetch_target_deferred`), the probabilistic whiff, and the wincon-tutor redundancy question.
        It must NOT widen with the deadness scope: a dig-7 Pokégear over a deck that still holds a
        Supporter would then claim it FILLS that need, when it can only probably reach it — a
        fabricated endorsement, the fail direction `fetch_closure` forbids. For "is this search
        dead?" use `_fetch_deadness_set`, which is a superset."""
        return self._deck_fetch_set(cid, _REACH)

    def _fetch_deadness_set(self, cid) -> set:
        """The DEADNESS set (ADR-0073): deck card ids the search/tutor ``cid`` could find AT ALL —
        every ``zone: deck`` FETCH target class (`_FETCH_DEADNESS_TARGETS`), `dig`/`trigger` carriers
        INCLUDED. The set the sound whiff question ranges over: the search is dead iff every member is
        provably gone (`Board.deck_empty_ids`), which both `dont-search-an-empty-deck` and the fetcher
        deadline gate (`gate_library.fetch_deploy_odds`) ask — one derivation, so the play side and
        the keep side cannot disagree about whether a card is dead.

        Wider than the reach set on purpose, and sound BECAUSE the consumer is a conjunction: adding a
        target makes `all(gone)` harder, so over-inclusion can only suppress a whiff claim, never
        fabricate one. That is what admits a `dig` clause here (a top-7 look over a deck holding zero
        Supporters provably finds nothing) and the documented over-inclusion of an energy-type lock on
        a Pokémon target. Empty for a card with no deck-zone fetch clause."""
        return self._deck_fetch_set(cid, _DEADNESS)

    def _chain_fetch_targets(self, cid) -> set:
        """The FULL-scope set of deck card ids card ``cid``'s ``zone: deck`` FETCH clauses can pull —
        every clause class (`trainer` / energy / Pokémon), unlike `_search_deck_set`'s Pokémon-only
        whiff scope. The tutor-chain GRAPH leg (seam C): deck-fixed, memoised per card id (the
        `_search_deck_set` discipline); clauses only via `fetch_closure.fetch_target_matches`, never
        a text parse (ADR-0065). Empty for a card with no such clause."""
        if cid is None:
            return set()
        if cid not in self._chain_target_cache:
            from common import fetch_closure
            clauses = [cl for cl in (self.effects.clauses(cid) if self.effects else ())
                       if cl.get("kind") == "fetch" and cl.get("zone") == "deck"]
            ids: set = set()
            if clauses:
                for tid in set(self.deck):
                    stat = self.stats.get(tid) if self.stats else None
                    if any(fetch_closure.fetch_target_matches(cl, stat) for cl in clauses):
                        ids.add(tid)
            self._chain_target_cache[cid] = ids
        return self._chain_target_cache[cid]

    def _chain_grab_value(self, obs: dict, board, cid) -> float:
        """The discounted closure value of tutoring card ``cid`` into hand — spec Round 9 §3 ("a
        tutor's held value = the closure-reachable value, recursively free"), backing
        `grab-the-chain-opener`. δ × the best reachable target's `_grab_value_of` (MAX, never a sum
        — a tutor fetches ONE card), recursing one more hop through ITEM tutors only (`_CHAIN_MAX_
        HOPS` = 2; a fetched Item plays free the same turn, a fetched Supporter does not — the
        gamble's `_supporter_*_tutor_reaches` post-Item precedent). A Supporter tutor with the
        one-per-turn slot already spent prices 0 (fail-closed: the chain is not free this turn;
        `card_unplayable_this_turn` additionally demotes). Reachability drops provably-gone targets
        (`deck_empty_ids`) and non-Energy cards already in hand (the value must be value you LACK —
        the chain-side mirror of `dont-grab-a-card-already-in-hand`). End values read the shared
        oracle, so every need stand-down is inherited and the chain DECAYS as needs are met — incl.
        `_greedy_grab`'s virtual board re-score. The chain rung itself never fires inside
        `_grab_value_of` (its reduced Context leaves `card_chain_value` 0), so the recursion is
        exactly this helper: cycle-safe via the path `seen` set (Petrel's `trainer` clause reaches
        Petrel), Item-only descent, and the hop cap. Endorser fail direction: unknown card → 0."""
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if stat is None:
            return 0.0
        if stat.is_supporter and board.supporter_played:
            return 0.0
        return self._chain_value_from(obs, board, cid, _CHAIN_MAX_HOPS, {cid}, {})

    def _chain_value_from(self, obs: dict, board, cid, hops: int, seen: set, memo: dict) -> float:
        """`_chain_grab_value`'s recursive leg: δ × max over card ``cid``'s reachable fetch targets
        of (the target's own grab value | one more Item hop). ``memo`` caches `_grab_value_of` per
        target for THIS call tree only — the value is board-bound, never cached across boards."""
        if hops <= 0:
            return 0.0
        best = 0.0
        for tid in self._chain_fetch_targets(cid):
            if tid in seen or tid in board.deck_empty_ids:
                continue
            tst = self.stats.get(tid) if self.stats else None
            if tid in board.hand_ids and not (tst is not None and tst.is_energy):
                continue                                     # already held: not value you lack
            if tid not in memo:
                memo[tid] = self._grab_value_of(obs, board, tid)
            v = memo[tid]
            if tst is not None and tst.is_item:              # only an Item plays free the same turn
                v = max(v, self._chain_value_from(obs, board, tid, hops - 1, seen | {tid}, memo))
            best = max(best, v)
        return _CHAIN_HOP_DISCOUNT * best

    def _spends_last_evolution_route(self, select: dict | None, board, cid) -> bool:
        """True iff grabbing chain-hop candidate ``cid`` at this TO_HAND search would consume the
        LAST free tutor reaching a WANTED evolution — an evolution still in the revealed pool whose
        base is in my play or hand and which no other free (non-`cost_discard`) tutor in the pool or
        my hand can still fetch. The scarcity-gated preserve-the-closure tie-break (seam C hop
        audit): with Makuhita down, its Hariyama is the coming want, and Fighting Gong's
        `basic_pokemon` clause can never reach a Stage 1 — spending the last Poké Pad as the hop
        closes the only free route (Ultra Ball reaches it too, but at discard-2: not a preserve).
        Count-aware via the revealed pool (a search select's exact within-frame deck), so it is
        SILENT while copies abound — spending one of four Poké Pads closes nothing. False off a
        TO_HAND reveal, for a non-tutor, and for a `cost_discard` candidate (already demoted;
        its loss is priced). Endorser fail direction: unknown facts → False."""
        if not select or select.get("context") != _TO_HAND or cid is None:
            return False
        tags = self.functions.tags(cid) if self.functions else []
        if "cost_discard" in tags:
            return False
        reach = self._chain_fetch_targets(cid)
        if not reach:
            return False
        pool = [c.get("id") for c in (select.get("deck") or []) if c]
        if pool.count(cid) != 1:
            return False                              # another copy remains: not the last route
        pool_set = set(pool)
        base_names = ({getattr(self.stats.get(b), "name", None)
                       for b in (board.in_play_ids | board.hand_ids)} - {None}
                      if self.stats else set())
        for e in reach:
            est = self.stats.get(e) if self.stats else None
            if est is None or not getattr(est, "evolvesFrom", None):
                continue                              # only an EVOLUTION names a future line want
            if e not in pool_set or e in board.hand_ids:
                continue                              # gone from the pool / already held
            if est.evolvesFrom not in base_names:
                continue                              # no base in play or hand: not (yet) wanted
            if not any(tid != cid
                       and "cost_discard" not in (self.functions.tags(tid) if self.functions else [])
                       and e in self._chain_fetch_targets(tid)
                       for tid in pool_set | board.hand_ids):
                return True                           # no other free route to the wanted evolution
        return False

    def _grab_value_of(self, obs: dict, board, cid: int) -> float:
        """The grab comparator's value for fetching card `cid` into hand right now — **the same
        quantity the real grab decides on** (the shared-oracle invariant, ADR-0023). The
        whether-to-play lookahead's per-candidate term.

        Delegates to `Pilot._grab_add_marginal`: ``keep_v2(hand u {cid}) - keep_v2(hand)``, in Worth
        points. Until ADR-0121 this summed the POSITIVE `_TO_HAND` Hypotheses over a reduced
        `Context` — a faithful mirror of the grab as it then was, because the grab was that rung
        ladder. Replacing the ladder without moving this too would have split the one oracle ADR-0023
        exists to keep whole: the play-reason would still be endorsing what the grab no longer valued.

        **The `> 0` gates its callers apply survive the swap, and read better than before.** A
        `keep_v2` marginal is ``V(superset) - V(subset)`` over a monotone assignment, so it is never
        negative and ``> 0`` means exactly *"this candidate covers a need nothing I already hold
        covers"* — which is what every caller was reaching for when it asked whether a rung fired.

        ``deck_backed`` is left at its default: every caller here is asking about a card still IN the
        deck (the lookahead ranges over `_search_deck_set`, the refresh over `deck_known_counts`), so
        the copy in question would leave the deck if taken."""
        return self._grab_add_marginal(obs, board, cid)

    def _fetch_fills_a_need(self, obs: dict, board, cid) -> bool:
        """True iff the fetch ``cid`` can pull a card I currently LACK from the deck — any still-reachable
        candidate (its fetch-clause set minus the provably-gone `deck_empty_ids`) whose grab value is
        positive. The whether-to-play lookahead: it estimates `best_grab_value > 0` from the known deck
        before the search reveals it. False for a non-fetch (empty fetch set)."""
        fetch_set = self._search_deck_set(cid)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        return any(self._grab_value_of(obs, board, c) > 0 for c in reachable)

    def _fetched_playable_this_turn(self, obs: dict, cid, board) -> bool:
        """Could the fetched Pokémon ``cid`` be PLAYED this turn once in hand? A Basic lands on the
        Bench now (unless full); an evolution needs an ELIGIBLE base already on my board — a body of
        its `evolvesFrom` name in play since last turn (`appearThisTurn` False) — and neither player
        may evolve on their own first turn (rules.md §4, rulebook L123-128). Unknown facts fail OPEN
        (playable), so the deferral veto reading this never fires on a guess. Exotic evolve-from-hand
        shortcuts are not modelled (none exist in the pool's Items; Salvatore's rush-evolve fetches
        from the DECK, bypassing the hand entirely)."""
        st = self.stats.get(cid) if self.stats else None
        if st is None or getattr(st, "hp", 0) <= 0:
            return True                              # unknown / non-Pokémon: never claim a deferral
        base = getattr(st, "evolvesFrom", None)
        if not base:
            return not board.bench_full              # a Basic benches right now (unless full)
        state = obs.get("current") or {}
        turn, first = state.get("turn"), state.get("firstPlayer")
        yi = state.get("yourIndex", 0)
        if turn is not None and first is not None and turn <= (1 if first == yi else 2):
            return False                             # neither player evolves on their own first turn
        players = state.get("players") or []
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        for body in (me.get("active") or []) + (me.get("bench") or []):
            if not body or body.get("appearThisTurn"):
                continue                             # new in play -> can't evolve this turn (§4 L96)
            bs = self.stats.get(body.get("id")) if self.stats else None
            if bs is not None and getattr(bs, "name", None) == base:
                return True
        return False

    def _fetched_playable_next_turn(self, obs: dict, cid, board) -> bool:
        """Is NEXT turn a CONCRETE deadline for the fetched Pokémon ``cid`` — i.e. will it provably
        become playable then? Only an evolution has one: by next turn the `appearThisTurn` and
        own-first-turn bans lapse, so a body of its base name already in play — or a held base
        benched this turn (Bench space) — receives it. False for a Basic (a full Bench has no
        modelled next-turn opening) and for an evolution with no base in play or hand (no deadline
        AT ALL — the dead-grab/baseless rungs own that, never the deferral)."""
        st = self.stats.get(cid) if self.stats else None
        if st is None or getattr(st, "hp", 0) <= 0:
            return False
        base = getattr(st, "evolvesFrom", None)
        if not base:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        for body in (me.get("active") or []) + (me.get("bench") or []):
            bs = self.stats.get(body.get("id")) if (body and self.stats) else None
            if bs is not None and getattr(bs, "name", None) == base:
                return True                          # eligible next turn whatever it is today
        if board.bench_full:
            return False
        return any((hs := self.stats.get(hid)) is not None and getattr(hs, "name", None) == base
                   for hid in board.hand_ids if self.stats)

    def _fetch_target_deferred(self, obs: dict, cid, board) -> bool:
        """The DEADLINE leg of the held-card risk (spec §Round 8 §5): every still-reachable NEEDED
        target of fetch ``cid`` (positive grab value — the same set `_fetch_fills_a_need` endorses)
        is provably unplayable this turn BUT playable next turn — a concrete deadline, so fetching
        now gains nothing over fetching then (a whole-deck search succeeds iff the target remains in
        deck — identical next turn) while the fetched key would sit in hand exposed across the
        opponent's turn. False when any needed target lands this turn, when a target has NO concrete
        deadline (a baseless payoff waits on nothing — the dead-grab rungs' jurisdiction), when
        nothing is needed, or on unknown facts (fail-open — a suppressor never fires on a guess)."""
        fetch_set = self._search_deck_set(cid)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        needed = [c for c in reachable if self._grab_value_of(obs, board, c) > 0]
        if not needed:
            return False
        return all(not self._fetched_playable_this_turn(obs, c, board)
                   and self._fetched_playable_next_turn(obs, c, board) for c in needed)

    def _held_fetch_deferred(self, obs: dict, refresh_cid, board) -> bool:
        """The fetch-LATE leg viewed from the hand: some fetch card I HOLD (other than the refresh
        being priced) still fills a need whose every target is deferred past this turn
        (`_fetch_target_deferred`). A self-refresh would shuffle that held plan-vehicle away — the
        very strip the deferral is guarding against — so `dont-shuffle-away-the-deferred-fetch`
        reads this to hold the hand instead. False with no such held fetch (fail-open)."""
        return any(self._fetch_target_deferred(obs, hid, board)
                   for hid in board.hand_ids if hid != refresh_cid)

    def _shed_signals(self, obs: dict, option: dict, tags: list, board, plan) -> tuple[bool, bool, bool]:
        """(sheds_junk, sheds_live, sheds_key) for a `cost_discard` fetch PLAY — the COST side of
        cost-netting (ADR-0023 amendment): what will the discard this search forces actually take?

        Priced by the equation that will take it (Issue #261 item 2h). Until then this scored the
        hand at a virtual `_DISCARD` Context against the tuned `_DISCARD` ladder, and the whole point
        of doing so was stated in its own docstring — *"scoring with the SAME rungs the real discard
        select uses keeps prediction and pick agreeing."* That stopped being true the day the
        keep-value v2 assignment took the discard select (2026-07-20) and the ladder stopped
        deciding, and it would have become
        vacuous the day the ladder was deleted: every score would be 0.0, all three bits permanently
        False, and the three rungs reading them silent forever (the Issue #238 shape). So the
        predictor moves onto the DECIDER's own machinery — the whole-hand v2 rows
        (`_needs_hand_rows`, the refresh SHED's), the shared resolver, and `needs.removal_score`, the
        objective `needs.cheapest_removal` minimises — and the sentence is true again.

        The three bands are that ONE number, the net cost of the two cards the assignment would
        actually shed:

          * ``junk`` — costs ``<= 0`` AND every shed card is either actively dead (``pitch`` > 0) or
            REPLACEABLE (a second copy held, or a copy already in play). The second clause is
            load-bearing and was measured, not assumed: v2 prices a redundant spare and a role-less
            singleton *identically* at keep 0, because neither costs anything to lose — but only the
            first is a card we still effectively have. Reading "costs nothing" as junk lifts a fetch
            paid for with genuine singletons into the free-dig band it has not earned, and flipped
            `test_neutral_sheds_leave_the_fetch_at_the_pessimism_baseline` on the first run. v1 drew
            the same three-way distinction through the ladder's `discard-the-redundant` (+20) and
            `discard-the-hand-duplicate` (+12) rungs; this is those premises at source.
          * ``live`` — costs ``> 0``: a real price is paid for the dig.
          * ``key``  — costs ``>= ACE_SPEC_TIER``: the price is at least an unrecoverable card's worth.
            The bar is the LOWEST tier the retired `keep-key-cards-at-discard` (-30) protected —
            wincon 30, ACE SPEC 25, burst Energy 30 (`card_worth.TAG_TIER`'s own reconciliation
            comment) — reused rather than re-invented, so no new constant enters the fit. Note the
            keep is MARGINAL, so a duplicated wincon prices its succession slot (~15) and correctly
            does not read as key: a second copy is not irreplaceable.

        All False off a PLAY / a free fetch / with < 2 other cards (engine legality)."""
        if option.get("type") != _PLAY or "cost_discard" not in tags:
            return False, False, False
        from common import needs
        from common.card_worth import ACE_SPEC_TIER
        fetch_cid = self._option_card_id(obs, None, option)
        rows = self._as_discard_rows(self._needs_hand_rows(obs, board, exclude_cid=fetch_cid),
                                     obs, board)
        if len(rows) < 2:
            return False, False, False
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = [0.0] * len(slots)            # a forced discard has no redraw window (as `_needs_v2`)
        intrinsics = [0.0] * len(rows)           # no v1 post-gate hedge exists over the HAND rows
        shed = needs.cheapest_removal(slots, elig, resupply, intrinsics, 2,
                                      **self._removal_ranking_legs(rows))
        cost = needs.removal_score(slots, elig, resupply, intrinsics, shed)
        junk = cost <= 0.0 and all(rows[i].get("pitch", 0) > 0 or rows[i].get("dup_hand")
                                   or rows[i].get("in_play") for i in shed)
        return junk, cost > 0.0, cost >= ACE_SPEC_TIER

    def _top_fetch_priority_id(self, select: dict | None, exclude: frozenset = frozenset()) -> int | None:
        """The highest-priority card id the deck WANTS most among a search's revealed candidates — the
        first id in `Strategy.fetch_priority` that is present in the select's `deck` list (Tier-3, the
        combo deck's explicit grab override). None off a TO_HAND search, an empty list, or no match.
        `exclude` drops ids already acquired this multi-pick so the NEXT priority surfaces (greedy)."""
        fp = getattr(self.strategy, "fetch_priority", None)
        if not fp or not select or select.get("context") != _TO_HAND:
            return None
        present = {c.get("id") for c in (select.get("deck") or []) if c} - set(exclude)
        return next((cid for cid in fp if cid in present), None)

    def _is_support_id(self, cid: int | None) -> bool:
        """True iff card `cid` is an engine/support Pokémon (hp > 0 with a draw/accel/search Ability) —
        the per-id form of `card_is_support`, used to close the `support_in_play` gap as one is grabbed."""
        if cid is None or not self.stats:
            return False
        st = self.stats.get(cid)
        tags = self.functions.tags(cid) if self.functions else []
        return bool(st and st.hp > 0 and (_ENGINE_TAGS & set(tags)))

    def _virtual_grab_board(self, board, select: dict, acquired_ids: list, bench_ctx: bool):
        """`board` as if the cards acquired so far this multi-pick were already had — the gap signals the
        grab rungs read (wincon/support in play, bench size, in-play ids, the next fetch-priority) close as
        needs are met, so greedy re-scoring won't re-pick an already-satisfied need (ADR-0023)."""
        acq = {a for a in acquired_ids if a is not None}
        wincon = self._wincon_set()
        return replace(
            board,
            in_play_ids=board.in_play_ids | acq,
            my_bench=board.my_bench + (len(acquired_ids) if bench_ctx else 0),
            wincon_in_play=board.wincon_in_play or bool(wincon & acq),
            wincon_in_hand=board.wincon_in_hand or bool(wincon & acq),
            support_in_play=board.support_in_play or any(self._is_support_id(a) for a in acq),
            top_fetch_priority_id=self._top_fetch_priority_id(select, exclude=acq))

    def _greedy_grab(self, obs: dict, select: dict, board, traces: list, options: list,
                     min_count: int, max_count: int) -> list[int]:
        """Resolve a fetch-grab multi-select (maxCount>1) greedily instead of static top-N: take the best
        candidate, mark its need satisfied (a virtual board where acquired cards count as had), re-score
        the rest, repeat. So a second copy of an already-met need stands down. TAKE-FEWER: once min_count
        is met, stop as soon as no remaining candidate has positive grab value — don't over-grab (e.g.
        bench a prize-liability body you don't need). ADR-0023; only for `_GRAB_CONTEXTS`.

        **The decline bar differs by context, and the difference is about who prices the COST**
        (Issue #261 item 2d). At a BENCH grab the Deploy Marginal prices the whole cost — the slot
        it displaces and the Prize-Path exposure it hands over — so a candidate at exactly 0 is one
        that genuinely costs nothing, and the search that revealed it is already spent. ADR-0086
        decision 6 says so in its own words: take-fewer "is how a BELOW-zero deploy expresses
        itself". Declining at 0 there is the Buddy-Poffin whiff. At a `_TO_HAND` grab there is no
        equation, only one-sided endorsement rungs, so 0 means "no rung spoke" rather than "free" —
        and a card taken into hand is not free (it thins the deck and must then be held). Those
        stay declined, which is also the `<= 0` bar every ruled fetch frame was captured under.

        The pick breaks an exact tie on the option's **Option Equivalence Class identity**, not on its
        menu index (ADR-0103, Issue #254). It cannot consume `_score_order`'s ordering directly —
        it re-scores between picks — so it takes the same `_order_key`, which is why that key is a
        function rather than a lambda at each site. The canonical keys are a pure function of the
        ORIGINAL menu, which the loop never permutes, so they are computed once."""
        bench_ctx = select.get("context") in _BENCH_PLACEMENT_CONTEXTS
        canon = canonical_keys(options, obs)
        if bench_ctx:
            # The Bench holds FIVE (`docs/rulebook.txt` L75, L122) — a game rule, so it bounds the
            # pick as a filter rather than through a price. The marginal is 0 for a body that cannot
            # be placed (there is no counterfactual for an impossible play), and the bench take-fewer
            # bar declines only BELOW zero, so without this bound the greedy would keep grabbing past
            # a full Bench. `min_count` still wins if the engine somehow asks for more, because
            # refusing a mandatory pick is the one failure worse than an over-grab.
            max_count = max(int(min_count),
                            min(int(max_count), _BENCH_MAX - int(board.my_bench or 0)))
        remaining = set(range(len(options)))
        cur = traces
        chosen: list[int] = []
        acquired: list = []
        while len(chosen) < max_count and remaining:
            i = min(remaining, key=lambda j: self._order_key(cur[j], canon[j], j))
            if len(chosen) >= min_count and (cur[i].score < 0 if bench_ctx else cur[i].score <= 0):
                break                                        # take-fewer: nothing more worth grabbing
            chosen.append(i)
            remaining.discard(i)
            acquired.append(cur[i].card_id)
            if len(chosen) >= max_count or not remaining:
                break
            vboard = self._virtual_grab_board(board, select, acquired, bench_ctx)
            cur = [self._option_trace(obs, select, vboard, o, k) if k in remaining else cur[k]
                   for k, o in enumerate(options)]
        return chosen

    def _support_in_play(self, me: dict) -> bool:
        """True if any of my in-play Pokémon is an engine/support piece — its Ability draws, accelerates
        or searches (an `_ENGINE_TAGS` Function Tag). The gap behind `fetch-the-support`: with an engine
        already online I needn't tutor another. False with no functions table."""
        if not self.functions:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and (_ENGINE_TAGS & set(self.functions.tags(p.get("id"))))
                   for p in board)


# ── the need-gated rungs: their additive scored sum IS `fetch_value` (grab A/B, then discard C) ──
HYPOTHESES = [
    Hypothesis(
        id="attach-off-color-at-fixed-recipient",
        rationale="At an ATTACH_TO (the recipient is FIXED by the effect — a Crispin/attach where you only pick "
                  "WHICH Energy, and every option scores 0 today), DEMOTE an Energy whose colour NO in-play body "
                  "can use — neither an attack cost nor an Ability fuel (`board.in_play_required_colors`). "
                  "Dumping {D} onto the dragon line when no {D}-body is in play is dead weight; the {P} it needs "
                  "for Phantom Dive isn't (dragapult f86, CRITICAL). The recipient isn't carried per-option in "
                  "this context, so this is a SOUND board-union floor: an off-board-colour Energy is wasted "
                  "regardless of which body receives it. −8 mirrors the +3 ToHand tie-break; silent for a "
                  "mono-colour deck (every colour on-board).",
        when=lambda c: c.select_context == _ATTACH_TO and bool(c.stat)
        and getattr(c.stat, "hp", 1) == 0 and getattr(c.stat, "energyType", None) not in (None, 0)
        and c.stat.energyType not in c.board.in_play_required_colors,
        weight=-8, status="testing"),
    Hypothesis(
        id="prefer-bench-fill-first",
        rationale="A `bench_fill` card (Buddy-Buddy Poffin) is best played FIRST in a thin deck: develops the "
                  "Bench, thins the deck (raises later draw/search quality), and feeds spread-Energy attacks. "
                  "Fires in SETUP and RACE (refill a KO-thinned Bench before the turn-ending attack); stands "
                  "down once the Bench is full.",
        when=lambda c: c.option_type == _PLAY
        and "bench_fill" in c.tags and c.board.my_bench < _BENCH_MAX,
        weight=15, status="testing"),
    Hypothesis(
        id="dont-search-an-empty-deck",
        rationale="A search/tutor is a dead card once the deck is PROVABLY empty of every card it can fetch "
                  "(`Context.search_targets_exhausted`: sound `deck_definitely_empty_of` + fetch-filter, all "
                  "copies accounted for outside the deck) — SOUND not probabilistic, so a copy that could sit "
                  "in hidden prizes stays silent. Outweighs `prefer-bench-fill-first`/`dig-before-commit`, "
                  "dropping a guaranteed-whiff search below End (mirrors `dont-rush-evolve-without-target`).",
        when=lambda c: c.option_type == _PLAY and c.search_targets_exhausted,
        weight=-60, status="testing"),
    Hypothesis(
        id="dont-recycle-the-dead",
        rationale="A discard-recycler (Function Tag `recycle`, Night Stretcher) is a wasted card when "
                  "EVERY target in my discard is dead — a Pokémon this deck can never deploy from hand "
                  "(the stranded-evolution set: the setup-only Explosiveness Cinderace) and no Basic "
                  "Energy. Recycling a dead card burns the Item AND jams the hand with an unplayable "
                  "card (ep83457493 f33: End turn ≻ Night Stretcher fetching Cinderace). Deck-static "
                  "and SOUND like `dont-search-an-empty-deck`; any Basic Energy or deployable Pokémon "
                  "in the discard keeps it silent.",
        when=lambda c: c.option_type == _PLAY and "recycle" in c.tags and c.board.recycle_dead_only,
        weight=-40, status="assumed"),
    Hypothesis(
        id="recover-to-refill-bench",
        rationale="Play a `recycle` Item (Night Stretcher) to refill a THIN Bench when the discard holds "
                  "a recoverable body (`not recycle_dead_only`) — an empty/thin Bench loses the game if "
                  "the Active is Knocked Out with nothing to promote (ep83667237 f87/f120: a Staryu sat "
                  "in the discard — the whole point of Night Stretcher — while the Bench was empty and "
                  "the agent attacked / refreshed instead). +22 sequences it TIER-0 (development) ahead "
                  "of a hand-refresh (`dig-before-commit` +20) and, via `_finish_turn_last`, before a "
                  "turn-ending attack — refill THEN attack. `dont-recycle-the-dead` (−40) owns the "
                  "all-dead-pool case, so the two never both fire.",
        when=lambda c: c.option_type == _PLAY and "recycle" in c.tags
        and c.board.my_bench < _THIN_BENCH and not c.board.recycle_dead_only,
        weight=22, status="assumed"),
    Hypothesis(
        id="dont-search-a-probable-whiff",
        rationale="PROBABILISTIC complement to `dont-search-an-empty-deck` (ADR-0029): reads "
                  "`Context.search_targets_unlikely` — best reachable target's hypergeometric P(deck still "
                  "contains it) below `_WHIFF_PROB_THRESHOLD` (common/deck_odds.py) — to softly stand a search "
                  "down. Mutually exclusive with the sound rung and weighted far above it (−25 vs −60, a guess "
                  "not a fact — only cancels a lone `dig-before-commit` +20); a plausibly-present copy (refuted "
                  "ep82524455-f6: 2-of-3 Staryu in 6 prizes → P ≈ 0.98) stays above the bar, unsuppressed.",
        when=lambda c: c.option_type == _PLAY and c.search_targets_unlikely,
        weight=-25, status="testing"),
    Hypothesis(
        id="search-the-confirmed-hit",
        rationale="The POSITIVE complement of the two whiff guards (ADR-0029): once the deck-tracker "
                  "has anchored the prizes (a search reveal → exact deck counts), a search whose "
                  "filter PROVABLY still reaches a needed card — `Board.deck_definitely_has` on a "
                  "target with positive grab value (the same rungs the real grab scores, the ADR-0023 "
                  "shared-oracle invariant) — is a CERTAIN hit: endorse the dig over sitting on it. "
                  "Sound-or-silent like the oracle it reads (`Context.search_confirmed_hit` stays "
                  "False before the anchor, so pre-anchor behavior is untouched) and mutually "
                  "exclusive with the sound veto by construction (a definitely-has target is never "
                  "definitely-empty). Stands aside for the redundant wincon-tutor — that dig is "
                  "`dont-tutor-the-held-wincon`'s case (−45), and endorsing what a veto owns would "
                  "just dilute it. Normal-band (+15, cf `prefer-bench-fill-first`): tips a marginal "
                  "dig toward the provable hit and orders certain digs above uncertain ones without "
                  "overriding any real lacking-need grab.",
        when=lambda c: c.option_type == _PLAY and c.search_confirmed_hit
        and not c.search_redundant_wincon,
        weight=15, status="assumed"),
    Hypothesis(
        id="dont-tutor-the-held-wincon",
        rationale="A tutor that can fetch ONLY the win-condition is redundant when a copy is already in HAND, "
                  "or the win-condition is IN PLAY with no base to evolve another onto (ep83038055 f40: a "
                  "benchless agent dug a useless 2nd Mega over a bench refresh) — `Context.search_redundant_wincon` "
                  "stands it down, actively penalizing to cancel `dig-before-commit`'s blanket endorsement. "
                  "Mirrors `play-a-tutor-for-the-unfound-wincon`'s gate; silent for a flexible tutor (fetch-set "
                  "not ⊆ the wincon).",
        when=lambda c: c.option_type == _PLAY and c.search_redundant_wincon,
        weight=-45, status="testing"),
    Hypothesis(
        id="dont-tutor-the-baseless-wincon-turn-one",
        rationale="Turn-1 premature-wincon-tutor veto (85164605:f6). A wincon-ONLY tutor whose payoff "
                  "has NO deployable base and isn't already in hand/play (`Context.search_baseless_wincon` "
                  "— fetch-set ⊆ the wincon, its immediate pre-evo neither in play nor hand, and this tutor "
                  "can't fetch that base) leaves the fetched Mega sitting DEAD; on turn 1 with a held Energy "
                  "to attach instead (`reusable_energy_in_hand` — charge the accelerator / develop a body) "
                  "the tutor is pure tempo waste (ms Mega Signal → Mega Starmie ex with no Staryu anywhere; "
                  "the human: 'fetching a Mega Starmie here doesn't help us'). Sized to CANCEL the whole "
                  "free-dig endorsement stack (`dig-before-commit` +20 + `fetch-when-it-fills-a-need` +8 + "
                  "`play-a-tutor-for-the-unfound-wincon` +25 = +53) and drive the tutor to score ≤0 → "
                  "`_finish_turn_last` tier 4 (behind the tier-2 attach and End) so the attach wins — merely "
                  "sinking it below the attach is NOT enough, a free PLAY at score>0 stays tier 0 and plays "
                  "FIRST. NARROW by design (`turn<=1` + a held Energy) so it never touches the SOUND "
                  "`play-a-tutor-for-the-unfound-wincon` setup case (tutor the in-deck wincon on a later "
                  "turn / when nothing more productive is available). Mirrors `dont-tutor-the-held-wincon` "
                  "(−45) in shape; a hair stronger to clear the +25 the redundant case doesn't stack. Seed; ladder-tuned.",
        when=lambda c: c.option_type == _PLAY and c.search_baseless_wincon
        and c.board.turn <= 1 and c.board.reusable_energy_in_hand,
        weight=-55, status="assumed"),
    Hypothesis(
        id="fetch-when-it-fills-a-need",
        rationale="Whether-to-PLAY a fetch (ADR-0023, decision A): play when the reachable deck set still holds "
                  "a card you LACK (`Context.fetch_fills_a_need`, same-rung lookahead). Fills the gap "
                  "`dig-before-commit` leaves for `cost_discard` fetches (Ultra Ball); modest weight sequences it "
                  "after free digs and BELOW `power-up-attacker` (+15, the ep82228640-fr7 shape). The +8 is the "
                  "NEUTRAL-shed band — the netting rungs (`costly-fetch-sheds-junk` / `dont-shed-a-*`) move it.",
        when=lambda c: c.option_type == _PLAY and c.fetch_fills_a_need,
        weight=8, status="testing"),
    Hypothesis(
        id="play-a-tutor-for-the-unfound-wincon",
        rationale="During SETUP, play a `tutor`-Roled card to dig for the win-condition (Role-keyed; which "
                  "card the search pulls is `fetch-the-wincon`/`fetch-energy-when-starved`). Stands down once "
                  "the wincon is in hand, or its fetch-set is provably exhausted (ep83117367: a wincon-only "
                  "tutor with every copy gone burns the turn on a whiff); folded from mega_starmie `tutor-the-wincon`.",
        when=lambda c: not c.board.line_ready and c.option_type == _PLAY and "tutor" in c.roles
        and not c.board.wincon_in_hand and not c.search_targets_exhausted,
        weight=25, status="assumed"),
    Hypothesis(
        id="costly-fetch-sheds-junk",
        rationale="Cost-netting, the junk band (ADR-0023 amendment): a `cost_discard` fetch whose 2 "
                  "predicted sheds cost the keep-value assignment nothing and are each dead or replaceable "
                  "(`Context.fetch_sheds_junk` — the two cards the v2 discard decider would actually "
                  "take) pays with dead cards, so it digs at the free band: +12 on `fetch-when-it-fills-a-need`'s +8 "
                  "matches `dig-before-commit` (+20). Gated on the need (a modifier of the "
                  "endorsement, not standalone); a `discard_fodder` deck's sheds score junk-positive, "
                  "so its costly digs ride here with no deck rule.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags
        and c.fetch_fills_a_need and c.fetch_sheds_junk,
        weight=12, status="testing"),
    Hypothesis(
        id="dont-shed-a-live-card",
        rationale="Cost-netting, the live band (ADR-0023 amendment): a `cost_discard` fetch forced to "
                  "shed a card the keep-value assignment charges for (`Context.fetch_sheds_live` — the "
                  "predicted shed costs > 0, e.g. an engine Supporter) trades a live card for "
                  "the dig: net the play below End (+8 − 20). Deliberately liftable — a provable "
                  "needed hit (`search-the-confirmed-hit` +15) still clears it, so shedding live for "
                  "a certain grab survives. A veto, so NOT gated on `fetch_fills_a_need`; the "
                  "ep83007714-f8 'tossing the supporters' shape.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_sheds_live,
        weight=-20, status="testing"),
    Hypothesis(
        id="dont-shed-a-key-card",
        rationale="Cost-netting, the key band (ADR-0023 amendment): the predicted shed costs at least an "
                  "unrecoverable card's worth (`Context.fetch_sheds_key` — ACE_SPEC_TIER, the lowest "
                  "tier the retired keep-key rung protected) — the discard would be forced to pitch a "
                  "LIVE wincon / an ACE SPEC / a burst Energy. Stacks on `dont-shed-a-live-card` to −45: net −37, "
                  "unliftable by any normal-band endorsement — never pitch an irreplaceable to dig.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_sheds_key,
        weight=-25, status="testing"),
    # `bench-the-supporter-tutor` (+25), `dont-pre-bench-the-supporter-tutor` (−15) and
    # `dont-pre-bench-a-redundant-utility` (−15) stood here until ADR-0086. All three answered the
    # SAME question — is this body worth a Bench slot right now? — from the fetch side, and the
    # Deploy Marginal now prices it: the tutor's Supporter fetch is the ability leg's need-matched
    # yield (zero at `_SETUP_BENCH` by derivation, since a pregame placement never triggers the
    # bench-drop Ability — the hand-written stand-down, derived), and a redundant utility body
    # prices its own displacement against the slot it would occupy.
    Hypothesis(
        id="hold-costly-fetch-when-line-assembled",
        rationale="The GRAB-side net of a DISCARD-cost fetch (the shed side is the `fetch_sheds_*` rungs): once "
                  "the win-condition line is ALREADY assembled (`wincon_in_hand` and `wincon_base_deployable`), "
                  "the only pull left is a redundant duplicate, not worth two cards. Cancels "
                  "`fetch-when-it-fills-a-need`'s +8 (ep83007714 f8: plays Ultra Ball over End with the line in "
                  "hand) — fires only on `cost_discard` fetches once the line is assembled, never blocking a "
                  "still-needed dig.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_fills_a_need
        and c.board.wincon_in_hand and c.board.wincon_base_deployable,
        weight=-12, status="testing"),
    Hypothesis(
        id="dont-costly-tutor-when-starved-and-developed",
        rationale="Don't pay a `cost_discard` Pokémon-tutor's two-card cost (Ultra Ball) while ENERGY-STARVED "
                  "(Active unpowered, no reusable Energy in hand) with the Bench ALREADY developed "
                  "(>= _THIN_BENCH). The tutor fetches a Pokémon — never the Energy you actually lack — and "
                  "you already have bodies, so what it grabs can't help THIS turn (unpowered you can't attack, "
                  "and an early setup turn can't evolve either) while the discard bleeds two cards: save it "
                  "(ep83967841 f17: Ultra Ball over End with Riolu + Solrock + 2 Lunatone down and 0 Energy). "
                  "−30 nets the play below End, cancelling `search-the-confirmed-hit` (+15) + "
                  "`fetch-when-it-fills-a-need` (+8). Tightly gated: stands down on a THIN bench (you need "
                  "bodies then, the tutor earns its cost) and once the Active is powered (a real dig, not a "
                  "starved durdle).",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and "tutor_pokemon" in c.tags
        and c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand
        and c.board.my_bench >= _THIN_BENCH,
        weight=-30, status="assumed"),
    Hypothesis(
        id="dont-fetch-before-the-deadline",
        rationale="The held-card risk's fetch-EARLY leg (hypergeometric-fetch-closure §Round 8 §5; "
                  "the held-card-risk seam, built 2026-07-19). A whole-deck search succeeds iff its "
                  "target remains in deck "
                  "— identical next turn — so when EVERY needed target is provably unplayable this "
                  "turn yet lands at a CONCRETE next-turn deadline (`Context.fetch_target_deferred`: "
                  "an evolution whose base is down but new-in-play / blocked only by my own first "
                  "turn, rules.md §4 — never a baseless payoff, which has no deadline and belongs to "
                  "the dead-grab rungs), fetching NOW buys zero "
                  "tempo while it (a) pays a `cost_discard` two-card price a turn early and (b) holds "
                  "the fetched key across the opponent's turn, exposed to their symmetric refreshes "
                  "(Judge/Harlequin — the Read's `opp_hand_strip_odds`). Fetch-late dominates: the "
                  "target waits IN the deck where no hand-strip touches it (ep85163634 f17: turn-2 "
                  "Ultra Ball for a Mega Starmie ex no Staryu can receive until next turn; the human: "
                  "'no cost to just wait a turn'). Gated to a fetch that pays its cost now "
                  "(`cost_discard`) OR a FREE fetch under a LIVE strip read (≥ `_STRIP_ODDS_BAR`, "
                  "fail-open 0.0 — no rep → no exposure claimed → no veto). −60 cancels the whole "
                  "endorsement stack (confirmed-hit 15 + need 8 + wincon-tutor 25 + junk-shed 12), "
                  "driving the play ≤ 0 → tier 4 behind the attack (the "
                  "`dont-tutor-the-baseless-wincon-turn-one` sizing idiom). The starved-and-developed "
                  "board is EXCLUDED: `dont-costly-tutor-when-starved-and-developed` (−30) already "
                  "prices that jurisdiction and the currency-zone rule forbids stacking a second "
                  "deferral price beside it (replace, not stack).",
        when=lambda c: c.option_type == _PLAY and c.fetch_target_deferred
        and ("cost_discard" in c.tags or c.board.opp_hand_strip_odds >= _STRIP_ODDS_BAR)
        and not ("cost_discard" in c.tags and "tutor_pokemon" in c.tags
                 and c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand
                 and c.board.my_bench >= _THIN_BENCH),
        weight=-60, status="assumed"),
    Hypothesis(
        id="dont-shuffle-away-the-deferred-fetch",
        rationale="The held-card risk's fetch-LATE leg realised by OUR OWN refresh (spec §Round 8 §5: "
                  "fetch-late's re-access risk). While a held fetch's needed grab is DEFERRED to next "
                  "turn (`Context.refresh_shuffles_deferred_fetch` — the same deadline predicate that "
                  "just stood the fetch itself down), a `shuffle_hand` self-refresh shuffles the "
                  "plan's vehicle into the deck: the exact strip the deferral guards against, "
                  "self-inflicted. −20 cancels the flat speculative CYCLE credit (the refresh, like "
                  "the fetch, can wait a turn), so a plan-holding hand attacks/develops instead "
                  "(ep85163634 f17: with Ultra Ball correctly held, Lillie's Determination at +11.7 "
                  "was next in line to nuke the very hand the plan needs). A refresh with REAL "
                  "certain value (a Judge stripping a tailored opponent hand) still clears it on its "
                  "strip credits; the graded shed's role-tier can't see this PLAN signal, which is "
                  "what keeps the rung out of the keep-cost currency (a PLAN premise, unlike the "
                  "retired `hold-successor-when-doomed`, whose DEADLINE premise folded into the "
                  "pressure gate 2026-07-19).",
        when=lambda c: c.option_type == _PLAY and "shuffle_hand" in c.tags
        and c.refresh_shuffles_deferred_fetch,
        weight=-20, status="assumed"),
    Hypothesis(
        id="demote-needless-search-supporter-in-setup",
        rationale="During SETUP, a bare narrow `search` Supporter (Team Rocket's Petrel — search your deck for "
                  "ONE Trainer) whose search fills no modeled need (`not fetch_fills_a_need`) is NOT an "
                  "endorsed early play: it burns the once-per-turn Supporter slot for ~0 net cards while a "
                  "full-hand refresh (Lillie's Determination, draw 6) develops the whole hand. −20 EXACTLY "
                  "neutralises `dig-before-commit` (+20) so the tutor nets 0 → `_finish_turn_last` drops it "
                  "from tier 1 (endorsed non-shuffle Supporter, sequenced AHEAD of everything) to tier 4 "
                  "(score ≤ 0), so a tier-3 shuffle-refresh now out-sequences it and wins the mutually-"
                  "exclusive Supporter slot (ep83966336 f27: Petrel over Lillie's with a Supporter already in "
                  "hand). Netting to EXACTLY 0 (not below) keeps it tied with End, so it still plays as the "
                  "ONLY dig (tie broken to the tutor). Gated to a `search` Supporter with no need-hit, so a "
                  "genuinely useful tutor (a fetch-filter that reaches a lacked card) is untouched. NB: the "
                  "fix is a sequencing threshold, not a ranking margin — gated by "
                  "tests/strategy/test_setup_resource_discipline.py, not just the weight fit.",
        when=lambda c: not c.board.line_ready and c.option_type == _PLAY   # pre-payoff (ADR-0040
        and "search" in c.tags and not c.fetch_fills_a_need                # gate-ban migration:
        and bool(c.stat and getattr(c.stat, "is_supporter", False)),      # was plan==SETUP)
        weight=-20, status="assumed"),
]
