"""**The resolution-parity lane** — the recorded native engine as the answer key for a CHOICE node
(POC-T4/5, Issue #392; ADR-0121 decision 7).

A Deferred-Target Option resolves over two or three FURTHER selects, so `apply_parity`'s
next-frame reference cannot reach it. This lane walks each one past its follow-up selects to the
first settled frame, reads the target the trace records as taken, and diffs the synthesized board
against the recorded one on every homed zone.

Only the TAKEN branch is observable — the counterfactuals were never played — so this proves the
arithmetic and the space's membership, never that the enumeration is COMPLETE.

    python tools/train/choice_parity.py                 # every committed trace
    python tools/train/choice_parity.py --limit 25      # a subset, the shape CI runs
    python tools/train/choice_parity.py --kinds 12      # only `_RETREAT` steps
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _root in (REPO / "src", REPO / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

# The sibling lane is IMPORTED, never re-spelled: a second copy would let the two lanes report
# different numbers for one corpus.
from train.apply_parity import (TRACES, chosen_option, load,               # noqa: E402
                                offline_combat, zone_facts)
from common import board_choice, board_delta                               # noqa: E402
from common.state_model import StateModel                                  # noqa: E402

#: The deferred-target members this lane can read from a settled native board. Visible-discard fetch
#: predates this lane and has no new applier in this issue, so it remains outside this resolution set.
PARITY_KEYS = frozenset(set(board_choice.CHOICE_KINDS) | {
    "gust", "heal", "accel", "self_switch", board_choice.FETCH_IN_PLAY})

#: Compared as a MULTISET: nothing in `docs/rulebook.txt` orders a simultaneous discard, so the
#: engine's order is the recording policy's artifact. A WRONG card still fails; the multiset changes.
_ORDER_INSENSITIVE = frozenset({"my_discard_contents"})


def _multiset(value):
    out = []
    for item in value or ():
        out.extend(item if isinstance(item, (list, tuple)) else [item])
    return sorted(str(v) for v in out)


@dataclass
class Divergence:
    """One step where the choice node and the settled frame disagreed about a zone."""
    trace: str
    frame: int
    settled: int
    kind: object
    zone: str
    node_value: object
    engine_value: object

    def __str__(self) -> str:
        return (f"{self.trace} f{self.frame}->f{self.settled} kind={self.kind} zone={self.zone}\n"
                f"    node:   {self.node_value!r}\n    engine: {self.engine_value!r}")


@dataclass
class Report:
    traces: int = 0
    frames: int = 0
    #: Steps whose chosen option is a kind `board_choice` declares a CHOICE node — the population.
    choice_steps: int = 0
    #: …of which enumerated a space, found the taken instance in it, and matched on every homed zone.
    verified: int = 0
    #: …of which refused. Not a defect: the reasons ARE the modelling backlog.
    refused: int = 0
    #: …of which never reached a settled frame (the trace ends, or the turn passes mid-resolution).
    unsettled: int = 0
    #: …of which matched except on a `_ORDER_INSENSITIVE` zone's ORDER. Counted, never silent.
    order_only: int = 0
    #: …of which enumerated a space the TAKEN instance is not in — the SPACE is wrong, as against a
    #: divergence below, where the arithmetic is.
    unenumerated: list = field(default_factory=list)
    divergences: list = field(default_factory=list)
    refusal_reasons: dict = field(default_factory=dict)
    by_key: dict = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.divergences and not self.unenumerated

    def __str__(self) -> str:
        head = (f"{self.traces} traces / {self.frames} frames — {self.choice_steps} choice steps: "
                f"{self.verified} verified ({self.order_only} on a relaxed discard ORDER) · "
                f"{self.refused} refused · {self.unsettled} unsettled · "
                f"{len(self.unenumerated)} NOT ENUMERATED · {len(self.divergences)} DIVERGED")
        lines = [head]
        if self.by_key:
            lines.append("  per member: " + ", ".join(
                f"{key}: {row['verified']}v/{row['refused']}r/{row['unsettled']}u"
                for key, row in sorted(self.by_key.items(), key=lambda kv: str(kv[0]))))
        for miss in self.unenumerated[:10]:
            lines.append(f"  taken target not in the enumerated space: {miss}")
        for d in self.divergences[:20]:
            lines.append("  " + str(d))
        if len(self.divergences) > 20:
            lines.append(f"  … and {len(self.divergences) - 20} more")
        return "\n".join(lines)


def settled_frame(frames: list, start: int, seat: int):
    """None when the trace ends first or the turn passes mid-resolution; the caller reports that as
    ``unsettled`` rather than shrinking the denominator silently."""
    for j in range(start + 1, len(frames)):
        obs = frames[j].get("obs") or {}
        if ((obs.get("current") or {}).get("yourIndex")) != seat:
            return None                       # the turn passed — no same-orientation settled board
        if ((obs.get("select") or {}).get("context")) == board_delta.CONTEXT_MAIN:
            return j
    return None


def _serials(cards) -> list:
    return [(c or {}).get("serial") for c in (cards or ())]


def taken_retreat(before: dict, after: dict, seat: int):
    """``(discarded card indices, promoted bench index)`` in `board_choice.target_space` coordinates.
    Read by ``serial`` off the two observations: the ctx-30 select answers index a SHRINKING list."""
    def side(obs):
        players = ((obs.get("current") or {}).get("players")) or []
        return players[seat] if 0 <= seat < len(players) else None
    pre, post = side(before), side(after)
    if not pre or not post:
        return None
    a = next((b for b in (pre.get("active") or ()) if b), None)
    promoted = next((b for b in (post.get("active") or ()) if b), None)
    if not a or not promoted:
        return None
    bench = list(pre.get("bench") or ())
    index = next((i for i, b in enumerate(bench)
                  if b and b.get("serial") == promoted.get("serial")), None)
    if index is None:
        return None                           # the new Active did not come off the pre-state Bench
    # Indices are into the PRE-state list — the coordinate `target_space` enumerates in.
    landed = next((b for b in (post.get("bench") or ()) if b and b.get("serial") == a.get("serial")),
                  None)
    kept = set(_serials((landed or {}).get("energyCards")))
    discarded = tuple(i for i, c in enumerate(a.get("energyCards") or ())
                      if (c or {}).get("serial") not in kept)
    return (discarded, index)


def _side(obs: dict, seat: int):
    players = ((obs.get("current") or {}).get("players")) or []
    return players[seat] if 0 <= seat < len(players) else None


def _locate_serial(side: dict, serial):
    for area, zone in ((4, "active"), (5, "bench")):
        for index, body in enumerate((side or {}).get(zone) or ()):
            if body and body.get("serial") == serial:
                return area, index
    return None


def _taken_switch(before: dict, after: dict, seat: int, *, opponent: bool):
    target = 1 - seat if opponent else seat
    pre, post = _side(before, target), _side(after, target)
    active = next((b for b in (post or {}).get("active") or () if b), None)
    if not active:
        return None
    where = _locate_serial(pre, active.get("serial"))
    return where[1] if where and where[0] == 5 else None


def taken_gust(before: dict, after: dict, seat: int):
    return _taken_switch(before, after, seat, opponent=True)


def taken_self_switch(before: dict, after: dict, seat: int):
    return _taken_switch(before, after, seat, opponent=False)


def taken_heal(before: dict, after: dict, seat: int):
    pre, post = _side(before, seat), _side(after, seat)
    for area, zone in ((4, "active"), (5, "bench")):
        for index, body in enumerate((pre or {}).get(zone) or ()):
            if not body:
                continue
            later = next((b for b in (post or {}).get(zone) or ()
                          if b and b.get("serial") == body.get("serial")), None)
            if later and int(later.get("hp") or 0) > int(body.get("hp") or 0):
                return area, index
    return None


def _ids(cards):
    return [c.get("id") for c in cards or () if c and c.get("id") is not None]


def _new_ids(before, after):
    old = list(_ids(before))
    out = []
    for cid in _ids(after):
        if cid in old:
            old.remove(cid)
        else:
            out.append(cid)
    return out


def taken_accel(before: dict, after: dict, seat: int):
    pre, post = _side(before, seat), _side(after, seat)
    delivered = _new_ids((pre or {}).get("hand"), (post or {}).get("hand"))
    for area, zone in ((4, "active"), (5, "bench")):
        for index, body in enumerate((post or {}).get(zone) or ()):
            if not body:
                continue
            prior = _locate_serial(pre, body.get("serial"))
            if not prior:
                continue
            pre_zone = "active" if prior[0] == 4 else "bench"
            previous = ((pre or {}).get(pre_zone) or ())[prior[1]]
            attached = _new_ids(previous.get("energyCards"), body.get("energyCards"))
            if prior and len(attached) == 1 and len(delivered) == 1:
                return attached[0], delivered[0], prior[0], prior[1]
    return None


def taken_in_play_fetch(before: dict, after: dict, seat: int):
    pre, post = _side(before, seat), _side(after, seat)
    for area, zone in ((4, "active"), (5, "bench")):
        for index, body in enumerate((post or {}).get(zone) or ()):
            stack = body.get("preEvolution") or () if body else ()
            old = stack[-1] if stack else None
            where = _locate_serial(pre, (old or {}).get("serial"))
            if where:
                return body.get("id"), where[0], where[1]
    return None


#: Keyed like `board_choice`'s registry. A promoted member needs a settled-frame reader before it
#: can enter :data:`PARITY_KEYS`; no zero-population resolver can become a green gate silently.
TAKEN = {
    12: taken_retreat,
    "gust": taken_gust,
    "heal": taken_heal,
    "accel": taken_accel,
    "self_switch": taken_self_switch,
    board_choice.FETCH_IN_PLAY: taken_in_play_fetch,
}


def replay(path: Path, *, combat, kinds=None, report: Report | None = None) -> Report:
    report = report or Report()
    body = load(path)
    frames = body.get("frames") or []
    decks = (body.get("meta") or {}).get("decks") or [[], []]
    report.traces += 1
    report.frames += len(frames)
    for k in range(len(frames) - 1):
        option = chosen_option(frames[k])
        if not option:
            continue
        obs = frames[k]["obs"]
        seat = (obs.get("current") or {}).get("yourIndex", 0)
        if ((obs.get("select") or {}).get("context")) != board_delta.CONTEXT_MAIN:
            continue                          # not the MAIN menu — the node refuses it by contract
        deck = decks[seat] if seat < len(decks) else []
        pre = StateModel.build(obs, combat=combat, my_index=seat, deck=deck)
        try:
            key = board_choice.choice_key(pre, option, seat_index=seat)
        except board_delta.Unmodellable:
            continue
        if key not in PARITY_KEYS or (kinds and int(option.get("type", -1)) not in kinds):
            continue
        report.choice_steps += 1
        row = report.by_key.setdefault(key, {"population": 0, "verified": 0, "refused": 0,
                                             "unsettled": 0})
        row["population"] += 1
        j = settled_frame(frames, k, seat)
        if j is None:
            report.unsettled += 1
            row["unsettled"] += 1
            continue
        candidate = TAKEN[key](obs, frames[j]["obs"], seat)
        # ONE try around the whole synthesis: every refusal raised here is one
        # `board_choice.deferred_target` would raise for the same option, so none is a lane crash.
        try:
            space = board_choice.target_space(pre, option, seat_index=seat)
            if candidate is None:
                raise board_delta.Unmodellable(
                    "the settled frame does not describe a retreat this lane can key — no readable "
                    "Active either side, or the new Active did not come off the pre-state Bench")
            # Membership in the EQUIVALENCE, never the raw coordinates: which of eight identical
            # Energy cards the engine named is not a decision.
            taken_class = board_choice.candidate_class(pre, option, candidate, seat_index=seat)
            reachable = {board_choice.candidate_class(pre, option, c, seat_index=seat)
                         for c in space}
            # The taken candidate realised VERBATIM, so the surviving card order is the engine's own.
            after_obs, _fingerprint = board_choice.realise(pre, option, candidate, seat_index=seat)
        except board_delta.Unmodellable as gap:
            report.refused += 1
            row["refused"] += 1
            reason = str(gap).split(" — ")[0]
            report.refusal_reasons[reason] = report.refusal_reasons.get(reason, 0) + 1
            continue
        if taken_class not in reachable:
            report.unenumerated.append(
                f"{path.name} f{k}->f{j} kind={key} taken={candidate!r} class={taken_class!r} "
                f"space={len(space)}")
            continue
        ours = zone_facts(pre.rebuilt(
            after_obs, reuse_their_side=board_choice.CHOICE_REGISTRY[key].shares_opponent))
        theirs = zone_facts(StateModel.build(frames[j]["obs"], combat=combat, my_index=seat,
                                             deck=deck))
        bad, relaxed = [], False
        for zone, engine_value in theirs.items():
            if ours.get(zone) == engine_value:
                continue
            if zone in _ORDER_INSENSITIVE and _multiset(ours.get(zone)) == _multiset(engine_value):
                relaxed = True
                continue
            bad.append(zone)
        for zone in bad:
            report.divergences.append(Divergence(path.name, k, j, key, zone,
                                                 ours.get(zone), theirs[zone]))
        if not bad:
            report.verified += 1
            row["verified"] += 1
            report.order_only += int(relaxed)
    return report


def sweep(*, limit=None, kinds=None, combat=None, traces=None) -> Report:
    combat = combat or offline_combat()
    paths = list(traces) if traces is not None else sorted(TRACES.glob("*.trace.json.gz"))
    if limit:
        paths = paths[:limit]
    report = Report()
    for path in paths:
        replay(path, combat=combat, kinds=kinds, report=report)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=None, help="replay only the first N traces")
    ap.add_argument("--kinds", default=None,
                    help="comma-separated engine OptionType ints to restrict the sweep to")
    ap.add_argument("--backlog", action="store_true",
                    help="print the grouped refusal reasons (the modelling backlog)")
    args = ap.parse_args(argv)
    kinds = frozenset(int(k) for k in args.kinds.split(",")) if args.kinds else None
    report = sweep(limit=args.limit, kinds=kinds)
    print(report)
    if args.backlog:
        print("\nrefusal backlog (reason -> steps):")
        for reason, count in sorted(report.refusal_reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {count:6d}  {reason}")
    return 0 if report.clean else 1


if __name__ == "__main__":                                  # pragma: no cover — CLI
    raise SystemExit(main())
