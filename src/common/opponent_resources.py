"""Opponent Resources — the opponent-side mirror of the own-deck models (ADR-0047).

The **Resources** subsystem of the Opponent Model facade (`opponent_model.OpponentModel`). Two parts,
mirroring the own side exactly:

- ``copies_left_odds`` — the *stateless, probabilistic* estimate (the opponent-side ``deck_odds``): given
  the Read's representative-build prior, P(the opponent's deck still holds ≥1 copy of a card). The key
  asymmetry vs the own side is that the opponent's HAND is hidden (only ``handCount`` is known), so an
  unseen copy may sit in their deck, prizes, OR hand — hand joins prizes in the hidden non-deck pool.
- ``OpponentResourceModel`` — the *match-scoped* cross-turn tracker (the opponent-side ``deck_tracker``):
  the SOUND/observed signals (deck-count trajectory → deck-out timing, hand-size delta, discard dumps,
  KOs taken) that a single snapshot can't give.

Pure / lib-free; **never raises** (grader safety) and every estimate **fails OPEN** — it never suppresses
a real line on a missing read (the ADR-0047 sound-or-silent contract).
"""
from __future__ import annotations

from collections import Counter
from math import ceil

from . import deck_odds

_STACKS = ("energyCards", "tools", "preEvolution")   # cards attached to / stacked under a board Pokémon


def _card_id(entry) -> int | None:
    """The card id of a zone entry (a dict ``{'id': ...}`` or a bare int), or None."""
    if isinstance(entry, dict):
        return entry.get("id")
    return entry if isinstance(entry, int) else None


def opp_visible_counts(opp: dict) -> Counter:
    """The opponent's cards provably OUTSIDE their deck+prizes+hand — a ``{cardId: count}`` multiset.

    Visible = their discard, every board Pokémon (its id + attached Energy/Tools + stacked
    pre-evolutions) and any FACE-UP prize. Their HAND is deliberately excluded: we only know its size
    (``handCount``), not its contents, so a copy that could be in hand stays *unseen* (and joins the
    hidden non-deck pool in ``copies_left_odds``). Never raises.
    """
    c: Counter = Counter()
    try:
        for entry in (opp.get("discard") or []):
            cid = _card_id(entry)
            if cid is not None:
                c[cid] += 1
        for zone in ("active", "bench"):
            for poke in (opp.get(zone) or []):
                if not poke:
                    continue
                if poke.get("id") is not None:
                    c[poke["id"]] += 1
                for group in _STACKS:
                    for e in (poke.get(group) or []):
                        cid = _card_id(e)
                        if cid is not None:
                            c[cid] += 1
        for p in (opp.get("prize") or []):
            cid = _card_id(p)          # face-up prize carries an id; face-down is None
            if cid is not None:
                c[cid] += 1
    except Exception:
        return Counter()
    return c


def copies_left_odds(rep_build, opp: dict) -> dict[int, float]:
    """P(the opponent's deck still holds ≥1 copy) for every card in the representative-build prior.

    The opponent-side analog of ``deck_odds.contains_odds``: split each card's unseen copies
    (``rep_build`` count − visible) over the opponent's hidden non-deck pool. Because the opponent's
    hand is hidden, that pool is **prizes + hand** (a card not in deck is in a prize *or* the hand), so
    ``prizes_hidden`` passed to the hypergeometric is ``face-down prizes + handCount``.

    Args:
        rep_build: the confident archetype's representative build — a ``{cardId: count}`` mapping or an
            iterable of card ids (a 60-card multiset); ``Counter`` is applied to an iterable.
        opp: the opponent player dict (``deckCount`` / ``handCount`` / ``prize`` / board / ``discard``).

    Returns:
        ``{cardId: P(deck holds ≥1)}`` over the build. Fails OPEN — any bad input collapses to the
        conservative ``1.0`` ("assume present"), exactly like ``deck_odds`` (never stand a line down on
        a guess).
    """
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
    """The opponent-side cross-turn tracker — the SOUND/observed Resources signals a single snapshot
    can't give (the opponent-side ``deck_tracker.OwnCardModel``).

    Feed every observation to :meth:`observe`; read the properties. Match-scoped: resets on the
    deck-submission step (no ``select``) and on the turn counter going backwards (the local self-play
    harness reuses one process; the grader forks per match). Pure / lib-free; :meth:`observe` never
    raises. Estimates fail OPEN — an unknown value is ``None`` (the consumer does nothing), never a
    fabricated number.

    ``observe`` is called once per *decision* (many times per turn). The deltas are therefore computed
    against the previous **distinct turn**, not the previous decision within a turn; ``took_ko_this_turn``
    is measured against the start of the current turn.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Forget all match state (a new game began)."""
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
        """Update from one observation. Never raises: on any error it keeps prior state (never a
        false certainty, never a crash)."""
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
        """The opponent's current deck size (sound — the latest observed ``deckCount``)."""
        return self._deck

    @property
    def hand_size(self) -> int | None:
        """The opponent's current hand size (sound — the latest observed ``handCount``)."""
        return self._hand

    @property
    def hand_size_delta(self) -> int | None:
        """Change in the opponent's hand size since the previous distinct turn (a big positive jump =
        they drew/tailored a large hand); None until a prior turn is known."""
        if self._hand is None or self._prev_hand is None:
            return None
        return self._hand - self._prev_hand

    @property
    def discard_delta(self) -> int | None:
        """Growth of the opponent's discard pile since the previous distinct turn; None until known."""
        if self._discard is None or self._prev_discard is None:
            return None
        return self._discard - self._prev_discard

    @property
    def last_turn_dumped(self) -> bool:
        """Coarse proxy for an Ultra-Ball-class discard-cost play last turn: the opponent's discard grew
        by ≥2 since the previous distinct turn. A conservative signal (the consuming proposal refines it
        with a real discard-cost card fact); fails to False when unknown."""
        d = self.discard_delta
        return bool(d is not None and d >= 2)

    @property
    def took_ko_this_turn(self) -> bool:
        """Did I take a prize (i.e. a KO) during the current turn — my prize pile shrank since the turn
        started. Sound whenever it fires; False when unknown (never a false certainty)."""
        return bool(self._turn_start_my_prizes is not None and self._my_prizes is not None
                    and self._my_prizes < self._turn_start_my_prizes)

    @property
    def my_pokemon_koed_last_turn(self) -> bool:
        """Did the OPPONENT take ≥1 prize between the start of my previous distinct turn and the
        start of the current one — i.e. one of MY Pokémon was Knocked Out during their last turn
        (Unfair Stamp's own play condition; the attacker takes prize cards from their OWN pile on a
        KO, rules.md §6). Sound-when-fired up to one rare edge: a self-recoil KO during my OWN turn
        also lands in the measured interval (fail-open — the engine still legality-gates any actual
        play). False when unknown."""
        return bool(self._prev_turn_start_opp_prizes is not None
                    and self._turn_start_opp_prizes is not None
                    and self._turn_start_opp_prizes < self._prev_turn_start_opp_prizes)

    @property
    def deckout_in_turns(self) -> int | None:
        """Estimated game-turns until the opponent's deck is exhausted, from the observed deck-count
        trajectory (``deck_count / average decrease per turn``). None until ≥2 distinct-turn samples
        show a net decrease — an unknown estimate is silent, never fabricated."""
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
