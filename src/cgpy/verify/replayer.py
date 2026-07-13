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

    # GameState.coin_flip passes the flip OWNER's seat (checkup flips belong to the
    # condition owner — pinned collapse_9740 f17); the acting-seat fallback covers
    # legacy paths that flip without one.
    acting_seat: int = 0

    def coin(self, seat: int | None = None) -> bool:
        return self.coin_for(seat if seat is not None else self.acting_seat)


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


def replay(trace: Trace, *, compare_god: bool = True, fork_check: bool = False) -> ReplayReport:
    """Replay ``trace`` through cgpy. With ``fork_check`` (the M3 clone-safety gate), every
    recorded choice is ALSO applied to a fresh `Engine.fork()` of the live engine and the two
    resulting states must render identical god frames, outboxes and pending selects — proving
    a mid-cascade clone at every select of the game replays identically."""
    report = ReplayReport(frames_total=len(trace.frames))
    rnd = _TraceRandomness()
    deck0, deck1 = trace.decks

    # Pre-feed every mover window (draw identities/coins are consumed strictly in order,
    # and feeding ahead is safe: queues are per-seat FIFOs in chronological order).
    for fr in trace.frames:
        mover = fr["obs"]["current"]["yourIndex"]
        _feed_from_window(rnd, mover, fr["obs"].get("logs") or [])

    # Coins/draws: the god stream is authoritative when present — each event appears
    # exactly once, INCLUDING ones whose mover window falls past a truncated
    # micro-trace's end (coinfail_9200 f113 / tucktail_9521 f14: the last events never
    # reach the mover's next window).
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
        # God-free trace (cabt conversions): prize identities bind at TAKE time from
        # the owner's own PRIZE->HAND moves (from_cabt.py; the reveal-oracle path).
        for fr in trace.frames:
            mover = fr["obs"]["current"]["yourIndex"]
            for l in fr["obs"].get("logs") or []:
                if (l.get("type") == int(LogType.MOVE_CARD)
                        and l.get("playerIndex") == mover
                        and l.get("fromArea") == 6 and l.get("toArea") == 2
                        and l.get("serial") is not None):
                    rnd.prize_take_queue[mover].append(l["serial"])

    # Hand-pick channel (Psych Out family): a victim's forced hand exits — MOVE_CARD
    # out of HAND while the TURN belongs to their opponent — feed a per-victim FIFO in
    # chronological order (pinned psychout_9970 f21: no select, no reveal, just the
    # move log). Voluntary exits are always own-turn, so the turn gate excludes them;
    # setup-phase exits (mulligans, placements) precede the first TurnStart and are
    # skipped. God stream preferred (exactly-once, serials always visible); god-free
    # traces feed from the victim's OWN windows (their view always carries the serial),
    # with per-seat turn tracking since each seat's windows tile the game exactly once.
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
        else:
            # God-free: a revealed deck listing IS a reveal — adopt its order
            # (multiset-checked) so the rendered listing and later draws agree.
            listing = (fr["obs"].get("select") or {}).get("deck")
            if listing:
                serials = [c["serial"] for c in listing]
                ours = eng.gs.players[mover].deck
                if sorted(serials) != sorted(ours):
                    # Provisional-prize reconciliation (reveal-oracle, the prize_take
                    # rule applied at listing time): the facedown prize deal bound
                    # deck-top identities provisionally, so a listing that reveals the
                    # TRUE deck can name cards cgpy parked in the prize row — swap the
                    # differences pairwise (multiset-exact across deck+prizes). Any
                    # residue is a real divergence.
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
                    # the pose snapshotted the pre-adoption order — re-point the
                    # listing at the revealed truth and remap option deck-indices
                    # through serial identity (duplicates take positions in order)
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

        choice = fr.get("choice")
        if choice is None or k == len(trace.frames) - 1:
            break   # final frame: nothing follows to verify — stepping it can demand
                    # randomness a truncated micro-trace never recorded

        # God-free look-reveal pre-binding: if the NEXT recorded frame's own-window
        # logs show DECK->LOOKING moves (Pokégear-class look-at-top-N), those serials
        # are the deck-top truth — swap any provisionally prize-parked ones back and
        # arrange the deck top to yield them in pop order BEFORE stepping, so the
        # emitted MOVE_CARD logs, the looking zone and its options all bind right
        # (the draw/prize/listing reveal-oracle rule's fourth channel).
        if fr.get("god") is None:
            nxt = trace.frames[k + 1]["obs"]

            # Listing pre-adoption: a deck listing in the NEXT frame means the step
            # below poses a search over the deck — reconcile provisionally
            # prize-parked serials and adopt the revealed order BEFORE the pose, so
            # the option SET is filtered over the true deck (a post-hoc index remap
            # cannot fix a wrong set — kaggle 83692318 f6: prize-swapped serials made
            # Poké Pad offer supporters). Skipped when the CURRENT select is itself
            # deck-indexed (the answer below still resolves through those indices).
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
                    # feed identities in recorded order — the look op consumes them
                    # via rng.look_bind whichever deck end it reads (Dusk Ball reads
                    # the BOTTOM; Pokégear the top)
                    rnd.look_feed[look_owner] = list(rec_moves)

            # God-free mill pre-binding: the NEXT frame's own-window DECK->DISCARD
            # moves are the exact cards a top-of-deck mill discards (Hammer-lanche
            # 1046). Feed them per deck-owner so the mill binds native's true top-N
            # (and its damage scale counts the true discarded energy) — a god-free
            # shuffle otherwise leaves cgpy's own order, not native's. rng.mill_bind
            # swaps a provisionally prize-parked serial back into the deck.
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
