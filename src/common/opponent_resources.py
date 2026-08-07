"""Opponent Resources — the opponent-side mirror of the own-deck models (ADR-0047): stateless
``copies_left_odds`` (mirrors ``deck_odds``) plus the match-scoped ``OpponentResourceModel`` (mirrors
``deck_tracker``). The asymmetry: their HAND is hidden, so it joins prizes in the non-deck pool.

Pure / lib-free; **never raises** and every estimate **fails OPEN**.
"""
from __future__ import annotations

from collections import Counter
from math import ceil

from . import deck_odds
from .board_cards import body_card_ids, card_id as _card_id


def opp_visible_counts(opp: dict) -> Counter:
    """The opponent's cards provably OUTSIDE their deck+prizes+hand — a ``{cardId: count}`` multiset.
    Their HAND is deliberately excluded: only its size is known. Never raises."""
    c: Counter = Counter()
    try:
        for entry in (opp.get("discard") or []):
            cid = _card_id(entry)
            if cid is not None:
                c[cid] += 1
        for zone in ("active", "bench"):
            for poke in (opp.get(zone) or []):
                for cid in body_card_ids(poke):        # the ONE walk (common.board_cards)
                    c[cid] += 1
        for p in (opp.get("prize") or []):
            cid = _card_id(p)          # face-up prize carries an id; face-down is None
            if cid is not None:
                c[cid] += 1
    except Exception:
        return Counter()
    return c


def copies_left_odds(rep_build, opp: dict) -> dict[int, float]:
    """``{cardId: P(deck holds ≥1)}`` over ``rep_build``. The hidden non-deck pool handed to the
    hypergeometric is ``face-down prizes + handCount``, since their hand is hidden. Fails OPEN."""
    try:
        decklist = rep_build if isinstance(rep_build, dict) else Counter(int(c) for c in rep_build)
        visible = opp_visible_counts(opp)
        deck_count = opp.get("deckCount")
        prize_list = opp.get("prize") or []
        prizes_hidden = sum(1 for p in prize_list if _card_id(p) is None)
        hand_count = int(opp.get("handCount") or 0)
        hidden_nondeck = prizes_hidden + hand_count
        return deck_odds.contains_odds(decklist, visible, deck_count, hidden_nondeck)
    except Exception:
        return {}


class OpponentResourceModel:
    """The opponent-side cross-turn tracker. ``observe`` is called once per *decision*, so the deltas
    are against the previous **distinct turn**. Unknown is ``None``, never a fabricated number."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_turn: int | None = None
        self._deck: int | None = None
        self._hand: int | None = None
        self._discard: int | None = None
        self._prev_hand: int | None = None      # opp handCount at the previous distinct turn
        self._prev_discard: int | None = None   # opp discard size at the previous distinct turn
        self._my_prizes: int | None = None
        self._turn_start_my_prizes: int | None = None
        self._turn_start_opp_prizes: int | None = None       # opp prize count at the current turn's start
        self._prev_turn_start_opp_prizes: int | None = None  # … and at the previous distinct turn's start
        self._deck_samples: dict[int, int] = {}  # turn -> opp deckCount (latest that turn)

    def observe(self, obs: dict) -> None:
        """Never raises: on any error it keeps prior state."""
        try:
            self._observe(obs)
        except Exception:
            pass

    # -- internals -------------------------------------------------------------------------------
    def _observe(self, obs: dict) -> None:
        if obs.get("select") is None:            # deck-submission step == match start
            self.reset()
            return
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        oi = 1 - yi
        opp = players[oi] if 0 <= oi < len(players) and players[oi] else None
        me = players[yi] if 0 <= yi < len(players) and players[yi] else None
        if opp is None:
            return

        turn = state.get("turn")
        if self._last_turn is not None and turn is not None and turn < self._last_turn:
            self.reset()                         # turn went backwards -> new match

        new_turn = turn != self._last_turn
        if new_turn and self._last_turn is not None:
            self._prev_hand = self._hand         # roll previous-distinct-turn snapshots
            self._prev_discard = self._discard

        self._deck = opp.get("deckCount")
        self._hand = opp.get("handCount")
        self._discard = len(opp.get("discard") or [])
        if turn is not None and self._deck is not None:
            self._deck_samples[turn] = self._deck

        my_prizes = len(me.get("prize") or []) if me else None
        if new_turn:
            self._turn_start_my_prizes = my_prizes
            self._prev_turn_start_opp_prizes = self._turn_start_opp_prizes
            self._turn_start_opp_prizes = len(opp.get("prize") or [])
        self._my_prizes = my_prizes
        self._last_turn = turn

    # -- reads -----------------------------------------------------------------------------------
    @property
    def deck_count(self) -> int | None:
        return self._deck

    @property
    def hand_size(self) -> int | None:
        return self._hand

    @property
    def hand_size_delta(self) -> int | None:
        """Since the previous distinct turn; None until a prior turn is known."""
        if self._hand is None or self._prev_hand is None:
            return None
        return self._hand - self._prev_hand

    @property
    def discard_delta(self) -> int | None:
        """Since the previous distinct turn; None until known."""
        if self._discard is None or self._prev_discard is None:
            return None
        return self._discard - self._prev_discard

    @property
    def last_turn_dumped(self) -> bool:
        """Coarse proxy for an Ultra-Ball-class discard-cost play last turn; False when unknown."""
        d = self.discard_delta
        return bool(d is not None and d >= 2)

    @property
    def took_ko_this_turn(self) -> bool:
        """My prize pile shrank since the turn started. False when unknown."""
        return bool(self._turn_start_my_prizes is not None and self._my_prizes is not None
                    and self._my_prizes < self._turn_start_my_prizes)

    @property
    def my_pokemon_koed_last_turn(self) -> bool:
        """The attacker takes prizes from their OWN pile on a KO (rules.md §6), so their pile
        shrinking means one of MINE was KO'd. Edge: my own self-recoil KO lands here too."""
        return bool(self._prev_turn_start_opp_prizes is not None
                    and self._turn_start_opp_prizes is not None
                    and self._turn_start_opp_prizes < self._prev_turn_start_opp_prizes)

    @property
    def deckout_in_turns(self) -> int | None:
        """Game-turns until their deck is exhausted, from the observed trajectory. None until ≥2
        distinct-turn samples show a net decrease."""
        if self._deck is None or len(self._deck_samples) < 2:
            return None
        turns = sorted(self._deck_samples)
        first_turn, last_turn = turns[0], turns[-1]
        drop = self._deck_samples[first_turn] - self._deck_samples[last_turn]
        span = last_turn - first_turn
        if drop <= 0 or span <= 0:
            return None
        rate = drop / span                       # cards leaving the deck per game-turn
        return ceil(self._deck / rate)
