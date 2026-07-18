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

from common.strategy.context import (_ATTACH_TO, _BENCH_MAX, _CARD, _DISCARD, _ENGINE_TAGS, _OPENER_TAG,
                                      _PLAY, _SETUP_BENCH, _SUPPORTER, _THIN_BENCH, _TO_ACTIVE, _TO_BENCH,
                                      _TO_HAND, _WINCON_ROLES)
from common.strategy.strategy import Hypothesis

# Reliable-engine Supporter (draw/search/heal) = fuel, keep it at a forced discard, unlike a
# situational `hand_disruption` one (Harlequin: symmetric shuffle refills opponent too).
_KEEP_ENGINE_TAGS = frozenset({"draw", "search", "dig", "heal", "clutch_heal"})

# Win-condition LINE bases (a deck's Line pre-evolutions: Riolu, Dreepy, Makuhita) — the pieces an
# evolution deck must keep to field its attackers. Deck-declared Roles, so the discard side can floor
# them above a spent draw Supporter and exempt them from the redundant/duplicate pitch endorsement (a
# 2nd Dreepy is a 2nd LINE, not junk). ep83661652 f30 / ep83686860 f18.
_BASE_ROLES = frozenset({"win_condition_base", "evolution_base"})

# FETCH FILTER: cards a search can pull OUT of deck, predicate over CardStat, keyed by Function Tag.
# Shared basis for whiff/redundancy signals (all targets gone/held = dead card). Add filter tag+predicate per new search card.
_FETCH_FILTERS = {
    # Buddy-Buddy Poffin (the only `bench_fill` card in the pool): "up to 2 Basic Pokémon with 70 HP
    # or less". The HP cap is the card's own text — without it the filter counted a 170-HP Meowth ex
    # as fetchable and the whiff guard never fired on an exhausted deck (dragapult f79, CRITICAL).
    "bench_fill": lambda st: st.hp > 0 and not st.evolvesFrom and st.hp <= 70,
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

    def _search_signals(self, option: dict, tags: list, board) -> tuple[bool, bool, bool]:
        """The three deck-knowledge signals for a search/tutor PLAY (see Context): whether it WHIFFS
        (every card it can fetch is provably gone from the deck), whether it is a REDUNDANT
        wincon-tutor (it can fetch ONLY the win-condition, which you can't usefully deploy a second
        of), and whether it is a BASELESS wincon-tutor (it can fetch only the win-condition and there
        is NO base to deploy it onto and it isn't in hand/play — the fetched payoff sits dead). All
        three False off a PLAY / a card with no known fetch-filter (cf. `_FETCH_FILTERS`).

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
        fetch_set = self._search_deck_set(tags)
        if not fetch_set:
            return False, False, False
        exhausted = all(cid in board.deck_empty_ids for cid in fetch_set)
        wincon = self._wincon_set()
        wincon_only = bool(wincon) and fetch_set <= wincon
        wincon_undeployable_in_play = board.wincon_in_play and not board.wincon_base_deployable
        redundant = (wincon_only
                     and (board.wincon_in_hand or wincon_undeployable_in_play))
        baseless = (wincon_only and not board.wincon_in_hand
                    and not board.wincon_in_play and not board.wincon_base_deployable)
        return exhausted, redundant, baseless

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
            card_is_redundant=cid is not None and cid in board.in_play_ids,   # f14 breadth stand-down
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

    def _pitch_value_of(self, board, cid: int, plan) -> tuple[float, bool]:
        """(pitch score, keep-key fired) of hand card `cid` at a virtual `_DISCARD` Context — the
        discard side's FULL signed sum (unlike `_grab_value_of`, negatives count: a keep-floor makes a
        card expensive to shed). The shed predictor behind cost-netting (ADR-0023 amendment): scoring
        with the SAME rungs the real discard select uses keeps prediction and pick agreeing."""
        from common.pilot import Context, _fires   # lazy: Context/Board live in pilot (cycle-free import)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        ctx = Context(
            plan=plan, select_context=_DISCARD, option_type=_CARD, card_id=cid,
            card_is_wincon=cid in self._wincon_set(),
            card_is_redundant=cid is not None and cid in board.in_play_ids,
            card_is_hand_duplicate=cid is not None and cid in board.hand_duplicate_ids,
            roles=self.strategy.roles.get(cid, []), tags=tags, stat=stat, board=board)
        score, key = 0.0, False
        for h in (*self.general.hypotheses, *self.strategy.hypotheses):
            if _fires(h, ctx):
                score += self._weight(h)
                key = key or h.id == "keep-key-cards-at-discard"
        return score, key

    def _shed_signals(self, obs: dict, option: dict, tags: list, board, plan) -> tuple[bool, bool, bool]:
        """(sheds_junk, sheds_live, sheds_key) for a `cost_discard` fetch PLAY: pitch-score the hand
        minus the fetch card, take the top-2 (what the later `_DISCARD` select will shed — same rungs,
        argmax alignment). junk = both > 0; live = any < 0; key = `keep-key-cards-at-discard` fires on
        a forced shed. All False off a PLAY / a free fetch / with < 2 other cards (engine legality)."""
        if option.get("type") != _PLAY or "cost_discard" not in tags:
            return False, False, False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        fetch_cid = self._option_card_id(obs, None, option)
        cands, excluded = [], False
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is None:
                continue
            if not excluded and cid == fetch_cid:
                excluded = True                              # the played copy itself is not sheddable
                continue
            cands.append(cid)
        if len(cands) < 2:
            return False, False, False
        top2 = sorted((self._pitch_value_of(board, cid, plan) for cid in cands),
                      key=lambda t: t[0], reverse=True)[:2]
        return (all(s > 0 for s, _ in top2),
                any(s < 0 for s, _ in top2),
                any(k for _, k in top2))

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
        rationale="When the payoff isn't yet deployable (`wincon_base_deployable` False — the payoff's IMMEDIATE "
                  "pre-evolution is neither in play nor in hand), prefer fetching the base: a payoff with nothing "
                  "to evolve from strands a dead card (and starves a recipient like Cinderace's Turbo Flare), "
                  "while the base unblocks the whole line. Inverse of `prefer-payoff-over-preevo`; lifts the "
                  "pre-evolution above `fetch-the-wincon` (+30) but stays additive, so a payoff-only offer is "
                  "still grabbed. Stands down once the win-condition is in play AND the Bench is already "
                  "developed (`wincon_in_play and my_bench > 0`) — nothing is stranded then and a SECOND line is "
                  "a luxury, so the +20 must not out-grab a genuinely needed engine piece (ml f39, CRITICAL: a "
                  "spare Riolu over the Solrock that turns Lunatone's draw-3 on, energized Mega already benched). "
                  "Two more BREADTH stand-downs (dragapult f14): a REDUNDANT base whose copy is already in play "
                  "adds no line progression on a thin Bench (`card_is_redundant and my_bench < _THIN_BENCH` — grab "
                  "a fresh body, not a 2nd of what's already down); and on an EMPTY Bench a mid-Line EVOLUTION "
                  "(`evolvesFrom`) can only stack on the Active, leaving the Bench empty (a KO-then-lose risk) — "
                  "develop a benchable Basic instead. (A Basic base on an empty Bench still fires — building the "
                  "first developed body is a real need, the ADR-0048 2nd-line case.)",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_line_preevo
        and not c.board.wincon_base_deployable
        and not (c.board.wincon_in_play and c.board.my_bench > 0)
        and not (c.card_is_redundant and c.board.my_bench < _THIN_BENCH)
        and not (c.board.my_bench == 0 and bool(c.stat and c.stat.evolvesFrom)),
        weight=20, status="testing"),
    Hypothesis(
        id="fetch-energy-when-starved",
        rationale="With the Active unpowered and no Energy in hand, take a reusable Basic Energy at a search — "
                  "you need to power an attack now, and neither a Pokémon nor a discard-at-EOT Energy (Ignition) "
                  "does that. Also prefers a reusable Basic over a discard Energy at the same search. Seeded "
                  "+35 (above `fetch-the-wincon` +30, which already stands DOWN when energy-starved) so energy "
                  "DOMINATES every Pokémon grab in the famine — not just the wincon but a redundant engine "
                  "piece (`fetch-the-engine-first` +20 + `fetch-a-starter` +12 = 32) or a line-piece "
                  "(`prefer-wincon-line-piece` +18 + starter = 30): an unpowered board does nothing, so a 2nd "
                  "Solrock/Lunatone never out-ranks the Energy that turns the game on (ep83966336 f9, "
                  "ep83967841 f14). The old +25 sat BELOW the grabs it was meant to beat — the doctrine's own "
                  "stated priority, now weighted to match.",
        when=lambda c: c.select_context == _TO_HAND and c.board.my_active_energy == 0
        and not c.board.reusable_energy_in_hand and _is_reusable_energy(c.stat, c.tags),
        weight=35, status="testing"),
    Hypothesis(
        id="fetch-the-attack-color",
        rationale="At an Energy search, break the `fetch-energy-when-starved` tie toward a color one of my "
                  "IN-PLAY attackers actually needs (`board.in_play_attack_colors`, via AttackStat energy "
                  "types) over an off-color utility Energy no body in play can use yet — grab the Fire for "
                  "Phantom Dive [Fire, Psychic], and save the off-color {D} for when Munkidori is benched "
                  "(dragapult f18). Tiny tie-break (+3) so a real need still dominates; silent for "
                  "mono-color decks (every fetch is on-color) and when no in-play body has a typed attack.",
        when=lambda c: c.select_context == _TO_HAND and bool(c.stat)
        and getattr(c.stat, "hp", 1) == 0 and getattr(c.stat, "energyType", None) not in (None, 0)
        and c.stat.energyType in c.board.in_play_attack_colors,
        weight=3, status="testing"),
    Hypothesis(
        id="fetch-the-ability-fuel-color",
        rationale="At an Energy search, prefer a colour that switches a DORMANT in-play Ability on over a "
                  "plain attack colour — grab the {D} a bare Munkidori needs for Adrena-Brain (its damage-move "
                  "engine, usable now) rather than the redundant {R}/{P} of a dragon line still two evolutions "
                  "from attacking (dragapult f22). Keyed on `board.in_play_unfueled_ability_colors` (the fuel a "
                  "body has an Ability for but LACKS attached), so it never fires for an already-fuelled Ability "
                  "or a body whose Ability wants no energy. +5 to out-rank `fetch-the-attack-color` (+3): an "
                  "Ability is repeatable free value that doesn't end the turn. Silent when Munkidori is in the "
                  "deck (empty set) — the must-not-regress f18 anchor picks the attack colour there.",
        when=lambda c: c.select_context == _TO_HAND and bool(c.stat)
        and getattr(c.stat, "hp", 1) == 0 and getattr(c.stat, "energyType", None) not in (None, 0)
        and c.stat.energyType in c.board.in_play_unfueled_ability_colors,
        weight=5, status="testing"),
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
        id="prefer-wincon-line-piece",
        rationale="At a hand-search, prefer a pre-evolution on a recognized ATTACKER Line over an off-line "
                  "opener/accelerator. ADR-0048: at the FETCH seam the credit is broadened to ANY declared "
                  "attacker Line (`card_is_recognized_line_preevo` — win-condition OR secondary-attacker), so "
                  "a cheap secondary base (Makuhita) earns the same +18 as the wincon base (Riolu), letting "
                  "`develop-the-cheap-prize-wall-line` tip the cheaper line on prize economy; it narrows back "
                  "to the win-condition line when the kill-switch is off. At a PROMOTE it stays "
                  "win-condition-only (`card_is_line_preevo`) and only when the payoff is in hand to evolve it "
                  "THIS turn — else a bare pre-evolution just exposes a fragile base (see `promote-the-staller`); "
                  "ranks below `fetch-the-wincon` and `fetch-energy-when-starved`. The TO_HAND credit carries "
                  "the same two BREADTH stand-downs as `fetch-base-before-stranded-payoff` (dragapult f14): a "
                  "redundant in-play base on a thin Bench, and an empty-Bench mid-Line evolution, both yield to "
                  "developing a fresh benchable body.",
        when=lambda c: (c.card_is_recognized_line_preevo and c.select_context == _TO_HAND
                        and not (c.card_is_redundant and c.board.my_bench < _THIN_BENCH)
                        and not (c.board.my_bench == 0 and bool(c.stat and c.stat.evolvesFrom)))
        or (c.card_is_line_preevo and c.select_context == _TO_ACTIVE
            and c.board.evolve_to_ready_wincon_available),
        weight=18, status="testing"),
    Hypothesis(
        id="develop-the-cheap-prize-wall-line",
        rationale="Once my MULTI-prize win-condition is in play (`wincon_in_play`; wincon_prize_value >= 2 "
                  "follows from the < comparison), a fetch that develops a CHEAPER attacker Line — a "
                  "recognized attacker pre-evo whose forward-payoff prize is LOWER than the win-condition's "
                  "(`card_forward_payoff_prize` < `wincon_prize_value`: Makuhita→Hariyama 1 < Mega 3) — forces "
                  "the opponent onto an eight-prizes-of-work path for a six-prize game (odd-prizing; the "
                  "FETCH-seam mirror of the Interpose promote trio, ADR-0048). A small POSITIVE tie-break (+3) "
                  "BELOW every real need (energy-starved +35 / fetch-wincon +30 / missing-piece +20 / engine "
                  "+15) — the wincon Line is still developed first while offline; `prefer-wincon-line-piece`'s "
                  "broadened credit equalizes the two line bases first, then this tips the cheaper one. Silent "
                  "without a declared secondary attacker Line, off the FETCH seam, or with the kill-switch off "
                  "(`card_is_recognized_line_preevo` narrows to the wincon base, which never satisfies the <).",
        when=lambda c: c.select_context == _TO_HAND and c.board.wincon_in_play
        and c.card_is_recognized_line_preevo
        and 0 < c.card_forward_payoff_prize < c.board.wincon_prize_value,
        weight=3, status="assumed"),
    Hypothesis(
        id="fetch-a-starter",
        rationale="With an underdeveloped board (< 2 benched in SETUP), take a startable Basic at a search — "
                  "the fallback grab rung beneath `fetch-the-wincon`/`prefer-wincon-line-piece`: no Line piece "
                  "on offer still wants board presence over an off-need card. Gap-gated (stands down once the "
                  "Bench is developed); 'starter' is structural (Basic: hp > 0, no `evolvesFrom`).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_starter
        and not c.board.line_ready and c.board.my_bench < _THIN_BENCH,
        weight=12, status="testing"),
    Hypothesis(
        id="develop-the-item-lock-opener",
        rationale="At a hand-search with a thin Bench, prefer developing the deck's item-lock OPENER (Function "
                  "Tag `item_lock`, e.g. Budew's Itchy Pollen — the opponent can't play Items next turn) over a "
                  "redundant base or an evolution that only stacks on the Active. It is the sacrificial "
                  "disruptor STARTER: it fills the empty Bench (survival), buys a tempo turn, and is the wall "
                  "you hide the fragile win-condition line behind while it develops. The FETCH-seam sibling of "
                  "`open-the-item-lock-starter` (the pregame Active pick); keyed on the `item_lock` tag so it is "
                  "silent for decks without such an opener. +30 clears the (breadth-stood-down) line-piece and "
                  "support grabs so the ideal starter wins the empty-Bench develop (dragapult f14: grab Budew, "
                  "not a 2nd Dreepy or a Drakloak that only stacks on the Active). Gated to a startable "
                  "`item_lock` Basic on a thin Bench; stands down once the Bench is developed.",
        when=lambda c: c.select_context == _TO_HAND and "item_lock" in c.tags
        and c.card_is_starter and c.board.my_bench < _THIN_BENCH,
        weight=30, status="assumed"),
    Hypothesis(
        id="bench-fill-a-basic",
        rationale="At a bench-PLACEMENT grab (`_TO_BENCH`/`_SETUP_BENCH`), take a startable Basic — the "
                  "bench-context mirror of `fetch-a-starter`. Needed because a CARD-target candidate is invisible "
                  "to the `option_type==_PLAY` bench reflexes, so every candidate would score 0 and greedy "
                  "take-fewer benches NOTHING (the Buddy-Poffin whiff that cost ~3:1 in the mirror); skips a "
                  "multi-prizer (ex/Mega ex) and stands down once the Bench is full.",
        when=lambda c: c.select_context in (_TO_BENCH, _SETUP_BENCH) and c.card_is_starter
        and c.board.my_bench < _BENCH_MAX
        and not (c.stat and getattr(c.stat, "is_ex_body", False)),
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
                  "a stranded evolution (`card_stranded_evolution`, cf `dont-fetch-the-setup-only-opener`). Also "
                  "excludes a win-condition-LINE evolution (`card_is_line_preevo`, e.g. Drakloak's Recon "
                  "Directive): you tutor a mid-Line piece to EVOLVE it, not to bench it as a standalone engine "
                  "— crediting it as support double-counts its line-piece value and over-ranks it above a fresh "
                  "body on an empty Bench (dragapult f14). STANDS DOWN at the energy famine (same predicate as "
                  "`fetch-the-wincon`, honouring its own charter 'second only to … energy-when-starved': once "
                  "Lunatone earned its `draw` tag (2026-07-17 audit) this stacked with a deck engine rung to 49 "
                  "and out-ranked the +35 famine Energy, re-opening ml0705 f9).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_support
        and not c.card_is_line_preevo
        and not c.card_stranded_evolution and not c.board.support_in_play
        and not (c.board.my_active_energy == 0 and not c.board.reusable_energy_in_hand),
        weight=15, status="testing"),
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
                  "predicted sheds BOTH pitch positive (`Context.fetch_sheds_junk` — top-2 keep-value "
                  "over hand minus the fetch, the same rungs the real discard select uses) pays with "
                  "dead cards, so it digs at the free band: +12 on `fetch-when-it-fills-a-need`'s +8 "
                  "matches `dig-before-commit` (+20). Gated on the need (a modifier of the "
                  "endorsement, not standalone); a `discard_fodder` deck's sheds score junk-positive, "
                  "so its costly digs ride here with no deck rule.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags
        and c.fetch_fills_a_need and c.fetch_sheds_junk,
        weight=12, status="testing"),
    Hypothesis(
        id="dont-shed-a-live-card",
        rationale="Cost-netting, the live band (ADR-0023 amendment): a `cost_discard` fetch forced to "
                  "shed a card with NEGATIVE keep-value (`Context.fetch_sheds_live` — a keep-floor "
                  "fires on a predicted top-2 shed, e.g. an engine Supporter) trades a live card for "
                  "the dig: net the play below End (+8 − 20). Deliberately liftable — a provable "
                  "needed hit (`search-the-confirmed-hit` +15) still clears it, so shedding live for "
                  "a certain grab survives. A veto, so NOT gated on `fetch_fills_a_need`; the "
                  "ep83007714-f8 'tossing the supporters' shape.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_sheds_live,
        weight=-20, status="testing"),
    Hypothesis(
        id="dont-shed-a-key-card",
        rationale="Cost-netting, the key band (ADR-0023 amendment): `keep-key-cards-at-discard` FIRES "
                  "on a predicted shed (`Context.fetch_sheds_key` — predicate-based, so tuning the key "
                  "floor can't drift this gate) — the discard would be forced to pitch the wincon / an "
                  "ACE SPEC / a burst Energy. Stacks on `dont-shed-a-live-card` to −45: net −37, "
                  "unliftable by any normal-band endorsement — never pitch an irreplaceable to dig.",
        when=lambda c: c.option_type == _PLAY and "cost_discard" in c.tags and c.fetch_sheds_key,
        weight=-25, status="testing"),
    Hypothesis(
        id="bench-the-supporter-tutor",
        rationale="Bench a `supporter_tutor` Pokémon (Meowth ex — Last-Ditch Catch: on the bench-drop "
                  "from hand, search your deck for a SUPPORTER to hand) during SETUP when you hold NO "
                  "Supporter, to guarantee one. Its tutor is a free ABILITY, so you bench it AND still "
                  "play a Supporter + attack the same turn — its edge over a Supporter-tutor Trainer "
                  "(Petrel), which costs the slot. SETUP is the safety proxy (opponents rarely have a "
                  "gust + a 170-KO online that early); the 2-prize bench liability is accepted for the "
                  "consistency/tempo. Stands down once a Supporter is in hand (no need — save the "
                  "2-prize exposure). NOTE: this REPLACES routing Meowth through a `tutor` Role, which "
                  "`play-a-tutor-for-the-unfound-wincon` (+25) mis-read as a WINCON dig — but Last-Ditch "
                  "fetches a Supporter, not the wincon, so it benched the 2-prize ex for the wrong "
                  "reason (mega_lucario STRATEGY.md §3, grill 2026-07-03). Splashable: Meowth ex runs "
                  "in many decks (mega_lucario, dragapult_ex), so the model is general (tag-keyed).",
        when=lambda c: not c.board.line_ready and c.option_type == _PLAY
        and "supporter_tutor" in c.tags and c.board.no_supporter_in_hand,
        weight=25, status="assumed"),
    Hypothesis(
        id="dont-pre-bench-the-supporter-tutor",
        rationale="At the PREGAME bench placement (`_SETUP_BENCH`, minCount 0), DON'T place a "
                  "`supporter_tutor` Pokémon (Meowth ex — Last-Ditch Catch) on the Bench: its tutor "
                  "Ability triggers on an IN-GAME bench-from-hand, NOT a pregame setup placement, so "
                  "benching it now wastes the free Supporter fetch — and when it is the only Basic it "
                  "should take the Active Spot, not sit benched. Negative so the Pilot DECLINES the "
                  "optional placement (decide()'s single-pick take-fewer; ep83661652 f3). The in-game "
                  "half is `bench-the-supporter-tutor` (+25, a Main-phase PLAY when holding no "
                  "Supporter) — the two never fire together (different select contexts).",
        when=lambda c: c.select_context == _SETUP_BENCH and "supporter_tutor" in c.tags,
        weight=-15, status="assumed"),
    Hypothesis(
        id="dont-pre-bench-a-redundant-utility",
        rationale="At the PREGAME bench placement (`_SETUP_BENCH`, minCount 0), DON'T bench a 2nd copy of a "
                  "standalone utility Basic already placed on my board (`card_id in board.setup_placed_ids`) — "
                  "a 2nd Munkidori while one is Active is a prize liability + a scarce bench slot, worth more "
                  "kept as Ultra-Ball discard fodder (dragapult f4). The `not card_is_line_preevo` guard keeps "
                  "benching a 2nd Dreepy (a win-condition LINE base you DO want multiples of). Setup-aware: the "
                  "just-placed Active shows only in the setup logs, so `card_is_redundant` (obs-zone `in_play_ids`) "
                  "reads False here — `setup_placed_ids` reads the placement from the logs. −15 mirrors the "
                  "supporter-tutor sibling: `bench-fill-a-basic` (+12) is the only positive, so 12−15 declines "
                  "the optional pick (`_greedy_grab` take-fewer). The _SETUP_BENCH generalization of mega_lucario's "
                  "`dont-bench-a-redundant-engine-piece` (−25, _PLAY).",
        when=lambda c: c.select_context == _SETUP_BENCH and c.card_id is not None
        and c.card_id in c.board.setup_placed_ids and not c.card_is_line_preevo,
        weight=-15, status="assumed"),
    Hypothesis(
        id="grab-a-gust-supporter-for-the-ko",
        rationale="At a TO_HAND Supporter grab (Meowth ex Last-Ditch Catch, or any supporter tutor), "
                  "take a `gust`-tagged Supporter (Boss's Orders) when a gust would KO/close NOW "
                  "(`gust_best_ko_prizes > 0`) — the top rung of the context-ranked grab. The free "
                  "Ability lets you grab it AND still play it + attack the same turn, so the closing "
                  "gust is the highest-value fetch. Above the draw-supporter default so the gust wins "
                  "when it pays.",
        when=lambda c: c.select_context == _TO_HAND and "gust" in c.tags
        and c.board.gust_best_ko_prizes > 0,
        weight=20, status="assumed"),
    Hypothesis(
        id="grab-a-draw-supporter-in-setup",
        rationale="The setup default of the context-ranked Supporter grab: with no closing gust "
                  "available, take a `draw` Supporter (Lillie's / Judge) to keep digging. Below the "
                  "gust rung (+20) so the closing gust still wins, and modest so `fetch-the-wincon` "
                  "(+30) and a genuinely needed non-draw grab still outrank it. Gated to a Supporter "
                  "CARD (`cardType`): a Pokémon carrying a `draw` ABILITY tag (Drakloak's Dig) is NOT a "
                  "draw Supporter to fetch — that mis-fire made a dead mid-line Drakloak out-grab a live "
                  "Basic (ep83686860 f33).",
        when=lambda c: not c.board.line_ready and c.select_context == _TO_HAND and "draw" in c.tags
        and bool(c.stat and getattr(c.stat, "is_supporter", False)),
        weight=10, status="assumed"),
    Hypothesis(
        id="dont-grab-a-card-already-in-hand",
        rationale="Don't tutor a card an identical copy of which is ALREADY in my hand — the second copy "
                  "does nothing the first doesn't, and the search is the scarce resource. The FETCH-side "
                  "mirror of the shipped `discard-the-hand-duplicate`, with the same fungible-Energy "
                  "exemption (a spare Basic Energy is always a future attach). `dont-fetch-the-redundant-"
                  "piece` covers redundancy IN PLAY; this covers redundancy IN HAND. ml f9 (CRITICAL): "
                  "already holding a Lillie's Determination, the agent spent Meowth ex's Last-Ditch Catch "
                  "on another one (`grab-a-draw-supporter-in-setup` +10, three copies tied on the option "
                  "index) instead of the Team Rocket's Petrel that opens the real chain (Petrel → Fighting "
                  "Gong → Solrock → Lunar Cycle draws 3). −12 cancels the draw-Supporter rung without "
                  "inverting the fetch order — a genuinely needed duplicate (`fetch-the-wincon` +30, "
                  "`fetch-energy-when-starved` +35) still wins.",
        when=lambda c: c.select_context == _TO_HAND and c.card_already_in_hand,
        weight=-12, status="assumed"),
    Hypothesis(
        id="grab-what-i-can-play-this-turn",
        rationale="At a search, a card that CANNOT be played this turn loses to one that can. Concretely: "
                  "once the one-per-turn Supporter is spent — often by the very tutor now resolving — a "
                  "fetched Supporter is next-turn fuel, while an Item plays immediately. ml f71: Team "
                  "Rocket's Petrel resolved with a DEAD hand (0 cards) and took a Lillie's Determination "
                  "(+10) that could not be played, over the Fighting Gong that fetches a Basic {F} to "
                  "discard to Lunar Cycle for 3 cards THIS turn. −12 cancels the draw-Supporter rung; a "
                  "Supporter worth more than any playable Item still wins on its own merits.",
        when=lambda c: c.select_context == _TO_HAND and c.card_unplayable_this_turn,
        weight=-12, status="assumed"),
    Hypothesis(
        id="dont-strand-the-evolving-engine",
        rationale="Don't tutor a Stage-1 ENGINE into hand when you hold no base to evolve it onto: a "
                  "`card_is_support` piece (hp>0 with an `energy_accel`/`draw`/`search`/`dig` Ability) "
                  "that is itself an Evolution with `card_evolution_baseless` (no copy of its "
                  "pre-evolution in play or hand) is unplayable this game — a dead grab that "
                  "`fetch-the-support` (+15) would otherwise prefer OVER the base that enables it "
                  "(Dudunsparce id 66 over base Dunsparce id 305, workflow wjzvrtwbk). The off-Line "
                  "complement of `dont-grab-a-baseless-mid-evolution` (which is `card_is_line_preevo`-"
                  "gated to the win-condition Line): gated to `not card_is_line_preevo` so the two never "
                  "double-fire. −25 nets the stranded engine below the base (Dunsparce's `fetch-a-starter` "
                  "+12). Board-SOUND (visible zones); silent once the base is in play/hand and for "
                  "line-only decks whose engines are Basics (Solrock/Lunatone → not baseless). Excludes "
                  "`card_stranded_evolution` (a setup-only engine like Cinderace whose whole chain is "
                  "out of deck) — that dead grab is `dont-fetch-the-setup-only-opener`'s (−60), so the "
                  "two never stack; this rung owns only the engine whose base IS reachable but not yet "
                  "in play/hand (Dudunsparce, base Dunsparce in deck → not stranded).",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_support
        and not c.card_is_line_preevo and c.card_evolution_baseless
        and not c.card_stranded_evolution,
        weight=-25, status="assumed"),
    Hypothesis(
        id="dont-fetch-an-unplayable-evolution-payoff",
        rationale="Don't tutor an EVOLUTION into hand when its pre-evolution base is provably UNREACHABLE "
                  "this game (`card_base_unreachable`: not in play/hand AND absent from the search's "
                  "revealed pool / provably empty from the deck) — it can't be played from hand and has "
                  "no base to evolve onto, so it is a dead card. A Mega ex only enters play by evolving "
                  "its Basic; grabbing Mega Lucario ex with every Riolu gone burns the fetch (ml f53: "
                  "CRITICAL — took the Mega over Solrock, all options scored 0 → index took the Mega). "
                  "The FETCH-side mirror of `hold-wincon-dont-shuffle`'s `wincon_in_hand_undeployable` "
                  "stand-down (that HOLDS an undeployable payoff; this declines tutoring one UP). Uses "
                  "the exact `search_deck_ids` within-frame reachability, so it holds under BOTH the "
                  "prize-exact tracker and a single-frame fetch reveal. −25 nets the dead grab below a "
                  "live one; unlike `dont-grab-a-baseless-mid-evolution` (`card_is_line_preevo`-gated, "
                  "play/hand only) it also catches the PAYOFF and requires the base to be gone from the "
                  "DECK too (a base still in-deck is drawable — not yet dead).",
        when=lambda c: c.select_context == _TO_HAND and c.card_base_unreachable,
        weight=-25, status="assumed"),
    Hypothesis(
        id="dont-grab-a-baseless-mid-evolution",
        rationale="Don't take a mid-Line EVOLUTION into hand at a search when you hold no base to evolve "
                  "it onto — no copy of its pre-evolution in play or hand (`card_evolution_baseless`), so "
                  "the grabbed card is dead weight (ep83686860 f33: a 3rd Drakloak with every Dreepy "
                  "already evolved or discarded — take the playable Munkidori instead). Board-SOUND "
                  "(visible zones only, no deck-content claim); gated to a `card_is_line_preevo` (a "
                  "mid-Line piece — never a Basic base or the payoff), so single-hop lines with Basic "
                  "bases (Riolu/Staryu) are untouched. −25 nets the baseless grab below "
                  "`prefer-wincon-line-piece` (+18) so a live Basic wins the pick.",
        when=lambda c: c.select_context == _TO_HAND and c.card_is_line_preevo
        and c.card_evolution_baseless,
        weight=-25, status="assumed"),
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
                  "pairs with `keep-key-cards-at-discard` to protect the key while pitching the redundant. "
                  "Exempts a win-condition LINE base (`_BASE_ROLES`): a 2nd Dreepy in play is a 2nd LINE to "
                  "field, not junk — pitching it drops you below your line count (ep83686860 f18).",
        when=lambda c: c.select_context == _DISCARD and c.card_is_redundant
        and not (_BASE_ROLES & set(c.roles)),
        weight=20, status="testing"),
    Hypothesis(
        id="discard-the-hand-duplicate",
        rationale="At a forced discard, shed a card held in MULTIPLE hand copies before a singleton — the "
                  "extra is redundant this turn (`Context.card_is_hand_duplicate`, 2+ in hand, fungible Energy "
                  "excluded). Hand-internal mirror of `discard-the-redundant`; protects lone disruptors (a "
                  "single Boss's Orders scoring 0 would otherwise lose the index tie-break) over a duplicate "
                  "engine Supporter, and pairs with `keep-key-cards-at-discard` so a 3rd wincon still nets negative. "
                  "Exempts a win-condition LINE base (`_BASE_ROLES`): two Dreepy in hand are two LINES you want, "
                  "not a redundant duplicate — `keep-line-base-at-discard` floors them instead (ep83686860 f18).",
        when=lambda c: c.select_context == _DISCARD and c.card_is_hand_duplicate
        and not (_BASE_ROLES & set(c.roles)),
        weight=12, status="testing"),
    Hypothesis(
        id="keep-key-cards-at-discard",
        rationale="At a cost-discard, don't throw away irreplaceable pieces — a `discard_eot` burst Energy "
                  "(Ignition), the win-condition, or an ACE SPEC (`CardStat.aceSpec`, never recoverable). "
                  "Negative weight ranks those last, so the agent sheds a redundant Supporter instead (this "
                  "guards what a cost DISCARDS; `fetch-the-wincon` handles what a search FETCHES). The "
                  "burst-Energy keep is PREMISE-GATED: once my Active already carries its biggest attack's "
                  "cost (`active_fully_powered`) the burst has no urgent job, and a hand-refresh engine "
                  "Supporter outkeeps it (ep83454549 f36: pitch Ignition, keep Lillie's Determination).",
        when=lambda c: c.select_context == _DISCARD
        and (("discard_eot" in c.tags and not c.board.active_fully_powered) or c.card_is_wincon
             or bool(c.stat and getattr(c.stat, "aceSpec", False))),
        weight=-30, status="testing"),
    Hypothesis(
        id="keep-line-base-at-discard",
        rationale="At a forced discard, keep a win-condition LINE base (`_BASE_ROLES`: Riolu / Dreepy / "
                  "Makuhita — a Line pre-evolution you must field to attack) over a spent draw Supporter. "
                  "`keep-key-cards-at-discard` (−30) protects only the PAYOFF / burst / ACE SPEC, so the "
                  "deep-evolution decks pitched their own bases (ep83661652 f30: discarded Riolu+Makuhita "
                  "over Lillie's; ep83686860 f18: discarded both Dreepy over Judge). −15 nets a base below "
                  "a `keep-engine-supporter-at-discard` Supporter (−8) so the Supporter is shed first; "
                  "combined with the `_BASE_ROLES` exemption on `discard-the-redundant`/`-hand-duplicate` "
                  "(else a 2nd line body scores +32 junk), it keeps the lines. Milder than the key floor: "
                  "a base is recoverable in principle, so a forced 2nd shed can still take one.",
        when=lambda c: c.select_context == _DISCARD and bool(_BASE_ROLES & set(c.roles)),
        weight=-15, status="assumed"),
    Hypothesis(
        id="keep-basic-energy-when-starved",
        rationale="At a forced discard, keep a reusable Basic Energy when the board is energy-STARVED "
                  "(my Active carries none) over a spent draw Supporter — with no Energy in play the "
                  "next attach is the whole turn's tempo, so shedding Energy 'when we otherwise have no "
                  "energy is a bad trade' (ep83686860 f11: discarded the Fire Energy the wincon needs). "
                  "−12 nets it below a `keep-engine-supporter-at-discard` Supporter (−8); gated on a "
                  "real Active carrying zero Energy (`my_active_id` set, `my_active_energy == 0`) so a "
                  "powered board — or an empty-Active setup state — still cycles a surplus Energy freely. "
                  "Basic Energy only (typed, non-`discard_eot`) — a burst is `keep-key-cards`' job.",
        when=lambda c: c.select_context == _DISCARD and c.board.my_active_id is not None
        and c.board.my_active_energy == 0
        and bool(c.stat and getattr(c.stat, "hp", 0) == 0
                 and getattr(c.stat, "energyType", None) not in (None, 0))
        and "discard_eot" not in c.tags,
        weight=-12, status="assumed"),
    Hypothesis(
        id="keep-the-evolution-tutor-at-discard",
        rationale="At a forced discard BEFORE the win-condition line is assembled (`not wincon_in_hand`), "
                  "floor a scarce evolution tutor (`rush_evolve`/`tutor_mega` — Salvatore, the deck's "
                  "only way to field a 2nd Mega Starmie) below a redundant DRAW duplicate: a held-in-2 "
                  "Salvatore and a held-in-2 Lillie's Determination both tie at `discard-the-hand-"
                  "duplicate` (+12) + `keep-engine-supporter-at-discard` (−8) = +4, so the index tie-"
                  "break shed the line-enabling tutor first (ep83967840 f54: kept both Salvatore, the "
                  "human wanted a plentiful Lillie's pitched instead). −6 nets the tutor below the tied "
                  "draw duplicate so the redundant draw Supporter is shed. Gated to `not wincon_in_hand` "
                  "so it never fights `discard-the-redundant-tutor` (+20), which correctly sheds a tutor "
                  "whose job is DONE once the wincon is already in hand.",
        when=lambda c: c.select_context == _DISCARD
        and ("rush_evolve" in c.tags or "tutor_mega" in c.tags)
        and not c.board.wincon_in_hand,
        weight=-6, status="assumed"),
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
        id="keep-gust-and-recovery-at-discard",
        rationale="At a forced discard, floor a `gust` (Boss's Orders / Counter Catcher — the deck's "
                  "reach to close a KO or gust around a wall) or `recycle` (Super Rod / Night Stretcher — "
                  "the deck's recovery) card below neutral filler: the existing keep-floors "
                  "(`keep-key-cards-at-discard` −30, `keep-engine-supporter-at-discard` −8) protect the "
                  "wincon / burst / ACE SPEC / draw-search-heal Supporters but NOT the Item-form gust and "
                  "recovery cards (`_KEEP_ENGINE_TAGS` omits `gust`/`recycle` and the −8 rung gates on "
                  "`cardType == SUPPORTER`), so a lone Boss's / Counter Catcher / Super Rod / Night "
                  "Stretcher scored 0 and could fall to the option-index tie-break — pitched over filler. "
                  "These are irreplaceable reach/recovery: the digest's 'Never-discard' bucket. −10 (just "
                  "under the −8 engine floor: a gust/recovery is at least as irreplaceable as a draw "
                  "Supporter) so filler is shed first; still below the −30 key floor and −15 line-base so "
                  "a genuinely forced multi-shed can still take one. seed-ladder (ADR-0018).",
        when=lambda c: c.select_context == _DISCARD
        and bool({"gust", "recycle"} & set(c.tags)),
        weight=-10, status="assumed"),
    Hypothesis(
        id="keep-engine-supporter-at-discard",
        rationale="At a forced discard, keep reliable engine Supporters (draw/search/heal) below a neutral "
                  "card or a situational `hand_disruption` Supporter (Harlequin) as the pitch — they're the fuel "
                  "that keeps the deck running. Small negative, so junk rules (dead opener/redundant tutor) still "
                  "out-pitch it; only protects the engine over filler.",
        when=lambda c: c.select_context == _DISCARD and c.stat is not None
        and getattr(c.stat, "is_supporter", False)
        and bool(_KEEP_ENGINE_TAGS & set(c.tags)) and "hand_disruption" not in c.tags,
        weight=-8, status="testing"),
]
