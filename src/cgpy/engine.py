"""Engine facade: start / step / observation / god view / clone (ADR-0050).

`step` validates selections with the native semantics (min/max, in-range, no duplicates) and
returns nothing — read the next `pending`/`observation`. The mover for the current select is
`engine.select_seat`.
"""
from __future__ import annotations

from . import render, turn
from .cards import CardDB, ERR_NONE
from .rng import SeededRng
from .state import GameState


class SelectionError(IndexError):
    """Invalid selection (native battle_select raises IndexError for these)."""


class Engine:
    def __init__(self, state: GameState):
        self.gs = state

    @classmethod
    def start(cls, deck0: list[int], deck1: list[int], *, rng=None,
              db: CardDB | None = None) -> tuple["Engine | None", int, int]:
        """Begin a battle. Returns (engine, errorPlayer, errorType) — engine None when a
        deck is illegal (that seat loses without playing), mirroring native BattleStart."""
        db = db or CardDB.load()
        for seat, deck in enumerate((deck0, deck1)):
            err = db.validate_deck(deck)
            if err != ERR_NONE:
                return None, seat, err
        gs = GameState.start(db, deck0, deck1, rng or SeededRng())
        turn.start_game(gs)
        return cls(gs), -1, 0

    # ------------------------------------------------------------------ stepping

    @property
    def select_seat(self) -> int | None:
        return self.gs.pending.seat if self.gs.pending else None

    @property
    def result(self) -> int:
        return self.gs.result

    def step(self, indices: list[int]) -> None:
        p = self.gs.pending
        if p is None or self.gs.result != -1:
            raise SelectionError("battle has ended / no selection pending")
        if not (p.min_count <= len(indices) <= p.max_count):
            raise SelectionError(
                f"need {p.min_count}..{p.max_count} selections, got {len(indices)}")
        if any(not (0 <= i < len(p.options)) for i in indices):
            raise SelectionError("selection index out of range")
        if len(set(indices)) != len(indices):
            raise SelectionError("duplicate selection indices")
        turn.apply_answer(self.gs, [int(i) for i in indices])

    # ------------------------------------------------------------------ views

    def observation(self, viewer: int | None = None, *, sbi_token: str | None = "cgpy") -> dict:
        seat = viewer if viewer is not None else (self.select_seat or 0)
        return render.observation(self.gs, seat, sbi_token=sbi_token)

    def god_frame(self) -> dict:
        return render.god_frame(self.gs)

    def clone(self) -> "Engine":
        return Engine(self.gs.clone())

    def fork(self) -> "Engine":
        """An independent twin: cloned state AND a deep-copied rng, so stepping one never
        advances the other's randomness — the search API's clone-per-step contract (M3)."""
        import copy

        twin = self.gs.clone()
        twin.rng = copy.deepcopy(self.gs.rng)
        return Engine(twin)
