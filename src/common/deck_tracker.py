"""Own-card perfect-information model — the "deck tracker" (match-scoped, ADR-0023).

Soundness rests on one invariant: the 6-card PRIZE pile is fixed at game start and only shrinks.
Everything else is re-read fresh from each observation, so the prize multiset is the ONLY persistent
state, and once it is known ``deck = decklist - prizes - visible`` holds exactly every turn.

ANCHORING: a search that reveals the WHOLE deck (``len(select.deck) == deckCount``) makes
``prizes = decklist - select.deck - visible`` exact. A partial reveal is rejected.

Prize takes come from the LOG, never a guess (Issue #175). ``logs`` is a DELTA, so takes accumulate across
observations, keyed by the engine's per-card ``serial`` so a replayed frame cannot count one twice.

Before the first reveal, and on ANY inconsistency, the anchor is dropped and None reported — the
caller falls back to the sound stateless pigeonhole bounds. Never raises (grader safety).
"""
from __future__ import annotations

from collections import Counter

from cg.api import AreaType, LogType
from common.board_cards import body_card_entries, card_id as _card_id
from common.cards import card_store, play_clauses

_HAND, _DISCARD, _ACTIVE, _BENCH = "hand", "discard", "active", "bench"
_AREA_HAND, _AREA_PRIZE = 2, 6                       # cg.api AreaType.HAND / .PRIZE (log zone codes)
_AREA_DECK = int(AreaType.DECK)
_CLEAR_TOP = frozenset({int(LogType.SHUFFLE), int(LogType.MOVE_CARD_REVERSE)})
_DRAW = int(LogType.DRAW)
_MOVE = int(LogType.MOVE_CARD)


