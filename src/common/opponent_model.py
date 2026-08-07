"""Opponent Model — the `board.opponent` facade over all opponent *knowledge* (ADR-0047): Identity
(the injected ``Scout``), Resources (``opponent_resources``) and Dispositions (the matched Brief's
``opponent_properties``, fed in per turn by the Pilot's γ-gated match).

Constructed once per match; one :meth:`observe` fan-out is the only write seam. **Fails OPEN** —
every accessor returns a safe default on a missing read, and :meth:`observe` never raises.
"""
from __future__ import annotations

from collections import Counter

from .opponent_resources import OpponentResourceModel, copies_left_odds
from .scouting.read import Read


class OpponentModel:
    """The opponent-knowledge facade (``board.opponent``)."""

    def __init__(self, scout=None, artifact=None, resources=None, *,
                 confidence_threshold: float = 0.6) -> None:
        self.scout = scout                                     # Identity subsystem (DI)
        self.artifact = artifact                               # representative-build prior for copies odds
        self.resources = resources or OpponentResourceModel()  # Resources subsystem (match-scoped)
        self.confidence_threshold = confidence_threshold
        self._read: Read = Read()
        self._brief = None                                     # Dispositions: the matched Brief (fed in)
        self._opp: dict | None = None                          # last opp player dict (for copies odds)

    # -- write seam -------------------------------------------------------------------------------
    def observe(self, obs: dict) -> Read:
        """Never raises — a failed subsystem degrades to its safe default."""
        try:
            self._read = self.scout.observe(obs) if self.scout is not None else Read()
        except Exception:
            self._read = Read()
        self.resources.observe(obs)
        self._opp = self._opp_of(obs)
        return self._read

    def note_brief(self, brief) -> None:
        """None clears it (posture off / no cover), so ``disposition`` returns the caller default."""
        self._brief = brief

    @staticmethod
    def _opp_of(obs: dict) -> dict | None:
        try:
            state = obs.get("current") or {}
            players = state.get("players") or []
            oi = 1 - state.get("yourIndex", 0)
            return players[oi] if 0 <= oi < len(players) and players[oi] else None
        except Exception:
            return None

    # -- Identity ---------------------------------------------------------------------------------
    @property
    def read(self) -> Read:
        """Always a ``Read`` (empty when posture off / unseen)."""
        return self._read

    @property
    def archetype(self) -> str | None:
        cands = self._read.candidates if self._read else []
        if cands and cands[0][1] >= self.confidence_threshold:
            return cands[0][0]
        return None

    # -- Resources --------------------------------------------------------------------------------
    @property
    def deck_count(self) -> int | None:
        return self.resources.deck_count

    @property
    def deckout_in_turns(self) -> int | None:
        return self.resources.deckout_in_turns

    @property
    def hand_size(self) -> int | None:
        return self.resources.hand_size

    @property
    def hand_size_delta(self) -> int | None:
        return self.resources.hand_size_delta

    @property
    def last_turn_dumped(self) -> bool:
        return self.resources.last_turn_dumped

    @property
    def took_ko_this_turn(self) -> bool:
        return self.resources.took_ko_this_turn

    def copies_left_odds(self, card_id: int | None = None):
        """P(the opponent's deck still holds ≥1 copy); ``None`` → the whole map. Fails OPEN at 1.0
        ("assume present") for an unknown card, so an unrecognized opponent suppresses nothing."""
        odds = self._copies_odds_map()
        if card_id is None:
            return odds
        return odds.get(card_id, 1.0)

    def _copies_odds_map(self) -> dict[int, float]:
        arch = self.archetype
        if arch is None or self.artifact is None or self._opp is None:
            return {}
        build = (self.artifact.dossiers.get(arch) or {}).get("representative_build") or []
        if not build:
            return {}
        return copies_left_odds(Counter(build), self._opp)

    # -- Dispositions -----------------------------------------------------------------------------
    def disposition(self, key: str, default=None):
        """The canonical read behind ``Board.opp_property``."""
        if self._brief is None:
            return default
        return (self._brief.opponent_properties or {}).get(key, default)
