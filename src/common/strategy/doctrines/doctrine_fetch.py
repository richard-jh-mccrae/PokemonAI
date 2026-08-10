"""DOCTRINE: Fetch (Search) — ADR-0023. One file, end to end.

A fetch is THREE decisions over one closed-form primitive
``fetch_value(card, board) = importance × still-lacking × available``: whether to play now, what to
grab, what to discard — so all three agree by construction. The scored sum of the `HYPOTHESES` rungs
below IS `fetch_value`; `FetchMixin` is the Pilot-side comparator/oracle plus greedy multi-pick.
"""
from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

from common.fetch_closure import (DEADNESS as _DEADNESS_READING, REACH as _REACH_READING,
                                  FETCH_DEADNESS_TARGETS as _FETCH_DEADNESS_TARGETS,
                                  FETCH_POKEMON_TARGETS as _FETCH_POKEMON_TARGETS)
from common.option_equivalence import canonical_keys
from common.strategy.context import (KO_SCORE, _ATTACH_TO, _ATTACK, _BENCH_MAX,
                                      _BENCH_PLACEMENT_CONTEXTS, _CARD, _DISCARD, _END,
                                      _ENGINE_TAGS, _OPENER_TAG,
                                      _MAIN, _PLAY, _SETUP_BENCH, _SUPPORTER, _THIN_BENCH,
                                      _TO_ACTIVE, _TO_BENCH,
                                      _TO_HAND, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis

# The two target-class scopes (ADR-0073) live in `fetch_closure`: `_FETCH_POKEMON_TARGETS` is the REACH
# scope, `_FETCH_DEADNESS_TARGETS` the wider DEADNESS scope. The per-card PREDICATE lives in the card.

class _Reading(NamedTuple):
    """The two readings this doctrine asks for (ADR-0073; ADR-0133 adds a third, for the reveal node):
    target scope, predicate mode, memo cache — a deadness answer in the reach memo is the unsoundness."""
    targets: frozenset
    mode: str
    cache_attr: str


#: The optimistic reading: what a search can be RELIED ON to pull. Feeds the endorsers.
_REACH = _Reading(_FETCH_POKEMON_TARGETS, _REACH_READING, "_fetch_cache")
#: The pessimistic reading: what a search could find AT ALL. Feeds the whiff veto and deadline gate.
_DEADNESS = _Reading(_FETCH_DEADNESS_TARGETS, _DEADNESS_READING, "_deadness_cache")

# PROBABLE-WHIFF threshold (ADR-0029): `dont-search-a-probable-whiff` fires when the best reachable
# target's hypergeometric P(still in deck) is below this. A SOUND whiff (P=0) is separate.
_WHIFF_PROB_THRESHOLD = 0.20

# Tutor-chain grab value (seam C). The per-hop discount < 1 buys the monotone-decay invariant: a direct
# target strictly outranks a tutor that merely reaches it. The floor is a noise floor; re-derive if regrilled.
_CHAIN_HOP_DISCOUNT = 0.75
_CHAIN_MAX_HOPS = 2
_CHAIN_OPENER_FLOOR = 10.0

# HELD-CARD-RISK exposure bar: a FREE fetch defers past the deadline only when the matched Read prices a
# live opponent hand-strip at least this. A costly fetch defers regardless — its cost is paid NOW.
_STRIP_ODDS_BAR = 0.5


def _is_reusable_energy(stat, tags) -> bool:
    """A reusable (non-discard) Energy card. The engine reports ``energyType == 0`` for Trainers AND
    colourless specials, so a typed Basic is ``energyType not in (None, 0)``."""
    return bool(stat and stat.hp == 0 and stat.energyType not in (None, 0)
                and "discard_eot" not in tags)


class FetchMixin:
    """The Pilot-side closed-form half of the Fetch doctrine. `_grab_value_of` IS `fetch_value` — the
    shared oracle behind grab, whether-to-play and greedy multi-pick."""

    def _recycle_dead_only(self, me: dict) -> bool:
        """True iff my discard's recycle pool is non-empty and EVERY member is a dead pick. Basic Energy
        is never dead; an unknown stat fails OPEN (counted live, never a false suppression)."""
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
        """The three deck-knowledge signals for a search/tutor PLAY: WHIFFS, a REDUNDANT wincon-tutor, and
        a BASELESS wincon-tutor. All three False off a PLAY or a card with no fetch clause."""
        if option.get("type") != _PLAY:
            return False, False, False
        deadness_set = self._fetch_deadness_set(cid)
        fetch_set = self._search_deck_set(cid)
        if not deadness_set and not fetch_set:
            return False, False, False
        # WHIFF reads the DEADNESS set (ADR-0073); the wincon-tutor questions below stay on the REACH
        # set — what a tutor can be RELIED ON to pull, not what it might touch.
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
        """The PROBABILISTIC complement to the SOUND whiff (ADR-0029): every still-reachable target sits
        below `_WHIFF_PROB_THRESHOLD`. Mutually exclusive with the sound whiff, which owns an empty set."""
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

    def _search_confirmed_hit(self, option: dict, cid, board, plan, obs=None) -> bool:
        """The POSITIVE deck-knowledge signal (ADR-0029): a fetchable card is PROVABLY still in the deck
        AND fills a real need, on the SAME rungs the real grab scores. Sound-or-silent."""
        if option.get("type") != _PLAY or not board.deck_known_counts:
            return False
        fetch_set = self._search_deck_set(cid)
        return any(board.deck_definitely_has(c) and self._grab_value_of(board, c, plan, obs=obs) > 0
                   for c in fetch_set)

    def _fetch_target_matches(self, clause: dict, stat, *, reading: str = _REACH_READING) -> bool:
        """True iff a card with ``stat`` matches a FETCH clause's target class. Delegates to
        `common.fetch_closure` (ADR-0065); ``reading`` picks which question is asked (ADR-0073)."""
        from common import fetch_closure
        return fetch_closure.fetch_target_matches(clause, stat, reading=reading)

    def _deck_fetch_set(self, cid, reading: _Reading) -> set:
        """The deck card ids ``cid``'s ``zone: deck`` FETCH clauses reach under ONE ``reading`` (ADR-0073).
        Deck-fixed, so memoised per card id in the READING's OWN cache — a shared memo would be unsound."""
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
                    if any(self._fetch_target_matches(cl, stat, reading=reading.mode)
                           for cl in clauses):
                        ids.add(tid)
            cache[cid] = ids
        return cache[cid]

    def _search_deck_set(self, cid) -> set:
        """The REACH set (ADR-0073): deck card ids ``cid`` can be RELIED ON to pull. What the ENDORSERS
        read; it must NOT widen to the deadness scope, or an endorsement is fabricated."""
        return self._deck_fetch_set(cid, _REACH)

    def _fetch_deadness_set(self, cid) -> set:
        """The DEADNESS set (ADR-0073): deck card ids ``cid`` could find AT ALL. Wider than the reach set
        on purpose and sound BECAUSE the consumer is a conjunction — over-inclusion can only suppress."""
        return self._deck_fetch_set(cid, _DEADNESS)

    def _chain_fetch_targets(self, cid) -> set:
        """The FULL-scope set of deck card ids ``cid``'s ``zone: deck`` FETCH clauses can pull — every
        clause class, unlike `_search_deck_set`'s Pokémon-only scope. Memoised per card id."""
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

    def _chain_grab_value(self, board, cid, plan, obs=None) -> float:
        """The discounted closure value of tutoring ``cid`` into hand. δ × the best reachable target's
        `_grab_value_of` (MAX, never a sum — a tutor fetches ONE card), through ITEM tutors only."""
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if stat is None:
            return 0.0
        if stat.is_supporter and board.supporter_played:
            return 0.0
        return self._chain_value_from(board, cid, plan, _CHAIN_MAX_HOPS, {cid}, {}, obs=obs)

    def _chain_value_from(self, board, cid, plan, hops: int, seen: set, memo: dict,
                          obs=None) -> float:
        """`_chain_grab_value`'s recursive leg. ``memo`` caches `_grab_value_of` per target for THIS call
        tree only — the value is board-bound and must never be cached across boards."""
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
                memo[tid] = self._grab_value_of(board, tid, plan, obs=obs)
            v = memo[tid]
            if tst is not None and tst.is_item:              # only an Item plays free the same turn
                v = max(v, self._chain_value_from(
                    board, tid, plan, hops - 1, seen | {tid}, memo, obs=obs))
            best = max(best, v)
        return _CHAIN_HOP_DISCOUNT * best

    def _spends_last_evolution_route(self, select: dict | None, board, cid) -> bool:
        """True iff grabbing ``cid`` here would consume the LAST free tutor reaching a WANTED evolution.
        Count-aware via the revealed pool, so it is SILENT while copies abound. Unknown facts → False."""
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

    def _grab_value_of(self, board, cid: int, plan, *, obs=None) -> float:
        """The grab comparator's value for fetching card `cid` into hand right now — the sum of the positive
        TO_HAND grab Hypotheses that fire, on the SAME rungs as the real grab (ADR-0023)."""
        from common.pilot import Context, _fires   # lazy re-export; Context/Board own module is
                                                   # `deciders.facts` (cycle-free import)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        roles = self.strategy.roles.get(cid, [])
        ctx = Context(
            plan=plan, select_context=_TO_HAND, option_type=_CARD, card_id=cid,
            card_is_line_preevo=cid in self._line_preevo_set(),
            card_is_wincon=cid in self._wincon_set(),
            card_is_starter=bool(stat and stat.hp > 0 and not stat.evolvesFrom),
            card_is_support=bool(stat and stat.hp > 0 and (_ENGINE_TAGS & set(tags))),
            card_stranded_evolution=cid in self._stranded_evolution_set(),
            card_is_top_fetch_priority=(cid == board.top_fetch_priority_id),
            card_is_redundant=cid is not None and cid in board.in_play_ids,   # f14 breadth stand-down
            roles=roles, tags=tags, stat=stat, board=board)
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        declared = sum(self._weight(h) for h in hyps
                       if _fires(h, ctx) and self._weight(h) > 0)
        if obs is None:
            return declared                 # compatibility for doctrine-level callers without a snapshot
        return max(declared, self._hypothetical_grab_value(obs, board, cid))

    def _fetch_fills_a_need(self, board, cid, plan, obs=None) -> bool:
        """True iff the fetch ``cid`` can pull a card I currently LACK — any still-reachable candidate with
        positive grab value. The whether-to-play lookahead, estimated before the search reveals."""
        fetch_set = self._search_deck_set(cid)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        return any(self._grab_value_of(board, c, plan, obs=obs) > 0 for c in reachable)

    def _fetch_play_value(self, obs: dict, board, ctx) -> float:
        """Net value of a deterministic fetch PLAY: delivered demand minus the spent card/cost.

        Clause combination comes from ``fetch_closure.reveal_legs``: conjunctions add one best
        target per leg, while exclusive choices take one best branch.  Every target is priced by
        :meth:`_grab_value_of`, hence by the shared needs ledger rather than a tutor-specific list.
        Conditional reveal windows (for example dig-7) leave benefit to the composer while this
        scorer still charges their certain card-consumption cost.
        """
        if ctx.option_type != _PLAY or ctx.card_id is None:
            return 0.0
        cost = self._role_value(ctx.card_id)
        picks = self._cost_picks(ctx.card_id)
        if picks:
            shed = self._cost_shed(obs, board, exclude_cid=ctx.card_id, picks=picks)
            if shed is not None:
                cost += max(0.0, shed.cost)
        if not self.effects:
            return -cost if ({"search", "dig", "recycle"} & set(ctx.tags)) else 0.0
        from common import fetch_closure
        clauses = tuple(cl for cl in self.effects.clauses(ctx.card_id)
                        if cl.get("kind") == "fetch")
        if not clauses:
            return 0.0
        if any(not fetch_closure.fetch_is_unconditional(cl) for cl in clauses):
            # Composer owns BOTH sides of a conditional window: it enumerates the delivered/whiff
            # boards, each of which already removes the played card. Charging only the cost here
            # would split one net across two layers and erase ADR-0095's structural information
            # ordering whenever Composer abstains on equivalent first steps.
            return 0.0
        try:
            relation, legs, _cap = fetch_closure.reveal_legs(clauses)
        except ValueError:
            return -cost

        me = self._my_player(obs)
        deck_ids = set(self.deck) - set(board.deck_empty_ids)
        discard_ids = {c.get("id") for c in (me.get("discard") or []) if c}

        def leg_value(clause) -> float:
            zone = clause.get("zone")
            pool = deck_ids if zone == "deck" else discard_ids if zone == "discard" else set()
            values = [self._grab_value_of(board, tid, ctx.plan, obs=obs) for tid in pool
                      if fetch_closure.fetch_target_matches(
                          clause, self.stats.get(tid) if self.stats else None)
                      and not (clause.get("dest") == "in_play"
                               and self._evolution_baseless(obs, tid))]
            return max(values, default=0.0)

        per_leg = [leg_value(clause) for clause in legs]
        benefit = sum(per_leg) if relation == "conjunction" else max(per_leg, default=0.0)
        return benefit - cost

    @staticmethod
    def _composed_first_step_opportunity(composed_result, composed_index: int) -> float | None:
        """The chosen first step's prize-equivalent edge over its best real alternative.

        This is an opportunity cost, not the chosen line's absolute gain over the root: replacing a
        first step forfeits only the margin by which it beat the next-best different first step.
        Same-first-step continuations are excluded because they do not represent an alternative
        action. End remains among the candidate/root alternatives at exactly zero continuation EV.
        """
        chosen = getattr(composed_result, "chosen", None)
        if chosen is None or chosen.first_index != composed_index:
            return None
        alternatives = [float(getattr(composed_result, "root_value", 0.0))]
        alternatives.extend(
            float(candidate.score)
            for candidate in getattr(composed_result, "selection_candidates", ())
            if candidate.first_index != composed_index and not candidate.coverage_gap)
        return max(0.0, float(chosen.score) - max(alternatives))

    def _fetch_sequence_override(self, obs: dict, select: dict, board, options: list, traces: list,
                                 composed_index: int, *, composed_result=None):
        """Keep a positive deterministic fetch ahead of the composer's selected first step.

        A quota-free Item can safely realize its already-netted benefit before any turn ender. A
        Supporter is narrower: it replaces End (whose opportunity is exactly zero) or another
        Supporter only when its net benefit beats Composer's converted first-step decision margin.
        Costed Items remain composer-owned.
        """
        if (select or {}).get("context") != _MAIN or not (0 <= composed_index < len(options)):
            return None
        composed_option = options[composed_index]
        if (composed_option.get("type") == _ATTACK
                and traces[composed_index].tactical >= KO_SCORE and board.active_can_ko
                and self._prize_value(self._opp_active(obs)) >= board.my_prizes_remaining):
            return None                         # the game ends; no future fetched value can be realised
        from common import fetch_closure

        def fetch_kind(i):
            option, trace = options[i], traces[i]
            if option.get("type") != _PLAY or trace.score <= 0 or trace.card_id is None:
                return None
            clauses = tuple(cl for cl in (self.effects.clauses(trace.card_id) if self.effects else ())
                            if cl.get("kind") == "fetch")
            if not clauses or any(not fetch_closure.fetch_is_unconditional(cl) for cl in clauses):
                return None
            stat = self.stats.get(trace.card_id) if self.stats else None
            if (stat is not None and getattr(stat, "is_item", False)
                    and self._cost_picks(trace.card_id) is None):
                return "quota-free-item"
            if stat is not None and getattr(stat, "is_supporter", False):
                return "supporter"
            return None

        composed = traces[composed_index]
        composed_stat = self.stats.get(composed.card_id) if (self.stats and composed.card_id) else None
        composed_supporter = bool(composed_stat and getattr(composed_stat, "is_supporter", False))
        from common import currency
        opportunity = self._composed_first_step_opportunity(composed_result, composed_index)
        supporter_opportunity = (currency.prize_to_damage(opportunity)
                                 if opportunity is not None else None)
        candidates = []
        for i in range(len(options)):
            kind = fetch_kind(i)
            if kind == "quota-free-item":
                candidates.append(i)
            elif (kind == "supporter"
                  and (composed_option.get("type") == _END
                       or (composed_supporter and supporter_opportunity is not None
                           and traces[i].score > supporter_opportunity))):
                candidates.append(i)
        if not candidates:
            return None
        winner = max(candidates, key=lambda i: (traces[i].score, traces[i].tactical, -i))
        if winner == composed_index:
            return None
        opportunity_label = 0.0 if supporter_opportunity is None else supporter_opportunity
        return winner, (f"cost-benefit: fetch net {traces[winner].score:.1f} exceeds "
                        f"the composed-action opportunity {opportunity_label:.1f}")

    def _fetched_playable_this_turn(self, obs: dict, cid, board) -> bool:
        """Could the fetched Pokémon ``cid`` be PLAYED this turn once in hand? An evolution needs a base in
        play since last turn, and no one evolves on their own first turn (rules.md §4). Unknown → OPEN."""
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
        """Is NEXT turn a CONCRETE deadline for the fetched Pokémon ``cid``? Only an evolution has one, and
        only with a base in play or in hand — no base at all is the dead-grab rungs' jurisdiction."""
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

    def _fetch_target_deferred(self, obs: dict, cid, board, plan) -> bool:
        """The DEADLINE leg of the held-card risk: every needed target of ``cid`` is unplayable this turn
        but playable next, so fetching now only exposes the card in hand. Fail-open on unknown facts."""
        fetch_set = self._search_deck_set(cid)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        needed = [c for c in reachable if self._grab_value_of(board, c, plan, obs=obs) > 0]
        if not needed:
            return False
        return all(not self._fetched_playable_this_turn(obs, c, board)
                   and self._fetched_playable_next_turn(obs, c, board) for c in needed)

    def _held_fetch_deferred(self, obs: dict, refresh_cid, board, plan) -> bool:
        """The fetch-LATE leg viewed from the hand: some fetch card I HOLD still fills a need whose every
        target is deferred past this turn, so a self-refresh would shuffle that plan-vehicle away."""
        return any(self._fetch_target_deferred(obs, hid, board, plan)
                   for hid in board.hand_ids if hid != refresh_cid)

    def _shed_signals(self, obs: dict, option: dict, tags: list, board, plan) -> tuple[bool, bool, bool]:
        """(sheds_junk, sheds_live, sheds_key) for a `cost_discard` fetch PLAY — the COST side of
        cost-netting (ADR-0023 amendment), read off the DECIDER's own shed assignment, not a ladder."""
        if option.get("type") != _PLAY or "cost_discard" not in tags:
            return False, False, False
        from common.card_worth import ACE_SPEC_TIER
        fetch_cid = self._option_card_id(obs, None, option)
        picks = self._cost_picks(fetch_cid)
        if picks is None:
            return False, False, False
        plan = self._cost_shed(obs, board, exclude_cid=fetch_cid, picks=picks)
        if plan is None:
            return False, False, False
        rows, cost = plan.rows, plan.cost
        junk = cost <= 0.0 and all(rows[i].get("pitch", 0) > 0 or rows[i].get("dup_hand")
                                   or rows[i].get("in_play") for i in plan.row_indices)
        return junk, cost > 0.0, cost >= ACE_SPEC_TIER

    def _cost_picks(self, card_id):
        """How many cards this card's `cost` takes, off `snapshot_coverage.COST_CARDS`. ``None`` for a card
        with no cost, or one whose cost names no fixed count (`discard_hand`, `bottom_2`)."""
        from common import board_delta, snapshot_coverage as sc
        for clause in board_delta.card_clauses(self.combat, card_id):
            value = clause.get("cost")
            if value is not None:
                return sc.COST_CARDS.get(value)
        return None

    def _top_fetch_priority_id(self, select: dict | None, exclude: frozenset = frozenset()) -> int | None:
        """The first id in `Strategy.fetch_priority` present in a search's revealed candidates — the combo
        deck's explicit grab override. ``exclude`` drops ids already acquired so the NEXT one surfaces."""
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
        """Board after prior picks, so Issue #388 decks keep their validated fetch comparator."""
        acquired = {cid for cid in acquired_ids if cid is not None}
        wincons = self._wincon_set()
        return replace(
            board,
            in_play_ids=board.in_play_ids | acquired,
            my_bench=board.my_bench + (len(acquired_ids) if bench_ctx else 0),
            wincon_in_play=board.wincon_in_play or bool(wincons & acquired),
            wincon_in_hand=board.wincon_in_hand or bool(wincons & acquired),
            support_in_play=board.support_in_play or any(self._is_support_id(cid) for cid in acquired),
            top_fetch_priority_id=self._top_fetch_priority_id(select, exclude=acquired))

    def _greedy_grab(self, obs: dict, select: dict, board, traces: list, options: list,
                     min_count: int, max_count: int) -> list[int]:
        """Doctrine-owned fallback: greedily reprice after each acquired card (ADR-0023)."""
        bench_ctx = select.get("context") in _BENCH_PLACEMENT_CONTEXTS
        canon = canonical_keys(options, obs)
        if bench_ctx:
            max_count = max(int(min_count),
                            min(int(max_count), _BENCH_MAX - int(board.my_bench or 0)))
        remaining = set(range(len(options)))
        current = traces
        chosen: list[int] = []
        acquired: list = []
        while len(chosen) < max_count and remaining:
            index = min(remaining, key=lambda i: self._order_key(current[i], canon[i], i))
            if len(chosen) >= min_count and (current[index].score < 0 if bench_ctx
                                             else current[index].score <= 0):
                break
            chosen.append(index)
            remaining.remove(index)
            acquired.append(current[index].card_id)
            if len(chosen) >= max_count or not remaining:
                break
            virtual = self._virtual_grab_board(board, select, acquired, bench_ctx)
            current = [self._option_trace(obs, select, virtual, option, i) if i in remaining
                       else current[i] for i, option in enumerate(options)]
        return chosen

    def _support_in_play(self, me: dict) -> bool:
        """True if any of my in-play Pokémon is an engine/support piece (an `_ENGINE_TAGS` Function Tag).
        The gap behind `fetch-the-support`: with an engine already online I needn't tutor another."""
        if not self.functions:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and (_ENGINE_TAGS & set(self.functions.tags(p.get("id"))))
                   for p in board)


# ── the need-gated rungs: their additive scored sum IS `fetch_value` (grab A/B, then discard C) ──
# The lone fetch guard rejects an impossible search; shared valuations are composer-owned (Issue #459).
HYPOTHESES = [
    Hypothesis(
        id="dont-search-an-empty-deck",
        rationale="A search whose complete legal target set is provably empty cannot produce a card.",
        when=lambda c: c.option_type == _PLAY and c.search_targets_exhausted,
        weight=-60, status="testing"),
]
