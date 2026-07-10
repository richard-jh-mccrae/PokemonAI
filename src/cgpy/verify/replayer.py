"""Replay a recorded native trace through cgpy and localize the first divergence (ADR-0050).

Randomness binding (docs/pyeng/determinism.md): draw identities come from the mover's own
full DRAW logs (a seat's draws always land in its own next window, in order), coins from that
seat's COIN logs, and deck/prize ORDER re-syncs from the god frame at every step — with a
multiset assertion, and order-adoption only when a shuffle actually occurred in the window
(otherwise an order mismatch is a real divergence).

The per-frame comparison is exact: the mover's live obs (select + logs + current) must equal
the recorded one with no normalization.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import Engine
from ..rng import ReplayRandomness
from ..schema import LogType
from .differ import Divergence, first_divergence
from .trace import Trace


@dataclass
class ReplayReport:
    trace_path: str = ""
    frames_total: int = 0
    frames_green: int = 0
    divergence: Divergence | None = None
    frame: int = -1
    kind: str = ""            # obs | god | error | result
    error: str = ""

    @property
    def clean(self) -> bool:
        return self.divergence is None and not self.error

    def __str__(self) -> str:
        if self.clean:
            return f"CLEAN  {self.frames_green}/{self.frames_total} frames"
        head = f"DIVERGED at frame {self.frame} ({self.kind}), " \
               f"{self.frames_green}/{self.frames_total} green"
        if self.error:
            return f"{head}\n  {self.error}"
        return f"{head}\n{self.divergence}"


class _TraceRandomness(ReplayRandomness):
    """Per-seat draw/coin binding fed lazily from the trace as frames are consumed."""

    def __init__(self):
        super().__init__()
        self.coin_queues: dict[int, list[bool]] = {0: [], 1: []}

    def coin_for(self, seat: int) -> bool:
        if not self.coin_queues[seat]:
            from ..rng import ReplayError
            raise ReplayError(f"seat {seat}: coin requested but none recorded")
        return self.coin_queues[seat].pop(0)

    # GameState.coin_flip calls rng.coin() without a seat; cgpy binds the acting seat via
    # engine wiring below (set before each flip).
    acting_seat: int = 0

    def coin(self) -> bool:
        return self.coin_for(self.acting_seat)


def _feed_from_window(rnd: _TraceRandomness, mover: int, logs: list[dict]) -> None:
    """Queue the mover's own full DRAW serials + COIN outcomes from their window."""
    for l in logs:
        if l.get("type") == int(LogType.DRAW) and l.get("playerIndex") == mover \
                and l.get("serial") is not None:
            rnd.draw_queues[mover].append(l["serial"])
        elif l.get("type") == int(LogType.COIN) and l.get("playerIndex") == mover:
            rnd.coin_queues[mover].append(bool(l.get("head")))


def _sync_hidden_order(eng: Engine, god: dict, *, frame: int) -> str | None:
    """Adopt deck order from the god frame (multiset-asserted); error string on mismatch.
    Hands are identity-tracked in cgpy, so a hand mismatch is a real divergence, not a sync."""
    gs = eng.gs
    for seat in (0, 1):
        god_deck = [c["serial"] for c in god["players"][seat]["deck"]]
        ours = gs.players[seat].deck
        if sorted(god_deck) != sorted(ours):
            only_god = sorted(set(god_deck) - set(ours))
            only_us = sorted(set(ours) - set(god_deck))
            return (f"frame {frame}: seat {seat} deck multiset mismatch "
                    f"(god-only {only_god[:6]}, cgpy-only {only_us[:6]})")
        ours[:] = god_deck
        god_prize = [c["serial"] for c in god["players"][seat]["prize"]]
        ours_p = gs.players[seat].prize
        if sorted(god_prize) != sorted(ours_p):
            return (f"frame {frame}: seat {seat} prize multiset mismatch "
                    f"(god {len(god_prize)} vs cgpy {len(ours_p)})")
        ours_p[:] = god_prize
        god_hand = [c["serial"] for c in god["players"][seat].get("hand") or []]
        ours_h = gs.players[seat].hand
        if god_hand != ours_h:
            return (f"frame {frame}: seat {seat} HAND mismatch\n"
                    f"    god:  {god_hand}\n    cgpy: {ours_h}")
    return None


def _strip_for_compare(obs: dict) -> dict:
    out = dict(obs)
    out.pop("search_begin_input", None)
    return out


def replay(trace: Trace, *, compare_god: bool = True) -> ReplayReport:
    report = ReplayReport(frames_total=len(trace.frames))
    rnd = _TraceRandomness()
    deck0, deck1 = trace.decks

    # Pre-feed every mover window (draw identities/coins are consumed strictly in order,
    # and feeding ahead is safe: queues are per-seat FIFOs in chronological order).
    for fr in trace.frames:
        mover = fr["obs"]["current"]["yourIndex"]
        _feed_from_window(rnd, mover, fr["obs"].get("logs") or [])

    # Prize identities: facedown deals never log serials — bind from the god frames
    # (the first frame where a seat's prize row appears, in array order = deal order).
    fed_prize = {0: False, 1: False}
    for fr in trace.frames:
        god = fr.get("god")
        if god is None:
            continue
        for seat in (0, 1):
            row = god["players"][seat].get("prize") or []
            if row and not fed_prize[seat]:
                rnd.prize_feed[seat] = [c["serial"] for c in row]
                fed_prize[seat] = True
        if all(fed_prize.values()):
            break

    eng, err_player, err_type = Engine.start(deck0, deck1, rng=rnd)
    if eng is None:
        report.error = f"cgpy rejected a deck: seat {err_player} errorType {err_type}"
        report.kind = "error"
        return report

    for k, fr in enumerate(trace.frames):
        mover = fr["obs"]["current"]["yourIndex"]
        rnd.acting_seat = mover

        # God sync BEFORE comparing: the recorded frame's hidden order is authoritative.
        god = fr.get("god")
        if god is not None:
            err = _sync_hidden_order(eng, god, frame=k)
            if err:
                report.error, report.kind, report.frame = err, "god", k
                return report

        ours = _strip_for_compare(eng.observation(mover))
        theirs = _strip_for_compare(fr["obs"])
        d = first_divergence(theirs, ours)
        if d:
            report.divergence, report.kind, report.frame = d, "obs", k
            return report
        report.frames_green += 1

        choice = fr.get("choice")
        if choice is None:
            break
        try:
            eng.step(choice)
        except Exception as e:  # noqa: BLE001 — any engine failure is the finding itself
            report.error = f"frame {k}: cgpy raised on recorded choice {choice}: {e!r}"
            report.kind, report.frame = "error", k
            return report

    return report
