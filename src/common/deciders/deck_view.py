"""What is left in the deck: exact counts where the tracker knows (a search reveal, a prize-exact split), hypergeometric
odds where it does not (ADR-0029).

The emptiness oracle is SOUND — it claims a card is gone only when the count proves it, so a search that would whiff
can be declined rather than guessed at."""
from __future__ import annotations


from collections import Counter

from common import deck_odds
from common.board_cards import body_card_ids
from common.deciders.facts import Board



class DeckViewMixin:
    """Deck contents: what is known exactly, and what is only probable."""

    def _unseen_deck_counts(self, me: dict, board: Board) -> dict:
        """My deck as *"not provably gone"* counts: the match tracker's EXACT per-card remainder
        (`Board.deck_known_counts`) once it has anchored, else the decklist minus everything visible
        (`_visible_card_counts` — in play, hand, discard; face-down prizes stay counted, which is
        what keeps the read SOUND rather than merely observed).

        One spelling for what was three identical five-line walks — `_discard_equation_rows`,
        `_needs_hand_rows` and `_deploy_supplier_rows` each carried their own copy, and the
        playability gate (Issue #288) would have made it four. Every deck-availability question in
        the keep-value family therefore answers off the same counts by construction.

        The pre-anchor fallback is memoised on the identity of ``(me, board)`` so repeat callers get
        back the SAME dict, not an equal one. That is not micro-optimisation: `_playability_zones`
        caches on its inputs' identity, and a freshly built counts dict per caller would miss that
        cache every time — the two row builders and the gate would each rebuild the zone sets over
        the same board. Strong references, never ``id()`` (a collected object's address is reused)."""
        counts = board.deck_known_counts
        if counts:
            return counts
        cached = getattr(self, "_unseen_counts_cache", None)
        if cached is not None and cached[0] is me and cached[1] is board:
            return cached[2]
        from collections import Counter
        unseen = Counter(self.deck)
        unseen.subtract(self._visible_card_counts(me))
        counts = {cid: n for cid, n in unseen.items() if n > 0}
        self._unseen_counts_cache = (me, board, counts)
        return counts

    def _basic_energy_in_deck(self, deck_empty) -> bool:
        """True if my deck can still yield a Basic Energy — a Basic-Energy card id in my decklist is not
        known-exhausted (`deck_empty`, the sound emptiness oracle). The fuel gate for an accelerator promote:
        Cinderace's Turbo Flare fetches Basic Energy to the Bench, so with none left the acceleration whiffs.
        Fail-open (True) early when nothing is known-exhausted; False with no stats."""
        if not self.stats:
            return False
        empty = deck_empty or frozenset()
        for cid in set(self.deck or ()):
            stat = self.stats.get(cid)
            if stat and stat.is_basic_energy and cid not in empty:
                return True
        return False

    def _basic_energy_types_in_deck(self, deck_empty) -> frozenset:
        """The Basic-Energy TYPES my deck can still yield — the typed extension of
        ``_basic_energy_in_deck`` the Attach Budget's deck-fetch leg needs (issue #137).

        Same epistemic as its untyped sibling, per type: a type counts unless EVERY Basic Energy
        card id of that type is known-exhausted by the sound emptiness oracle (``deck_empty``) —
        *not-provably-empty*, never provably-present. ADR-0067 rules that split deliberately: with
        a thin 3-copy Energy suite nothing is provable before a search anchors the prizes, so a
        strict gate would zero every deck-fetch pre-anchor and re-fire the f70 false famine. The
        honest probability for a still-uncertain fetch lives in ``CombatMath.readiness_p``.
        Empty with no stats (fail-CLOSED — a stat-blind Pilot claims no fuel)."""
        if not self.stats:
            return frozenset()
        empty = deck_empty or frozenset()
        return frozenset(
            stat.energyType for cid in set(self.deck or ())
            if cid not in empty and (stat := self.stats.get(cid)) is not None
            and stat.is_typed_basic_energy)

    def _deck_basic_energy_fuel(self, etype) -> float:
        """Matching Basic Energy a whole-deck search rider (Turbo Flare) can EXPECT to still find in
        my deck — `CountTriple.expected` off the ONE `MySide.deck_energy_counts` derivation
        (ADR-0077 decision 3).

        A COUNT question, so it reads the count leg. `p_any` answers *is there at least one?* and
        weighting a full `recoverN` by it would claim "P(≥1) odds of finding ALL of them"; the
        provable `floor` this replaces answered a question nobody asked — it reads 0 for every
        realistic suite still behind hidden prizes (3 unseen Water behind 5 prizes on
        `82756664|1|decision|97`, a deck 99.75 % certain to hold Water), which zeroed
        `min(recoverN, fuel, need)` and killed the accel dividend outright (Issue #172).

        `etype` None is an UNTYPED rider (Turbo Flare, Whimsicott ex's Energy Gift — "search your
        deck for up to 3 Basic Energy cards"), which takes the cross-type union. That union is EXACT
        rather than a second instrument: every type's leg divides the same
        `(deck_count, prizes_hidden)`, so `Σₜ expectedₜ == expected(Σₜ unseenₜ)` — the identity that
        licenses on `expected` what ADR-0074 decision 6 forbids on `p_any`.

        No regime branch: anchored, the legs collapse to the exact integer on their own, so the old
        `deck_known_counts` short-circuit is subsumed rather than replaced. 0.0 with no StateModel."""
        model = self._state_model
        if model is None:
            return 0.0
        counts = model.mine.deck_energy_counts
        if etype is None:
            return float(sum(c.expected for c in counts.values()))
        triple = counts.get(etype)
        return float(triple.expected) if triple else 0.0

    def _deck_body_names(self) -> frozenset:
        """Every card NAME in this deck's list. NAMES rather than ids because an evolution identifies
        its previous stage by name (`CardStat.evolvesFrom`) and reprints share a name across ids —
        Raboot is both 152 and 665 — so an id-keyed test would miss the reprint.

        Deck-fixed and match-invariant, so memoised like `_wincon_set` / `_derived_accel_body_ids`
        rather than rebuilt per call: `_route_only_at_setup` is consulted once per declared starter,
        and rebuilding a 60-card set inside that loop is the kind of quiet quadratic the neighbouring
        derived sets already avoid."""
        cached = getattr(self, "_deck_body_names_cache", None)
        if cached is not None:
            return cached
        names = frozenset(s.name for s in (self.stats.get(c) for c in set(self.deck or ()))
                          if s and s.name) if self.stats else frozenset()
        self._deck_body_names_cache = names
        return names

    def _visible_card_counts(self, me: dict) -> Counter:
        """Count MY card copies that are provably OUTSIDE the deck: my hand, my discard, every board
        Pokémon (its own id + attached Energy cards + Tools + the `preEvolution` cards stacked under
        it — e.g. the Staryu under a Mega Starmie ex) and any FACE-UP prize. Face-down prizes (None)
        and the hidden deck are left uncounted — exactly the unknowns that keep `_deck_empty_ids`
        sound."""
        counts: Counter = Counter()
        for c in (me.get("hand") or []):
            if c and c.get("id") is not None:
                counts[c["id"]] += 1
        for c in (me.get("discard") or []):
            if c and c.get("id") is not None:
                counts[c["id"]] += 1
        for p in (me.get("prize") or []):
            if p and p.get("id") is not None:          # a revealed prize (face-down prizes are None)
                counts[p["id"]] += 1
        for poke in (me.get("active") or []) + (me.get("bench") or []):
            self._count_in_play(poke, counts)
        return counts

    def _deck_known_counts(self, me: dict, prizes: dict | None) -> dict | None:
        """EXACT count of each card still in my deck (``decklist − visible − prizes``), once the
        deck-tracker has anchored the prizes; None when the prizes are not yet resolved (no positive
        deck claim without certainty). Only positive counts are kept."""
        if not self.deck or prizes is None:
            return None
        deck_counts = Counter(self.deck)
        seen = self._visible_card_counts(me)
        return {cid: rem for cid, n in deck_counts.items()
                if (rem := n - seen.get(cid, 0) - prizes.get(cid, 0)) > 0}

    def _deck_contains_prob(self, me: dict, deck_known: dict | None) -> dict | None:
        """PROBABILISTIC ``{cardId: P(deck still holds ≥1 copy)}`` — the complement to the sound
        ``_deck_empty_ids`` (ADR-0029, `Board.deck_contains_odds`). When the deck-tracker has resolved
        the prizes (`deck_known` given), there is no randomness left — collapse to exact certainty
        (1.0 for any in-deck card, 0.0 otherwise), reusing the SAME sound counts so the two signals
        cannot disagree. Otherwise split each card's unseen copies (`decklist − visible`) over the
        face-down prize slots hypergeometrically (`deck_odds.contains_odds`). None when uncomputable
        (no deck / no `deckCount`) → the signal stays silent. Never raises (grader safety)."""
        if not self.deck:
            return None
        try:
            if deck_known is not None:                    # prizes resolved -> exact certainty, no guess
                return {cid: 1.0 for cid in deck_known}
            deck_count = me.get("deckCount")
            if not isinstance(deck_count, int) or isinstance(deck_count, bool) or deck_count < 0:
                return None                               # no sound deck size -> stay silent
            prize_list = me.get("prize") or []            # face-DOWN prizes (a face-up prize visible)
            prizes_hidden = sum(1 for p in prize_list
                                if not (isinstance(p, dict) and p.get("id") is not None))
            seen = self._visible_card_counts(me)
            return deck_odds.contains_odds(Counter(self.deck), seen, deck_count, prizes_hidden)
        except Exception:
            return None

    def _deck_empty_ids(self, me: dict, prizes: dict | None = None) -> frozenset:
        """The card ids my deck is PROVABLY empty of. SOUND in both modes, never probabilistic.

        Stateless (``prizes`` None): every copy of the id is accounted for OUTSIDE the deck (hand,
        discard, board, a face-up prize), reaching the known 60-card count — so none can remain. The
        deck and FACE-DOWN prizes are the only unseen zones, so a count that falls short leaves the
        id out (it could be prized). Exact (``prizes`` given by the deck-tracker): the prizes are
        resolved, so ``deck = decklist − visible − prizes`` and the id is empty when that is 0 —
        which ALSO catches cards that are entirely prized. Empty when no deck list is configured."""
        if not self.deck:
            return frozenset()
        deck_counts = Counter(self.deck)
        seen = self._visible_card_counts(me)
        if prizes is not None:
            return frozenset(cid for cid, n in deck_counts.items()
                             if n - seen.get(cid, 0) - prizes.get(cid, 0) <= 0)
        return frozenset(cid for cid, n in deck_counts.items() if seen.get(cid, 0) >= n)

    @staticmethod
    def _count_in_play(poke: dict | None, counts: Counter) -> None:
        """Add a board Pokémon and everything attached to / stacked under it (its own id, attached
        Energy CARDS and Tools, and the `preEvolution` cards beneath it) to `counts` — all are out
        of the deck. One walk, shared with the deck tracker and `MySide.visible_counts`
        (`common.board_cards`, Issue #297)."""
        for cid in body_card_ids(poke):
            counts[cid] += 1
