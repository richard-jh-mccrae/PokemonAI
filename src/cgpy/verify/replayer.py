"""Replay a recorded native trace through cgpy and localize the first divergence (ADR-0059).

Randomness binds from recorded native logs; deck/prize ORDER re-syncs
UNCONDITIONALLY from the god frame every step, so only a MULTISET mismatch is a divergence.

The per-frame comparison is exact — the mover's live obs must equal the recorded one with NO
normalization.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import Engine
from ..rng import ReplayRandomness
from ..schema import AreaType, LogType
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

    # GameState.coin_flip passes the flip OWNER's seat; the acting-seat fallback covers paths
    # that flip without one.
    acting_seat: int = 0

    def coin(self, seat: int | None = None) -> bool:
        return self.coin_for(seat if seat is not None else self.acting_seat)


def _feed_from_window(rnd: _TraceRandomness, mover: int, logs: list[dict]) -> None:
    for l in logs:
        if l.get("type") == int(LogType.DRAW) and l.get("playerIndex") == mover \
                and l.get("serial") is not None:
            rnd.draw_queues[mover].append(l["serial"])
        elif l.get("type") == int(LogType.COIN) and l.get("playerIndex") == mover:
            rnd.coin_queues[mover].append(bool(l.get("head")))


def _sync_hidden_order(eng: Engine, god: dict, *, frame: int) -> str | None:
    """Hands are identity-tracked in cgpy, so a hand mismatch is a real DIVERGENCE, not a sync."""
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


def replay(trace: Trace, *, compare_god: bool = True, fork_check: bool = False,
           on_frame=None) -> ReplayReport:
    """``fork_check`` also applies every choice to a fresh `Engine.fork()` and requires identical renders."""
    report = ReplayReport(frames_total=len(trace.frames))
    rnd = _TraceRandomness()
    deck0, deck1 = trace.decks

    # feeding ahead is safe: the queues are per-seat FIFOs in chronological order
    for fr in trace.frames:
        mover = fr["obs"]["current"]["yourIndex"]
        _feed_from_window(rnd, mover, fr["obs"].get("logs") or [])

    # Coins/draws: the god stream is AUTHORITATIVE when present — each event appears exactly once,
    # including ones whose mover window falls past a truncated trace's end.
    god_coins: dict[int, list[bool]] = {0: [], 1: []}
    god_draws: dict[int, list[int]] = {0: [], 1: []}
    saw_god_logs = False
    for fr in trace.frames:
        for entry in fr.get("god_logs") or []:
            saw_god_logs = True
            if entry.get("type") in ("Coin", int(LogType.COIN)):
                god_coins[entry.get("playerIndex", 0)].append(bool(entry.get("head")))
            elif entry.get("type") in ("Draw", int(LogType.DRAW)) \
                    and entry.get("serial") is not None:
                god_draws[entry.get("playerIndex", 0)].append(entry["serial"])
    if saw_god_logs:
        rnd.coin_queues = god_coins
        rnd.draw_queues = god_draws
    else:
        # god-free: prize identities bind at TAKE time from the owner's own PRIZE->HAND moves
        for fr in trace.frames:
            mover = fr["obs"]["current"]["yourIndex"]
            for l in fr["obs"].get("logs") or []:
                if (l.get("type") == int(LogType.MOVE_CARD)
                        and l.get("playerIndex") == mover
                        and l.get("fromArea") == 6 and l.get("toArea") == 2
                        and l.get("serial") is not None):
                    rnd.prize_take_queue[mover].append(l["serial"])

    # Hand-pick channel: a victim's forced hand exits are MOVE_CARDs out of HAND while the TURN
    # belongs to their opponent — that turn gate is what excludes their own voluntary exits.
    if saw_god_logs:
        cur_turn = None
        for fr in trace.frames:
            for entry in fr.get("god_logs") or []:
                ty = entry.get("type")
                if ty in ("TurnStart", int(LogType.TURN_START)):
                    cur_turn = entry.get("playerIndex")
                elif (ty in ("MoveCard", int(LogType.MOVE_CARD))
                        and entry.get("fromArea") == int(AreaType.HAND)
                        and entry.get("serial") is not None
                        and cur_turn is not None
                        and entry.get("playerIndex") == 1 - cur_turn):
                    rnd.hand_pick_queue[entry["playerIndex"]].append(entry["serial"])
    else:
        turn_seen: dict[int, int | None] = {0: None, 1: None}
        for fr in trace.frames:
            mover = fr["obs"]["current"]["yourIndex"]
            cur_turn = turn_seen[mover]
            for l in fr["obs"].get("logs") or []:
                if l.get("type") == int(LogType.TURN_START):
                    cur_turn = l.get("playerIndex")
                elif (l.get("type") == int(LogType.MOVE_CARD)
                        and l.get("fromArea") == int(AreaType.HAND)
                        and l.get("serial") is not None
                        and l.get("playerIndex") == mover
                        and cur_turn == 1 - mover):
                    rnd.hand_pick_queue[mover].append(l["serial"])
            turn_seen[mover] = cur_turn

    # facedown deals never log serials, so bind from the god frames — array order = deal order
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
        else:
            # god-free: a revealed deck listing IS a reveal, so adopt its order (multiset-checked)
            listing = (fr["obs"].get("select") or {}).get("deck")
            if listing:
                serials = [c["serial"] for c in listing]
                ours = eng.gs.players[mover].deck
                if sorted(serials) != sorted(ours):
                    # A listing revealing the TRUE deck can name cards the provisional prize deal
                    # parked; swap pairwise (multiset-exact). Any RESIDUE is a real divergence.
                    prize = eng.gs.players[mover].prize
                    ours_ctr, listing_ctr = {}, {}
                    for s in ours:
                        ours_ctr[s] = ours_ctr.get(s, 0) + 1
                    for s in serials:
                        listing_ctr[s] = listing_ctr.get(s, 0) + 1
                    extra_deck = sorted(s for s in ours_ctr
                                        for _ in range(ours_ctr[s]
                                                       - listing_ctr.get(s, 0))
                                        if ours_ctr[s] > listing_ctr.get(s, 0))
                    extra_listing = sorted(s for s in listing_ctr
                                           for _ in range(listing_ctr[s]
                                                          - ours_ctr.get(s, 0))
                                           if listing_ctr[s] > ours_ctr.get(s, 0))
                    if (len(extra_deck) == len(extra_listing)
                            and all(s in prize for s in extra_listing)):
                        for wrong, right in zip(extra_deck, extra_listing):
                            ours[ours.index(wrong)] = right
                            prize[prize.index(right)] = wrong
                    if sorted(serials) != sorted(ours):
                        report.error = (f"frame {k}: revealed deck listing is a "
                                        f"different multiset than cgpy's deck")
                        report.kind, report.frame = "god", k
                        return report
                old_order = list(ours)
                ours[:] = serials   # listings preserve the TRUE internal order (M0 pin)
                if (eng.gs.pending is not None
                        and eng.gs.pending.deck_listing is not None
                        and old_order != serials):
                    # the pose snapshotted the PRE-adoption order, so option deck-indices must be
                    # remapped through serial identity (duplicates take positions in order)
                    eng.gs.pending.deck_listing = list(serials)
                    used: set[int] = set()

                    def _new_index(old_i: int) -> int:
                        s = old_order[old_i]
                        for j, s2 in enumerate(serials):
                            if s2 == s and j not in used:
                                used.add(j)
                                return j
                        return old_i
                    for o in eng.gs.pending.options:
                        if o.get("area") == int(AreaType.DECK) and "index" in o:
                            o["index"] = _new_index(o["index"])
                    if all(o.get("area") == int(AreaType.DECK)
                           for o in eng.gs.pending.options):
                        eng.gs.pending.options.sort(key=lambda o: o["index"])

        ours = _strip_for_compare(eng.observation(mover))
        theirs = _strip_for_compare(fr["obs"])
        d = first_divergence(theirs, ours)
        if d:
            report.divergence, report.kind, report.frame = d, "obs", k
            return report
        report.frames_green += 1
        if on_frame is not None:
            on_frame(k, eng.fork())

        choice = fr.get("choice")
        if choice is None or k == len(trace.frames) - 1:
            break   # final frame: nothing follows to verify — stepping it can demand
                    # randomness a truncated micro-trace never recorded

        # God-free look-reveal pre-binding: the NEXT frame's DECK->LOOKING moves are the deck-top
        # TRUTH, so the deck must be arranged to yield them in pop order BEFORE stepping.
        if fr.get("god") is None:
            nxt = trace.frames[k + 1]["obs"]

            # Adopt the NEXT frame's revealed deck order BEFORE the pose, so the option SET is
            # filtered over the true deck — a post-hoc index remap cannot fix a wrong SET.
            nxt_listing = (nxt.get("select") or {}).get("deck")
            cur_deck_indexed = (
                eng.gs.pending is not None
                and (eng.gs.pending.deck_listing is not None
                     or any(o.get("area") == int(AreaType.DECK)
                            for o in eng.gs.pending.options)))
            if nxt_listing and not cur_deck_indexed:
                nxt_mover = nxt["current"]["yourIndex"]
                serials = [c["serial"] for c in nxt_listing]
                nb = eng.gs.players[nxt_mover]
                ours_d = nb.deck
                if sorted(serials) != sorted(ours_d):
                    ours_ctr: dict[int, int] = {}
                    listing_ctr: dict[int, int] = {}
                    for s in ours_d:
                        ours_ctr[s] = ours_ctr.get(s, 0) + 1
                    for s in serials:
                        listing_ctr[s] = listing_ctr.get(s, 0) + 1
                    extra_deck = sorted(s for s in ours_ctr
                                        for _ in range(ours_ctr[s]
                                                       - listing_ctr.get(s, 0))
                                        if ours_ctr[s] > listing_ctr.get(s, 0))
                    extra_listing = sorted(s for s in listing_ctr
                                           for _ in range(listing_ctr[s]
                                                          - ours_ctr.get(s, 0))
                                           if listing_ctr[s] > ours_ctr.get(s, 0))
                    if (len(extra_deck) == len(extra_listing)
                            and all(s in nb.prize for s in extra_listing)):
                        for wrong, right in zip(extra_deck, extra_listing):
                            ours_d[ours_d.index(wrong)] = right
                            nb.prize[nb.prize.index(right)] = wrong
                if sorted(serials) == sorted(ours_d):
                    ours_d[:] = serials
                # residue: leave it — the next frame's compare reports the truth

            rec_moves: list[int] = []
            look_owner = -1
            for l in nxt.get("logs") or []:
                if (l.get("type") == int(LogType.MOVE_CARD)
                        and l.get("fromArea") == int(AreaType.DECK)
                        and l.get("toArea") == int(AreaType.LOOKING)
                        and l.get("serial") is not None):
                    rec_moves.append(l["serial"])
                    look_owner = l.get("playerIndex", -1)
            if rec_moves and look_owner in (0, 1):
                lb = eng.gs.players[look_owner]
                ok = True
                for r in rec_moves:
                    if r in lb.deck:
                        continue
                    if r in lb.prize:
                        swap = next((d for d in lb.deck if d not in rec_moves), None)
                        if swap is None:
                            ok = False
                            break
                        lb.prize[lb.prize.index(r)] = swap
                        lb.deck[lb.deck.index(swap)] = r
                    else:
                        ok = False    # not a deck reveal (or a real divergence —
                        break         # the next frame's compare will report it)
                if ok:
                    # RECORDED order: look_bind consumes these whichever deck end the op reads.
                    rnd.look_feed[look_owner] = list(rec_moves)

            # God-free mill pre-binding: the NEXT frame's DECK->DISCARD moves are the exact cards
            # a mill discards, so its damage scale counts the TRUE discarded energy.
            for l in nxt.get("logs") or []:
                if (l.get("type") == int(LogType.MOVE_CARD)
                        and l.get("fromArea") == int(AreaType.DECK)
                        and l.get("toArea") == int(AreaType.DISCARD)
                        and l.get("serial") is not None
                        and l.get("playerIndex") in (0, 1)):
                    rnd.mill_feed[l["playerIndex"]].append(l["serial"])

        twin = eng.fork() if fork_check else None
        try:
            eng.step(choice)
            if twin is not None:
                twin.step(choice)
        except Exception as e:  # noqa: BLE001 — any engine failure is the finding itself
            report.error = f"frame {k}: cgpy raised on recorded choice {choice}: {e!r}"
            report.kind, report.frame = "error", k
            return report
        finally:
            rnd.look_feed = {0: [], 1: []}   # a look/mill feed binds ONE step only
            rnd.mill_feed = {0: [], 1: []}
        if twin is not None:
            d = first_divergence(eng.god_frame(), twin.god_frame())
            if d is None and eng.gs.outbox != twin.gs.outbox:
                d = Divergence("$.outbox", eng.gs.outbox, twin.gs.outbox)
            if d is None:
                p, q = eng.gs.pending, twin.gs.pending
                if (p is None) != (q is None) or (p is not None and
                                                  (p.options, p.context, p.min_count,
                                                   p.max_count) != (q.options, q.context,
                                                                    q.min_count, q.max_count)):
                    d = Divergence("$.pending", p, q)
            if d is not None:
                report.error = f"frame {k}: fork diverged from the original after one step\n  {d}"
                report.kind, report.frame = "error", k
                return report

    return report
