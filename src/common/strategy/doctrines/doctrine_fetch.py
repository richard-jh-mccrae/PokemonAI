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

from common.strategy.context import (_BENCH_MAX, _CARD, _DISCARD, _ENGINE_TAGS, _PLAY, _SETUP_BENCH,
                                      _THIN_BENCH, _TO_ACTIVE, _TO_BENCH, _TO_HAND, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis, Plan

# A deck-search's FETCH FILTER — what set of cards it can pull OUT of the deck, as a predicate over
# the engine CardStat — keyed by the curated behavioral Function Tag that names the filter (the same
# escape-hatch tags as `bench_fill`; structural categories like megaEx stay on CardStat, the runtime
# reads them here rather than duplicating them as tags). The shared basis for the deck-knowledge
# whiff / redundancy signals: a search whose every legal target is provably gone (or already held)
# is a dead card. Extend per new search card by adding its filter tag + predicate.
_FETCH_FILTERS = {
    "bench_fill": lambda st: st.hp > 0 and not st.evolvesFrom,    # Basic Pokémon (Buddy-Buddy Poffin)
    "tutor_mega": lambda st: bool(getattr(st, "megaEx", False)),  # a Mega Evolution ex (Mega Signal)
    "tutor_pokemon": lambda st: st.hp > 0,                        # any Pokémon (Ultra Ball)
}


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

    def _search_signals(self, option: dict, tags: list, board) -> tuple[bool, bool]:
        """The two deck-knowledge signals for a search/tutor PLAY (see Context): whether it WHIFFS
        (every card it can fetch is provably gone from the deck) and whether it is a REDUNDANT
        wincon-tutor (it can fetch ONLY the win-condition, which is already in hand). Both False off
        a PLAY / a card with no known fetch-filter (cf. `_FETCH_FILTERS`)."""
        if option.get("type") != _PLAY:
            return False, False
        fetch_set = self._search_deck_set(tags)
        if not fetch_set:
            return False, False
        exhausted = all(cid in board.deck_empty_ids for cid in fetch_set)
        wincon = self._wincon_set()
        redundant = bool(wincon) and fetch_set <= wincon and board.wincon_in_hand
        return exhausted, redundant

    def _search_deck_set(self, tags: list) -> set:
        """The set of card ids in my deck a search with these fetch-filter tags can pull OUT of the
        deck (union over the card's `_FETCH_FILTERS` tags; empty for a non-search / unknown filter).
        Each filter's deck-set is deck-fixed, so it is memoised per tag."""
        result: set = set()
        for tag in tags:
            pred = _FETCH_FILTERS.get(tag)
            if pred is None:
                continue
            if tag not in self._fetch_cache:
                ids = set()
                for cid in set(self.deck):
                    stat = self.stats.get(cid) if self.stats else None
                    if stat and pred(stat):
                        ids.add(cid)
                self._fetch_cache[tag] = ids
            result |= self._fetch_cache[tag]
        return result

    def _grab_value_of(self, board, cid: int, plan) -> float:
        """The grab comparator's value for fetching card `cid` into hand right now — the sum of the
        positive TO_HAND grab Hypotheses that fire for it, scored with the SAME rungs as the real grab
        (the shared-oracle invariant, ADR-0023). The whether-to-play lookahead's per-candidate term."""
        from common.pilot import Context, _fires   # lazy: Context/Board live in pilot (cycle-free import)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        roles = self.strategy.roles.get(cid, [])
        ctx = Context(
            plan=plan, select_context=_TO_HAND, option_type=_CARD, card_id=cid,
            card_is_line_preevo=cid in self._line_preevo_set(),
            card_is_wincon=cid in self._wincon_set(),
            card_is_starter=bool(stat and stat.hp > 0 and not stat.evolvesFrom),
            card_is_support=bool(stat and stat.hp > 0 and (_ENGINE_TAGS & set(tags))),
            card_is_top_fetch_priority=(cid == board.top_fetch_priority_id),
            roles=roles, tags=tags, stat=stat, board=board)
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        return sum(self._weight(h) for h in hyps if _fires(h, ctx) and self._weight(h) > 0)

    def _fetch_fills_a_need(self, board, tags: list, plan) -> bool:
        """True iff a fetch with these tags can pull a card I currently LACK from the deck — any
        still-reachable candidate (its fetch-filter set minus the provably-gone `deck_empty_ids`) whose
        grab value is positive. The whether-to-play lookahead: it estimates `best_grab_value > 0` from the
        known deck before the search reveals it. False for a non-fetch (empty fetch set)."""
        fetch_set = self._search_deck_set(tags)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        return any(self._grab_value_of(board, cid, plan) > 0 for cid in reachable)

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
        bench a prize-liability body you don't need). ADR-0023; only for `_GRAB_CONTEXTS`."""
        bench_ctx = select.get("context") in (_TO_BENCH, _SETUP_BENCH)
        remaining = set(range(len(options)))
        cur = traces
        chosen: list[int] = []
        acquired: list = []
        while len(chosen) < max_count and remaining:
            i = max(remaining, key=lambda j: (cur[j].score, -j))
            if len(chosen) >= min_count and cur[i].score <= 0:
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
        id="fetch-the-wincon",
        rationale="When a search lets you choose which card to take into your hand (e.g. Ultra Ball), "
                  "pull your win-condition / primary attacker first — getting the payoff into hand is "
                  "the highest-value fetch, because you can then develop it on your own terms. Fires "
                  "off the universal `win_condition` / `primary_attacker` Role, so any deck inherits "
                  "it. Stands down when the payoff is ALREADY in play (no dead second copy) and when "
                  "you are energy-starved (0 Energy on the Active, none in hand) — there "
                  "`fetch-energy-when-starved` should win, since a Pokémon you can't power does nothing.",
        when=lambda c: c.select_context == _TO_HAND and bool(_WINCON_ROLES & set(c.roles))
        and not c.board.wincon_in_play
        and not (c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand),
        weight=30, status="testing"),
    Hypothesis(
        id="fetch-energy-when-starved",
        rationale="When a search lets you choose a card AND your Active has no Energy and you have "
                  "none in hand, take a reusable Basic Energy — you need to power an attack now, and "
                  "a Pokémon or a discard-at-end-of-turn Energy (Ignition) won't do that. This also "
                  "prefers a reusable Basic over a discard Energy at the same search.",
        when=lambda c: c.select_context == _TO_HAND and c.board.my_active_energy == 0
        and not c.board.reusable_energy_in_hand and _is_reusable_energy(c.stat, c.tags),
        weight=25, status="testing"),
    Hypothesis(
        id="prefer-bench-fill-first",
        rationale="A card that fetches Basics straight onto your Bench (Function Tag `bench_fill`, "
                  "e.g. Buddy-Buddy Poffin) is best played FIRST in a thin deck — it develops the "
                  "Bench and shrinks the deck, raising the quality of every later draw/search, and "
                  "feeds spread-Energy attacks (e.g. Cinderace loading the Bench). Played in setup "
                  "AND while racing (refill a Bench thinned by knockouts before the turn-ending "
                  "attack). Stands down once the Bench is full, where a bench-filler places nothing.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "bench_fill" in c.tags and c.board.my_bench < _BENCH_MAX,
        weight=15, status="testing"),
    Hypothesis(
        id="dont-search-an-empty-deck",
        rationale="A deck-search / tutor (Buddy-Buddy Poffin → Basic Pokémon to the Bench; Mega "
                  "Signal → a Mega Evolution ex; Ultra Ball → any Pokémon) is a dead card once the "
                  "deck holds none of what it can fetch. Stand it down when the deck is PROVABLY "
                  "empty of EVERY card the search can pull — all copies accounted for OUTSIDE the "
                  "deck (hand + discard + board + revealed prizes vs the known 60-card list), read "
                  "off `Context.search_targets_exhausted` (built on the sound `deck_definitely_empty_of`"
                  " + each card's fetch-filter). SOUND, never probabilistic: a copy that could still "
                  "sit in the hidden prizes leaves the signal silent, so the search is suppressed "
                  "only when the whiff is CERTAIN — keep the spare card rather than burn it. Outweighs "
                  "`prefer-bench-fill-first` / `dig-before-commit` so a guaranteed-whiff search drops "
                  "below End. (Mirrors `dont-rush-evolve-without-target` for a tutor with no target.)",
        when=lambda c: c.option_type == _PLAY and c.search_targets_exhausted,
        weight=-60, status="testing"),
    Hypothesis(
        id="dont-tutor-the-held-wincon",
        rationale="A tutor that can fetch ONLY the win-condition (e.g. Mega Signal → a Mega "
                  "Evolution ex, the deck's lone Mega being the payoff) is redundant once the "
                  "win-condition is already in hand — it would only dig a second, dead copy. Stand "
                  "it down (read off `Context.search_redundant_wincon`: the search's fetch-set ⊆ the "
                  "win-condition set AND `wincon_in_hand`) so the agent develops / attaches instead "
                  "of burning the turn on a useless dig. Mirrors the deck's `tutor-the-wincon` gate "
                  "(`not wincon_in_hand`) but ACTIVELY penalises, cancelling `dig-before-commit`'s "
                  "blanket endorsement of any search. Stays silent for a flexible tutor (Ultra Ball "
                  "can also fetch a pre-evolution / opener, so its fetch-set isn't ⊆ the wincon).",
        when=lambda c: c.option_type == _PLAY and c.search_redundant_wincon,
        weight=-45, status="testing"),
    Hypothesis(
        id="prefer-wincon-line-piece",
        rationale="When fetching a card into hand (a search), prefer one that builds your win-"
                  "condition LINE — a pre-evolution on the path to the payoff (e.g. Staryu → Mega "
                  "Starmie) over an off-line opener / accelerator (e.g. Cinderace). At a PROMOTE "
                  "(bring a benched Pokémon to the Active Spot) only do this when the payoff is in "
                  "hand to evolve it THIS turn — otherwise promoting a bare pre-evolution just "
                  "exposes your fragile evolution base (see `promote-the-staller`). Ranks below "
                  "`fetch-the-wincon` (the payoff itself) and `fetch-energy-when-starved`.",
        when=lambda c: c.card_is_line_preevo and (
            c.select_context == _TO_HAND
            or (c.select_context == _TO_ACTIVE and c.board.wincon_in_hand)),
        weight=18, status="testing"),
    Hypothesis(
        id="fetch-a-starter",
        rationale="When a search lets you choose a card AND your board is underdeveloped (fewer than "
                  "two benched Pokémon in SETUP), take a startable Basic Pokémon — a body you can play "
                  "down to develop the Bench and open a turn of plays. The fallback grab rung beneath "
                  "the win-condition rungs (`fetch-the-wincon` / `prefer-wincon-line-piece`): when no "
                  "Line piece is on offer you still want board presence over an off-need card. Gap-gated "
                  "— stands down once the Bench is developed (you no longer lack a starter). 'Starter' "
                  "is derived structurally (a Basic: hp > 0, no `evolvesFrom`), so any deck inherits it.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_starter
        and c.plan == Plan.SETUP and c.board.my_bench < _THIN_BENCH,
        weight=12, status="testing"),
    Hypothesis(
        id="bench-fill-a-basic",
        rationale="At a bench-PLACEMENT grab (a card that puts Basics straight onto the Bench — "
                  "Buddy-Buddy Poffin's `_TO_BENCH`, or the Set-Up `_SETUP_BENCH` placement), take a "
                  "startable Basic. The bench-context mirror of `fetch-a-starter` (which is gated to a "
                  "`_TO_HAND` hand-search): a bench-placement candidate is a CARD-target option, so the "
                  "`option_type==_PLAY` bench reflexes (keep-a-bench / pre-position-attacker) never see "
                  "it and EVERY candidate would otherwise score 0 — at which point the greedy take-fewer "
                  "(min_count 0) benches NOTHING (the Buddy-Poffin whiff that cost ~3:1 in the mirror). A "
                  "small positive develops the Bench (free bodies, deck-thinning, spread-Energy targets). "
                  "Skips a multi-prizer (an ex / Mega ex liability — `dont-bench-multiprize` is `_PLAY`-"
                  "gated so it can't guard a CARD candidate) and stands down once the Bench is full.",
        when=lambda c: c.select_context in (_TO_BENCH, _SETUP_BENCH) and c.card_is_starter
        and c.board.my_bench < _BENCH_MAX
        and not (c.stat and (getattr(c.stat, "ex", False) or getattr(c.stat, "megaEx", False))),
        weight=12, status="testing"),
    Hypothesis(
        id="fetch-the-support",
        rationale="When a search lets you choose a card AND you have no engine/support Pokémon in play, "
                  "take one — a Pokémon whose Ability draws, accelerates Energy or searches (Function "
                  "Tags `energy_accel`/`draw`/`search`/`dig`). An online engine multiplies every later "
                  "turn, so when you lack one it is a high-value grab, second only to the win-condition "
                  "and energy-when-starved. Gap-gated off `Board.support_in_play` — stands down once an "
                  "engine is online (no dead second engine). Derived structurally (a Pokémon carrying an "
                  "engine tag), so any deck inherits it; a deck refines which engine via its Roles.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_support
        and not c.board.support_in_play,
        weight=15, status="testing"),
    Hypothesis(
        id="fetch-when-it-fills-a-need",
        rationale="Whether-to-PLAY a fetch (ADR-0023, decision A): play it when its reachable deck set "
                  "still holds a card you currently LACK — `Context.fetch_fills_a_need`, the lookahead "
                  "that scores the best grab with the SAME grab rungs (shared oracle) before the search "
                  "reveals the deck. The positive endorsement a discard-COST fetch otherwise misses: "
                  "`dig-before-commit` stands down for `cost_discard` (Ultra Ball), so without this an "
                  "Ultra Ball that can fetch your unfound win-condition had no driver to be played. "
                  "Modest, so it sequences as a commitment (`_finish_turn_last`) after the free digs; "
                  "silent on a whiff / when nothing is lacking (best grab value 0). Weighted BELOW a "
                  "free, needed development — a discard-cost dig should not outrank powering your "
                  "attacker (`power-up-attacker` nets +10), the ep82228640-fr7 shape — which also stands "
                  "in for the deferred cost-netting (the 2-card cost makes the net value lower than the "
                  "raw grab). The full cost-netting (subtract the shed cards) and Plan-scaled bar remain.",
        when=lambda c: c.option_type == _PLAY and c.fetch_fills_a_need,
        weight=8, status="testing"),
    Hypothesis(
        id="fetch-deck-priority",
        rationale="Tier-3 escape hatch (ADR-0023): when the deck declares an explicit ordered "
                  "`Strategy.fetch_priority`, grab the highest-priority card on that list that the "
                  "search actually reveals — the combo deck's override of the derived importance rungs "
                  "(it knows a specific piece matters more than the generic win-condition/starter/support "
                  "ladder). Fires on the single best-ranked present candidate (`card_is_top_fetch_priority`, "
                  "resolved cross-option in `Board.top_fetch_priority_id`), weighted above the derived "
                  "grab rungs so the deck's stated order wins. Empty list (most decks) -> silent.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_top_fetch_priority,
        weight=40, status="testing"),
    # ── discard side (decision C): keep-value = `fetch_value` inverted, so you never pitch a card
    #    you'd immediately fetch back. Pitch the redundant / deck-wanted; floor the key cards. ──
    Hypothesis(
        id="prefer-good-in-discard",
        rationale="The deck-override of the discard side (ADR-0023): a recursion / discard-fed deck "
                  "marks cards it WANTS in the discard with the Role `discard_fodder` (e.g. a Pokémon "
                  "a Night-Stretcher/Sacred-Ash line recurs, or Energy a discard-pull accelerator "
                  "reclaims). At a forced discard, prefer pitching such a card — for that deck the bin "
                  "is an asset, so its keep-value in hand is low. Reads the deck Role directly; silent "
                  "for any deck that declares no `discard_fodder`. Outranks the generic "
                  "`discard-the-redundant` (the deck's stated synergy beats a plain duplicate).",
        when=lambda c: c.select_context == _DISCARD and "discard_fodder" in c.roles,
        weight=25, status="testing"),
    Hypothesis(
        id="discard-the-redundant",
        rationale="At a forced discard (e.g. Ultra Ball's cost), shed the card whose need is already "
                  "met first — the lowest keep-value. v1's redundancy signal is a hand copy of a "
                  "Pokémon already in play (`Context.card_is_redundant`): a duplicate body you don't "
                  "need a second of right now. A positive weight ranks it ABOVE a still-needed card as "
                  "the pitch, the mirror of the grab comparator (shed what you'd not fetch back). Pairs "
                  "with `keep-key-cards-at-discard`, which floors the engine pieces / win-condition so "
                  "they are never the pitch — together: pitch the redundant, protect the key.",
        when=lambda c: c.select_context == _DISCARD and c.card_is_redundant,
        weight=20, status="testing"),
    Hypothesis(
        id="keep-key-cards-at-discard",
        rationale="At a cost-discard (e.g. Ultra Ball's 'discard 2 cards from your hand'), don't throw "
                  "away your engine pieces — a discard-at-end-of-turn burst Energy (Function Tag "
                  "`discard_eot`, e.g. Ignition Energy: finite, non-recyclable, the one-attach CCC that "
                  "powers Nebula Beam) or your win-condition. A negative weight ranks those LAST among "
                  "the discard candidates, so the agent sheds a redundant Supporter instead. (Which "
                  "card a search FETCHES is `fetch-the-wincon`; this guards what a cost DISCARDS.)",
        when=lambda c: c.select_context == _DISCARD
        and ("discard_eot" in c.tags or c.card_is_wincon),
        weight=-30, status="testing"),
]
