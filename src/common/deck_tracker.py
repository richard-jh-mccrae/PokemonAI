"""Own-card perfect-information model — the "deck tracker" (match-scoped).

Maintains an EXACT account of the agent's own cards by zone, from the known 60-card decklist and
the always-visible zones (hand / discard / board + attached Energy/Tools + evolution stacks),
anchored by what a deck SEARCH reveals.

Soundness rests on one invariant: the 6-card PRIZE pile is fixed at game start and only ever
shrinks (a card is taken into hand on a Knock Out). Everything else (deck<->hand<->discard<->board)
is re-read fresh from each observation, so it cannot drift — the ONLY persistent state is the prize
multiset. Once the prizes are known, the deck is derived exactly EVERY turn:

    deck = decklist - prizes - visible

**Anchoring.** A search presents the player the whole remaining deck in ``select.deck`` (length ==
``deckCount``); the card whose effect is resolving (the played search card) sits in no zone but is
named by ``select.effect`` / ``select.contextCard``, so it is counted as visible. Then
``prizes = decklist - select.deck - visible`` is exact — accepted only when it has exactly
``prizes_remaining`` cards (a partial/filtered reveal is rejected).

**Before the first reveal** the prize split is genuinely unknown (prizes are set face-down), so the
model reports None and the caller falls back to the sound stateless bounds (a card with more copies
hidden than there are prize slots must have the surplus in the deck — pigeonhole). On ANY
inconsistency (a "prized" card turns up visible, counts exceed the decklist, prizes grow) the anchor
is dropped — a desynced model must never assert a false certainty.

Match-scoped: reset on a new game (the local self-play harness reuses one process; the grader forks
per match — see the kaggle-execution-model). Pure / lib-free; never raises (grader safety).
"""
from __future__ import annotations

from collections import Counter

_HAND, _DISCARD, _ACTIVE, _BENCH = "hand", "discard", "active", "bench"
_STACKS = ("energyCards", "tools", "preEvolution")   # cards attached to / stacked under a board Pokémon


def _card_id(entry) -> int | None:
    """The card id of a zone entry (a dict ``{'id': ...}`` or a bare int), or None."""
    if isinstance(entry, dict):
        return entry.get("id")
    return entry if isinstance(entry, int) else None


class OwnCardModel:
    """A match-scoped, sound model of the agent's own hidden cards (deck + prizes).

    Feed every observation to :meth:`observe`; read :meth:`prize_export` for the exact prize multiset
    (or None until the first search anchors it). The consumer derives the deck from it.
    """

    def __init__(self, deck) -> None:
        self.decklist: Counter = Counter(int(c) for c in deck)
        self._prizes: Counter | None = None       # exact prize multiset once anchored (else None)
        self._anchor_remaining: int | None = None  # prizes_remaining at the last anchor
        self._last_turn: int | None = None

    def reset(self) -> None:
        """Forget all match state (a new game began)."""
        self._prizes = None
        self._anchor_remaining = None
        self._last_turn = None

    def prize_export(self) -> dict | None:
        """The exact prize multiset as a plain ``{cardId: count}`` dict, or None if not yet known."""
        return dict(self._prizes) if self._prizes is not None else None

    def observe(self, obs: dict) -> None:
        """Update the model from one observation. Never raises: on any error it drops the anchor
        (falls back to stateless bounds) rather than risk a false certainty or crashing the agent."""
        try:
            self._observe(obs)
        except Exception:
            self._prizes = None

    # -- internals -------------------------------------------------------------------------------
    def _observe(self, obs: dict) -> None:
        select = obs.get("select")
        if select is None:                         # the initial deck-submission step == match start
            self.reset()
            return
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else None
        if not me:
            return

        turn = state.get("turn")
        if self._last_turn is not None and turn is not None and turn < self._last_turn:
            self.reset()                           # turn went backwards -> a new match (local harness)
        self._last_turn = turn

        visible = self._visible(me, select)
        if any(visible[c] > self.decklist.get(c, 0) for c in visible):
            self._prizes = None                    # a foreign / inconsistent state -> never trust it
            return
        remaining = len(me.get("prize") or [])
        hidden = self.decklist - visible           # the deck ∪ prizes multiset (everything unseen)

        revealed = self._revealed_full_deck(select, me)
        if revealed is not None:                   # a full deck reveal -> (re)anchor the prizes exactly
            prizes = self.decklist - revealed - visible
            if sum(prizes.values()) == remaining and all(v >= 0 for v in prizes.values()):
                self._prizes, self._anchor_remaining = prizes, remaining
                return                             # anchored — done
            # a partial / filtered reveal (size mismatch): fall through, keep any prior anchor

        if self._prizes is None:
            return                                 # nothing to maintain yet
        if remaining == self._anchor_remaining:
            if not self._consistent(self._prizes, hidden, remaining):
                self._prizes = None                # a prized card surfaced -> desync, drop it
        elif remaining < self._anchor_remaining:   # a prize was taken since the anchor
            candidate = self._prizes & hidden      # the prizes still possibly hidden (taken ones left)
            if sum(candidate.values()) == remaining and self._consistent(candidate, hidden, remaining):
                self._prizes, self._anchor_remaining = candidate, remaining   # uniquely reconciled
            else:
                self._prizes = None                # ambiguous -> fall back until the next reveal
        else:                                      # prizes grew -> impossible -> desync
            self._prizes = None

    def _visible(self, me: dict, select: dict) -> Counter:
        """MY cards provably OUTSIDE deck+prizes: hand, discard, every board Pokémon (its id +
        attached Energy/Tools + the cards stacked under it) AND the card whose effect is resolving
        (``select.effect`` / ``contextCard`` — it has left the deck but sits in no zone)."""
        c: Counter = Counter()
        for zone in (_HAND, _DISCARD):
            for entry in (me.get(zone) or []):
                cid = _card_id(entry)
                if cid is not None:
                    c[cid] += 1
        for zone in (_ACTIVE, _BENCH):
            for poke in (me.get(zone) or []):
                if not poke:
                    continue
                if poke.get("id") is not None:
                    c[poke["id"]] += 1
                for group in _STACKS:
                    for e in (poke.get(group) or []):
                        cid = _card_id(e)
                        if cid is not None:
                            c[cid] += 1
        for key in ("effect", "contextCard"):
            cid = _card_id(select.get(key))
            if cid is not None:
                c[cid] += 1
        return c

    def _revealed_full_deck(self, select: dict, me: dict) -> Counter | None:
        """The full remaining deck as a multiset, ONLY when a search reveals all of it
        (``len(select.deck) == deckCount``); None for no/partial reveal — never anchor off a subset."""
        deck = select.get("deck")
        if not deck or len(deck) != me.get("deckCount"):
            return None
        return Counter(cid for cid in (_card_id(d) for d in deck) if cid is not None)

    @staticmethod
    def _consistent(prizes: Counter, hidden: Counter, remaining: int) -> bool:
        """The prize multiset must be a submultiset of the still-hidden cards and have the right size
        — else a 'prized' card is contradicted by what we can now see (a desync)."""
        return sum(prizes.values()) == remaining and all(prizes[c] <= hidden[c] for c in prizes)