class OwnCardModel:
    """Feed every observation to :meth:`observe`; read :meth:`prize_export` for the exact prize multiset
    (None until a search anchors it). The consumer derives the deck from it."""

    def __init__(self, deck, *, cards=None) -> None:
        self.decklist: Counter = Counter(int(c) for c in deck)
        #: Card records by id — the unified store unless a test injects its own records.
        cards = card_store() if cards is None else cards
        self._stackers = frozenset(
            int(card_id) for card_id, record in cards.items()
            if any(clause.params.get("dest") == "deck_top" for clause in play_clauses(record)))
        self._known_top: tuple[tuple[int, int], ...] | None = None
        self._resolving_source: int | None = None
        self._prizes: Counter | None = None       # exact prize multiset once anchored (else None)
        self._anchor_remaining: int | None = None  # prizes_remaining at last anchor
        self._last_turn: int | None = None
        self._takes: dict = {}                    # serial -> cardId of MY logged prize takes
        self._takes_at_anchor: set = set()        # serials already priced into `_prizes`

    def reset(self) -> None:
        """Forget all match state (a new game began)."""
        self._known_top = None
        self._resolving_source = None
        self._prizes = None
        self._anchor_remaining = None
        self._takes = {}
        self._takes_at_anchor = set()
        self._last_turn = None

    def prize_export(self) -> dict | None:
        """The exact prize multiset as a plain ``{cardId: count}`` dict, or None if not yet known."""
        return dict(self._prizes) if self._prizes is not None else None

    def known_top_export(self) -> tuple[tuple[int, int], ...] | None:
        return self._known_top

    def observe(self, obs: dict) -> None:
        """Update the model from one observation. Never raises: on any error it drops the anchor
        (falls back to stateless bounds) rather than risk a false certainty or crashing the agent."""
        try:
            self._observe(obs)
        except Exception:
            self._prizes = None
            self._known_top = None
            self._resolving_source = None

    # -- internals -------------------------------------------------------------------------------
    def _observe(self, obs: dict) -> None:
        select = obs.get("select")
        if select is None:                         # initial deck-submission step == match start
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
            self.reset()                           # turn went backwards -> new match (local harness)
        self._last_turn = turn
        self._advance_known_top(obs, int(yi))
        self._record_prize_takes(obs, yi)

        visible = self._visible(me, select)
        if any(visible[c] > self.decklist.get(c, 0) for c in visible):
            self._prizes = None                    # foreign / inconsistent state -> never trust it
            return
        remaining = len(me.get("prize") or [])
        hidden = self.decklist - visible           # deck ∪ prizes multiset (everything unseen)

        revealed = self._revealed_full_deck(select, me)
        if revealed is not None:                   # full deck reveal -> (re)anchor prizes exactly
            prizes = self.decklist - revealed - visible
            if sum(prizes.values()) == remaining and all(v >= 0 for v in prizes.values()):
                self._prizes, self._anchor_remaining = prizes, remaining
                self._takes_at_anchor = set(self._takes)   # takes before this reveal are priced in
                return                             # anchored — done
            # partial / filtered reveal (size mismatch): fall through, keep prior anchor

        if self._prizes is None:
            return                                 # nothing to maintain yet
        if remaining == self._anchor_remaining:
            if not self._consistent(self._prizes, hidden, remaining):
                self._prizes = None                # prized card surfaced -> desync, drop it
        elif remaining < self._anchor_remaining:   # a prize was taken since the anchor
            named = self._prizes_after_logged_takes(remaining)   # the engine NAMED them (#175)
            if named is not None and self._consistent(named, hidden, remaining):
                self._prizes, self._anchor_remaining = named, remaining
                self._takes_at_anchor = set(self._takes)         # re-baseline: now priced in
                return
            candidate = self._prizes & hidden      # prizes still possibly hidden (taken ones left)
            if sum(candidate.values()) == remaining and self._consistent(candidate, hidden, remaining):
                self._prizes, self._anchor_remaining = candidate, remaining   # uniquely reconciled
            else:
                self._prizes = None                # ambiguous -> fall back until next reveal
        else:                                      # prizes grew -> impossible -> desync
            self._prizes = None

    def _advance_known_top(self, obs: dict, seat: int) -> None:
        select = obs.get("select") or {}
        resolving = next((int(entry["id"]) for entry in
                          (select.get("effect"), select.get("contextCard"))
                          if isinstance(entry, dict) and entry.get("id") is not None), None)
        placing = self._resolving_source in self._stackers
        belief = self._known_top
        for entry in obs.get("logs") or ():
            if not isinstance(entry, dict) or entry.get("playerIndex") != seat:
                continue
            try:
                kind = int(entry.get("type"))
            except (TypeError, ValueError):
                continue
            if kind in _CLEAR_TOP:
                belief = None
            elif kind == _DRAW:
                serial = entry.get("serial")
                belief = (belief[1:] or None) if (belief and serial is not None
                                                   and int(serial) == belief[0][0]) else None
            elif kind == _MOVE:
                source, destination = entry.get("fromArea"), entry.get("toArea")
                if destination == _AREA_DECK:
                    serial, card_id = entry.get("serial"), entry.get("cardId")
                    if placing and serial is not None and card_id is not None:
                        belief = (belief or ()) + ((int(serial), int(card_id)),)
                    else:
                        belief = None
                elif source == _AREA_DECK:
                    belief = None
        self._known_top = belief
        self._resolving_source = resolving

    def _record_prize_takes(self, obs: dict, yi: int) -> None:
        """Accumulate MY prize takes from the log DELTA, keyed by ``serial`` so a replayed frame cannot
        count one twice. An entry missing ``serial``/``cardId`` is ignored (the fallback stays in charge)."""
        for entry in (obs.get("logs") or ()):
            if not isinstance(entry, dict):
                continue
            if (entry.get("fromArea") != _AREA_PRIZE or entry.get("toArea") != _AREA_HAND
                    or entry.get("playerIndex") != yi):
                continue
            serial, cid = entry.get("serial"), entry.get("cardId")
            if serial is not None and cid is not None:
                self._takes[serial] = cid

    def _prizes_after_logged_takes(self, remaining: int) -> Counter | None:
        """The EXACT prize multiset after the takes the log NAMED, or None when the log does not fully
        account for the drop — an unconfirmed pile must never be asserted."""
        taken = Counter(cid for serial, cid in self._takes.items()
                        if serial not in self._takes_at_anchor)
        if sum(taken.values()) != self._anchor_remaining - remaining:
            return None                            # log doesn't explain the drop -> don't trust it
        if any(n > self._prizes[c] for c, n in taken.items()):
            return None                            # names a card that wasn't prized -> desync
        return self._prizes - taken

    def _visible(self, me: dict, select: dict) -> Counter:
        """MY cards provably OUTSIDE deck+prizes, plus the card whose effect is RESOLVING (it has left
        the deck but sits in no zone). That rider is deduped by ``serial``: an Ability's is still in play."""
        c: Counter = Counter()
        seen: set = set()

        def add(entry) -> None:
            cid = _card_id(entry)
            if cid is None:
                return
            c[cid] += 1
            serial = entry.get("serial") if isinstance(entry, dict) else None
            if serial is not None:
                seen.add(serial)

        for zone in (_HAND, _DISCARD):
            for entry in (me.get(zone) or []):
                add(entry)
        for zone in (_ACTIVE, _BENCH):
            for poke in (me.get(zone) or []):
                for entry in body_card_entries(poke):   # the ONE walk (common.board_cards)
                    add(entry)
        for key in ("effect", "contextCard"):
            entry = select.get(key)
            if _card_id(entry) is None:
                continue
            serial = entry.get("serial") if isinstance(entry, dict) else None
            if serial is not None and serial in seen:
                continue                           # already counted where it actually sits
            add(entry)
        return c

    def _revealed_full_deck(self, select: dict, me: dict) -> Counter | None:
        """The full remaining deck as a multiset, ONLY on a complete reveal; None otherwise — never
        anchor off a subset."""
        deck = select.get("deck")
        if not deck or len(deck) != me.get("deckCount"):
            return None
        return Counter(cid for cid in (_card_id(d) for d in deck) if cid is not None)

    @staticmethod
    def _consistent(prizes: Counter, hidden: Counter, remaining: int) -> bool:
        """The prize multiset must be a submultiset of the still-hidden cards, at the right size — else a
        "prized" card is contradicted by what we can now see (a desync)."""
        return sum(prizes.values()) == remaining and all(prizes[c] <= hidden[c] for c in prizes)
