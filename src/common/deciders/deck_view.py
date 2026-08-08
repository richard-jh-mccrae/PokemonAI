"""What is left in the deck: exact counts where the tracker knows, hypergeometric odds where it does
not (ADR-0029). The emptiness oracle is SOUND — it claims a card is gone only when the count proves it."""
from __future__ import annotations


from collections import Counter

from common import deck_odds
from common.board_cards import body_card_ids
from common.deciders.facts import Board



class DeckViewMixin:
    """Deck contents: what is known exactly, and what is only probable."""

    def _unseen_deck_counts(self, me: dict, board: Board) -> dict:
        """My deck as *"not provably gone"* counts. The pre-anchor fallback is memoised on the IDENTITY
        of ``(me, board)`` — `_playability_zones` caches on identity, so a fresh dict would miss it."""
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
        """My deck can still yield a Basic Energy — the fuel gate for an accelerator. Fail-open (True)
        while nothing is known-exhausted; False with no stats."""
        if not self.stats:
            return False
        empty = deck_empty or frozenset()
        for cid in set(self.deck or ()):
            stat = self.stats.get(cid)
            if stat and stat.is_basic_energy and cid not in empty:
                return True
        return False

    def _basic_energy_types_in_deck(self, deck_empty) -> frozenset:
        """Basic-Energy TYPES my deck can still yield. *Not-provably-empty*, never provably-present
        (ADR-0067); the honest probability lives in `CombatMath.readiness_p`. Empty with no stats."""
        if not self.stats:
            return frozenset()
        empty = deck_empty or frozenset()
        return frozenset(
            stat.energyType for cid in set(self.deck or ())
            if cid not in empty and (stat := self.stats.get(cid)) is not None
            and stat.is_typed_basic_energy)

    def _deck_basic_energy_fuel(self, etype) -> float:
        """Basic Energy a whole-deck search rider can EXPECT to find — the `expected` leg, never `p_any`
        or `floor` (ADR-0077 decision 3). ``etype`` None is an untyped rider: the cross-type union."""
        model = self._state_model
        if model is None:
            return 0.0
        counts = model.mine.deck_energy_counts
        if etype is None:
            return float(sum(c.expected for c in counts.values()))
        triple = counts.get(etype)
        return float(triple.expected) if triple else 0.0

    def _deck_body_names(self) -> frozenset:
        """Every card NAME in this decklist. NAMES, not ids: `evolvesFrom` identifies a stage by name and
        reprints share a name across ids, so an id-keyed test misses the reprint. Memoised, deck-fixed."""
        cached = getattr(self, "_deck_body_names_cache", None)
        if cached is not None:
            return cached
        names = frozenset(s.name for s in (self.stats.get(c) for c in set(self.deck or ()))
                          if s and s.name) if self.stats else frozenset()
        self._deck_body_names_cache = names
        return names

    def _visible_card_counts(self, me: dict) -> Counter:
        """My card copies provably OUTSIDE the deck: hand, discard, every board Pokémon (with what is
        attached and stacked under it) and FACE-UP prizes. Face-down prizes stay uncounted."""
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
        """EXACT ``decklist − visible − prizes`` once the tracker anchors; None before, never a guess."""
        if not self.deck or prizes is None:
            return None
        deck_counts = Counter(self.deck)
        seen = self._visible_card_counts(me)
        return {cid: rem for cid, n in deck_counts.items()
                if (rem := n - seen.get(cid, 0) - prizes.get(cid, 0)) > 0}

    def _deck_contains_prob(self, me: dict, deck_known: dict | None) -> dict | None:
        """PROBABILISTIC ``{cardId: P(deck still holds ≥1 copy)}`` (ADR-0029) — anchored, it collapses to
        certainty off the SAME sound counts. None when uncomputable; never raises (grader safety)."""
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
        """The card ids my deck is PROVABLY empty of. SOUND in both modes, never probabilistic: without
        ``prizes`` a short count leaves the id out, since it could be prized."""
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
        """Add a board Pokémon and everything attached to or stacked under it to `counts`. One walk,
        shared with the deck tracker and `MySide.visible_counts` (`common.board_cards`)."""
        for cid in body_card_ids(poke):
            counts[cid] += 1
