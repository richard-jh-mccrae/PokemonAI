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

from common.strategy.context import (_BENCH_MAX, _CARD, _DISCARD, _ENGINE_TAGS, _OPENER_TAG, _PLAY,
                                      _SETUP_BENCH, _SUPPORTER, _THIN_BENCH, _TO_ACTIVE, _TO_BENCH,
                                      _TO_HAND, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis, Plan

# Reliable-engine Supporter (draw/search/heal) = fuel, keep it at a forced discard, unlike a
# situational `hand_disruption` one (Harlequin: symmetric shuffle refills opponent too).
_KEEP_ENGINE_TAGS = frozenset({"draw", "search", "dig", "heal", "clutch_heal"})

# FETCH FILTER: cards a search can pull OUT of deck, predicate over CardStat, keyed by Function Tag.
# Shared basis for whiff/redundancy signals (all targets gone/held = dead card). Add filter tag+predicate per new search card.
_FETCH_FILTERS = {
    "bench_fill": lambda st: st.hp > 0 and not st.evolvesFrom,    # Basic Pokémon (Buddy-Buddy Poffin)
    "tutor_mega": lambda st: bool(getattr(st, "megaEx", False)),  # a Mega Evolution ex (Mega Signal)
    "tutor_pokemon": lambda st: st.hp > 0,                        # any Pokémon (Ultra Ball)
    # Rush-evolve tutor (Salvatore): only ability-LESS Evolutions (e.g. Mega Starmie ex, not Cinderace).
    # Board-blind by design -> over-includes, never false-suppresses. Cf `dont-rush-evolve-without-target` (in-play case); this = not-in-DECK case, ep83117367.
    "rush_evolve": lambda st: bool(st.evolvesFrom) and not getattr(st, "hasAbility", False),
}

# PROBABLE-WHIFF threshold (ADR-0029): `dont-search-a-probable-whiff` fires when best reachable target's
# hypergeometric P(still in deck) < this. Conservative (refuted ep82524455-f6: P~=0.98 stays above bar). SOUND whiff (P=0) is separate/unconditional.
_WHIFF_PROB_THRESHOLD = 0.20


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
        wincon-tutor (it can fetch ONLY the win-condition, which you can't usefully deploy a second
        of). Both False off a PLAY / a card with no known fetch-filter (cf. `_FETCH_FILTERS`).

        The wincon-tutor is redundant when a copy is already in HAND (a second is a dead dig) OR the
        win-condition is already IN PLAY with no base to evolve another onto (`not
        wincon_base_deployable` — no Line pre-evolution in play or hand): fetching a second Mega you
        cannot deploy burns the turn while a real need (a Bench body) goes unmet (ep83038055 f40)."""
        if option.get("type") != _PLAY:
            return False, False
        fetch_set = self._search_deck_set(tags)
        if not fetch_set:
            return False, False
        exhausted = all(cid in board.deck_empty_ids for cid in fetch_set)
        wincon = self._wincon_set()
        wincon_undeployable_in_play = board.wincon_in_play and not board.wincon_base_deployable
        redundant = (bool(wincon) and fetch_set <= wincon
                     and (board.wincon_in_hand or wincon_undeployable_in_play))
        return exhausted, redundant

    def _search_probable_whiff(self, option: dict, tags: list, board) -> bool:
        """The PROBABILISTIC complement to `_search_signals`' SOUND `search_targets_exhausted`
        (ADR-0029): a search whose every still-REACHABLE fetch target is UNLIKELY to remain in the deck
        — the best reachable target's `Board.deck_contains_probability` is below `_WHIFF_PROB_THRESHOLD`,
        though not provably gone. Mutually exclusive with the sound whiff: it requires a target NOT in
        `deck_empty_ids` (an empty reachable set is the sound guard's certain whiff, left to it). False
        off a PLAY / a non-search / when any target is plausibly present (so a copy that could sit in the
        hidden prizes is never suppressed). Drives the soft `dont-search-a-probable-whiff`."""
        if option.get("type") != _PLAY:
            return False
        fetch_set = self._search_deck_set(tags)
        if not fetch_set:
            return False
        reachable = fetch_set - board.deck_empty_ids
        if not reachable:
            return False                          # all provably gone -> SOUND guard owns this whiff
        best = max(board.deck_contains_probability(cid) for cid in reachable)
        return best < _WHIFF_PROB_THRESHOLD

    def _search_confirmed_hit(self, option: dict, tags: list, board, plan) -> bool:
        """The POSITIVE deck-knowledge signal for a search/tutor PLAY (ADR-0029): True iff a card the
        search's fetch-filter can pull is PROVABLY still in the deck (`Board.deck_definitely_has` —
        the tracker's exact post-anchor counts) AND fills a real need (positive grab value, the SAME
        rungs the real grab scores — the ADR-0023 shared-oracle invariant). Sound-or-silent, mirroring
        the oracle it reads: False off a PLAY, before the tracker anchors the prizes, or for a card
        with no known fetch-filter — a positive endorsement is never asserted on a guess."""
        if option.get("type") != _PLAY or not board.deck_known_counts:
            return False
        fetch_set = self._search_deck_set(tags)
        return any(board.deck_definitely_has(cid) and self._grab_value_of(board, cid, plan) > 0
                   for cid in fetch_set)

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
            card_stranded_evolution=cid in self._stranded_evolution_set(),
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
        rationale="At a hand-search, pull the win-condition / primary attacker first (universal "
                  "`win_condition`/`primary_attacker` Role) — highest-value fetch, develop it on your own terms. "
                  "Stands down once the payoff is in play, or when energy-starved (`fetch-energy-when-starved` "
                  "wins there — an unpowered Pokémon does nothing).",
        when=lambda c: c.select_context == _TO_HAND and bool(_WINCON_ROLES & set(c.roles))
        and not c.board.wincon_in_play
        and not (c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand),
        weight=30, status="testing"),
    Hypothesis(
        id="prefer-payoff-over-preevo",
        rationale="When both the win-condition payoff and a pre-evolution are on offer at a search, take the "
                  "PAYOFF: `fetch-the-wincon` (+30) otherwise only TIES `prefer-wincon-line-piece` (+18) + "
                  "`fetch-a-starter` (+12) on the pre-evolution, and the tie breaks to the wrong option. Gated "
                  "like `fetch-the-wincon` (stands down once in hand/in play), so it never pulls a dead second copy.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_wincon
        and not c.board.wincon_in_play and not c.board.wincon_in_hand,
        weight=5, status="testing"),
    Hypothesis(
        id="fetch-base-before-stranded-payoff",
        rationale="When the payoff isn't yet deployable (`wincon_base_deployable` False — no Line pre-evolution "
                  "in play or hand), prefer fetching the base: a payoff with nothing to evolve from strands a "
                  "dead card (and starves a recipient like Cinderace's Turbo Flare), while the base unblocks the "
                  "whole line. Inverse of `prefer-payoff-over-preevo`; lifts the pre-evolution above "
                  "`fetch-the-wincon` (+30) but stays additive, so a payoff-only offer is still grabbed.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_line_preevo
        and not c.board.wincon_base_deployable,
        weight=20, status="testing"),
    Hypothesis(
        id="fetch-energy-when-starved",
        rationale="With the Active unpowered and no Energy in hand, take a reusable Basic Energy at a search — "
                  "you need to power an attack now, and neither a Pokémon nor a discard-at-EOT Energy (Ignition) "
                  "does that. Also prefers a reusable Basic over a discard Energy at the same search.",
        when=lambda c: c.select_context == _TO_HAND and c.board.my_active_energy == 0
        and not c.board.reusable_energy_in_hand and _is_reusable_energy(c.stat, c.tags),
        weight=25, status="testing"),
    Hypothesis(
        id="prefer-bench-fill-first",
        rationale="A `bench_fill` card (Buddy-Buddy Poffin) is best played FIRST in a thin deck: develops the "
                  "Bench, thins the deck (raises later draw/search quality), and feeds spread-Energy attacks. "
                  "Fires in SETUP and RACE (refill a KO-thinned Bench before the turn-ending attack); stands "
                  "down once the Bench is full.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
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
        id="prefer-wincon-line-piece",
        rationale="At a hand-search, prefer a pre-evolution on the win-condition LINE over an off-line "
                  "opener/accelerator. At a PROMOTE, only when the payoff is in hand to evolve it THIS turn — "
                  "otherwise a bare pre-evolution just exposes a fragile base (see `promote-the-staller`); "
                  "ranks below `fetch-the-wincon` and `fetch-energy-when-starved`.",
        when=lambda c: c.card_is_line_preevo and (
            c.select_context == _TO_HAND
            or (c.select_context == _TO_ACTIVE and c.board.evolve_to_ready_wincon_available)),
        weight=18, status="testing"),
    Hypothesis(
        id="fetch-a-starter",
        rationale="With an underdeveloped board (< 2 benched in SETUP), take a startable Basic at a search — "
                  "the fallback grab rung beneath `fetch-the-wincon`/`prefer-wincon-line-piece`: no Line piece "
                  "on offer still wants board presence over an off-need card. Gap-gated (stands down once the "
                  "Bench is developed); 'starter' is structural (Basic: hp > 0, no `evolvesFrom`).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_starter
        and c.plan == Plan.SETUP and c.board.my_bench < _THIN_BENCH,
        weight=12, status="testing"),
    Hypothesis(
        id="bench-fill-a-basic",
        rationale="At a bench-PLACEMENT grab (`_TO_BENCH`/`_SETUP_BENCH`), take a startable Basic — the "
                  "bench-context mirror of `fetch-a-starter`. Needed because a CARD-target candidate is invisible "
                  "to the `option_type==_PLAY` bench reflexes, so every candidate would score 0 and greedy "
                  "take-fewer benches NOTHING (the Buddy-Poffin whiff that cost ~3:1 in the mirror); skips a "
                  "multi-prizer (ex/Mega ex) and stands down once the Bench is full.",
        when=lambda c: c.select_context in (_TO_BENCH, _SETUP_BENCH) and c.card_is_starter
        and c.board.my_bench < _BENCH_MAX
        and not (c.stat and (getattr(c.stat, "ex", False) or getattr(c.stat, "megaEx", False))),
        weight=12, status="testing"),
    Hypothesis(
        id="dont-fetch-the-setup-only-opener",
        rationale="Never take a SETUP-ONLY opener into hand at a search: an `opener`-tagged Pokémon whose "
                  "evolution chain is absent from the deck (`card_stranded_evolution`) can never be played from "
                  "hand, so the fetched copy is dead — pull a live piece instead. Structural (stays fetchable if "
                  "the line IS in-deck), gated to TO_HAND only; folded from mega_starmie `never-fetch-cinderace`.",
        when=lambda c: c.select_context == _TO_HAND and _OPENER_TAG in c.tags
        and c.card_stranded_evolution,
        weight=-60, status="assumed"),
    Hypothesis(
        id="fetch-the-support",
        rationale="With no engine/support Pokémon in play (Ability tagged `energy_accel`/`draw`/`search`/`dig`), "
                  "take one at a search — an online engine multiplies every later turn, second only to the "
                  "win-condition and energy-when-starved. Gap-gated off `Board.support_in_play`; never endorses "
                  "a stranded evolution (`card_stranded_evolution`, cf `dont-fetch-the-setup-only-opener`).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_support
        and not c.card_stranded_evolution and not c.board.support_in_play,
        weight=15, status="testing"),
    Hypothesis(
        id="fetch-when-it-fills-a-need",
        rationale="Whether-to-PLAY a fetch (ADR-0023, decision A): play when the reachable deck set still holds "
                  "a card you LACK (`Context.fetch_fills_a_need`, same-rung lookahead). Fills the gap "
                  "`dig-before-commit` leaves for `cost_discard` fetches (Ultra Ball); modest weight sequences it "
                  "after free digs and BELOW `power-up-attacker` (+10, the ep82228640-fr7 shape) as a stand-in "
                  "for deferred cost-netting.",
        when=lambda c: c.option_type == _PLAY and c.fetch_fills_a_need,
        weight=8, status="testing"),
    Hypothesis(
        id="play-a-tutor-for-the-unfound-wincon",
        rationale="During SETUP, play a `tutor`-Roled card to dig for the win-condition (Role-keyed; which "
                  "card the search pulls is `fetch-the-wincon`/`fetch-energy-when-starved`). Stands down once "
                  "the wincon is in hand, or its fetch-set is provably exhausted (ep83117367: a wincon-only "
                  "tutor with every copy gone burns the turn on a whiff); folded from mega_starmie `tutor-the-wincon`.",
        when=lambda c: c.plan == Plan.SETUP and c.option_type == _PLAY and "tutor" in c.roles
        and not c.board.wincon_in_hand and not c.search_targets_exhausted,
        weight=25, status="assumed"),
    Hypothesis(
        id="hold-costly-fetch-when-line-assembled",
        rationale="Cost-net a DISCARD-cost fetch (Ultra Ball pays 2 cards): once the win-condition line is "
                  "ALREADY assembled (`wincon_in_hand` and `wincon_base_deployable`), the only pull left is a "
                  "redundant duplicate, not worth two cards. Cancels `fetch-when-it-fills-a-need`'s cost-blind "
                  "+8 (ep83007714 f8: plays Ultra Ball over End with the line in hand) — fires only on "
                  "`cost_discard` fetches once the line is assembled, never blocking a still-needed dig.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_fills_a_need
        and c.board.wincon_in_hand and c.board.wincon_base_deployable,
        weight=-12, status="testing"),
    Hypothesis(
        id="fetch-deck-priority",
        rationale="Tier-3 escape hatch (ADR-0023): when the deck declares `Strategy.fetch_priority`, grab the "
                  "highest-priority present card (`card_is_top_fetch_priority`, resolved in "
                  "`Board.top_fetch_priority_id`) — the combo deck's override of the derived importance ladder. "
                  "Weighted above the derived grab rungs so the deck's stated order wins; silent on the empty "
                  "list (most decks).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_top_fetch_priority,
        weight=40, status="testing"),
    # ── discard side (decision C): keep-value = `fetch_value` inverted, so you never pitch a card
    #    you'd immediately fetch back. Pitch the redundant / deck-wanted; floor the key cards. ──
    Hypothesis(
        id="prefer-good-in-discard",
        rationale="Deck-override of the discard side (ADR-0023): a recursion/discard-fed deck marks cards it "
                  "WANTS in the bin via Role `discard_fodder` — prefer pitching those (bin is an asset, keep-value "
                  "low). Reads the Role directly, silent with no `discard_fodder`; outranks the generic "
                  "`discard-the-redundant`.",
        when=lambda c: c.select_context == _DISCARD and "discard_fodder" in c.roles,
        weight=25, status="testing"),
    Hypothesis(
        id="discard-the-redundant",
        rationale="At a forced discard, shed the lowest keep-value card first — v1's redundancy signal is a "
                  "hand copy of a Pokémon already in play (`Context.card_is_redundant`). Positive weight ranks "
                  "it above a still-needed card (mirrors the grab comparator: shed what you'd not fetch back); "
                  "pairs with `keep-key-cards-at-discard` to protect the key while pitching the redundant.",
        when=lambda c: c.select_context == _DISCARD and c.card_is_redundant,
        weight=20, status="testing"),
    Hypothesis(
        id="discard-the-hand-duplicate",
        rationale="At a forced discard, shed a card held in MULTIPLE hand copies before a singleton — the "
                  "extra is redundant this turn (`Context.card_is_hand_duplicate`, 2+ in hand, fungible Energy "
                  "excluded). Hand-internal mirror of `discard-the-redundant`; protects lone disruptors (a "
                  "single Boss's Orders scoring 0 would otherwise lose the index tie-break) over a duplicate "
                  "engine Supporter, and pairs with `keep-key-cards-at-discard` so a 3rd wincon still nets negative.",
        when=lambda c: c.select_context == _DISCARD and c.card_is_hand_duplicate,
        weight=12, status="testing"),
    Hypothesis(
        id="keep-key-cards-at-discard",
        rationale="At a cost-discard, don't throw away irreplaceable pieces — a `discard_eot` burst Energy "
                  "(Ignition), the win-condition, or an ACE SPEC (`CardStat.aceSpec`, never recoverable). "
                  "Negative weight ranks those last, so the agent sheds a redundant Supporter instead (this "
                  "guards what a cost DISCARDS; `fetch-the-wincon` handles what a search FETCHES).",
        when=lambda c: c.select_context == _DISCARD
        and ("discard_eot" in c.tags or c.card_is_wincon
             or bool(c.stat and getattr(c.stat, "aceSpec", False))),
        weight=-30, status="testing"),
    Hypothesis(
        id="discard-the-redundant-tutor",
        rationale="At a forced discard, shed a `rush_evolve`/`tutor_mega` search whose job is done once the "
                  "win-condition is already in hand (`board.wincon_in_hand`) — a second dig for it is dead "
                  "weight. Positive weight ranks it among the discards; silent for a flexible Supporter "
                  "(e.g. Hilda, plain `search`, also finds Energy).",
        when=lambda c: c.select_context == _DISCARD and c.board.wincon_in_hand
        and ("rush_evolve" in c.tags or "tutor_mega" in c.tags),
        weight=20, status="testing"),
    Hypothesis(
        id="discard-the-dead-opener",
        rationale="At a forced discard, shed a setup-only `opener`-tagged card you can no longer play (once "
                  "the game is under way a held copy is dead) — mirrors `dont-fetch-the-setup-only-opener`, "
                  "which never takes one. Positive weight ranks it among the discards.",
        when=lambda c: c.select_context == _DISCARD and "opener" in c.tags,
        weight=20, status="testing"),
    Hypothesis(
        id="keep-engine-supporter-at-discard",
        rationale="At a forced discard, keep reliable engine Supporters (draw/search/heal) below a neutral "
                  "card or a situational `hand_disruption` Supporter (Harlequin) as the pitch — they're the fuel "
                  "that keeps the deck running. Small negative, so junk rules (dead opener/redundant tutor) still "
                  "out-pitch it; only protects the engine over filler.",
        when=lambda c: c.select_context == _DISCARD and c.stat is not None
        and getattr(c.stat, "cardType", None) == _SUPPORTER
        and bool(_KEEP_ENGINE_TAGS & set(c.tags)) and "hand_disruption" not in c.tags,
        weight=-8, status="testing"),
]
