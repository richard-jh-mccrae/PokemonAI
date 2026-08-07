"""The beam-margin probe — where a Deferred-Target Option ranks at 1-ply ordering (Issue #392).

Measured: the ordering `state_value` produces over one frame's MAIN menu, twice — `apply_option`
unarmed (a retreat resolves to the allowance-only board, so its delta is the near-zero this exists to
delete) and armed (an Expectation scored by the **max** over its classes). **Not claimed: that this
is the composer's beam** — `rank` is a 1-ply position, and `k` is NOT derived, so the margin is a
CURVE whose stopping width IS the finding.

    python tools/train/probes/choice_beam.py [--k 4] [--frame f32] [--cost]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for _root in (REPO / "src", REPO / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from common import apply_option as ao                        # noqa: E402
from common import board_choice, board_expectation           # noqa: E402
from common.state_value import state_value                   # noqa: E402

#: The two acceptance frames — fixture and replaying agent, both NAMED. These committed fixtures
#: carry no agent field, and guessing it off the filename would break the moment one is renamed.
FRAMES = {
    "f32": ("dragapult_hammer_over_develop_f32.json", "dragapult_ex"),
    "f35": ("dp_hold_evolve_until_typed_ready_f35.json", "dragapult_ex"),
}

FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _load(name: str):
    """``(observation, Pilot)`` for a named acceptance frame; the Pilot resolves the ONE deployment PROFILE."""
    from train import tune                                # noqa: PLC0415
    fixture, agent = FRAMES[name]
    body = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    return body, tune._build_pilot(agent)[0]


def score_menu(model, options, *, expand: bool, effects=None):
    """``[(index, delta_or_None, shape)]`` — one 1-ply DELTA per option, in menu order. ``None`` is a
    REFUSAL and is KEPT. An `Expectation` scores by the **max** over its classes, never `.expected()`."""
    base = state_value(model)
    rows = []
    for i, option in enumerate(options or ()):
        if ao.is_terminal(option):
            rows.append((i, None, "terminal"))
            continue
        clauses_cover = None
        if effects is not None:
            card_id = _card_of(model, option)
            clauses_cover = effects.clauses_cover(card_id) if card_id else None
        result = ao.apply_option(model, option, clauses_cover=clauses_cover,
                                 expand_deferred_targets=expand)
        if ao.must_expand(result):
            rows.append((i, None, "refused"))
        elif isinstance(result, ao.Expectation):
            rows.append((i, max(state_value(c.model) for c in result.classes) - base,
                         f"choice[{len(result.classes)}]"))
        else:
            rows.append((i, state_value(ao.require_model(result)) - base, "point"))
    return rows


def _card_of(model, option):
    from common.option_equivalence import AREA_HAND        # noqa: PLC0415
    if "index" not in option or option.get("area") not in (None, AREA_HAND):
        return None
    players = ((model.source_obs.get("current") or {}).get("players")) or []
    seat = int(getattr(model, "my_index", 0))
    hand = (players[seat] or {}).get("hand") or () if seat < len(players) else ()
    index = option.get("index")
    return (hand[index] or {}).get("id") if isinstance(index, int) and 0 <= index < len(hand) \
        else None


def margin_report(rows, target_index: int, *, k: int) -> dict:
    """One option's ORDERING RANK relative to ``k``, and its score margin to the k-th candidate. A refused
    option sorts to the top: `must_expand` makes a refusal the always-expand path, never pruned."""
    scored = sorted(((s, i) for i, s, _shape in rows if s is not None), reverse=True)
    order = [i for _s, i in scored]
    rank = order.index(target_index) + 1 if target_index in order else None
    kth = scored[k - 1][0] if len(scored) >= k else None
    mine = next((s for i, s, _shape in rows if i == target_index), None)
    return {"rank": rank, "scored": len(order),
            "refused": sum(1 for _i, s, sh in rows if s is None and sh == "refused"),
            "terminal": sum(1 for _i, _s, sh in rows if sh == "terminal"),
            "k": k, "delta": mine, "kth_delta": kth,
            "margin_to_kth": None if (mine is None or kth is None) else mine - kth,
            "survives_k": None if rank is None else rank <= k}


def probe(name: str, *, k: int = 3) -> dict:
    """One frame, both orderings, with the retreat's rank and margin under each."""
    from common.state_model import StateModel               # noqa: PLC0415

    body, pilot = _load(name)
    obs = body["obs"]
    options = ((obs.get("select") or {}).get("option")) or []
    model = StateModel.build(obs, combat=pilot.combat, deck=list(pilot.deck or ()))
    retreat = next((i for i, o in enumerate(options)
                    if board_choice.has_deferred_target(model, o, seat_index=model.my_index)), None)
    out = {"frame": name, "key": body.get("frame_key"), "menu": len(options),
           "correct": body.get("correct"), "deferred_target_option": retreat}
    if retreat is None:
        return out
    for label, expand in (("unexpanded", False), ("expanded", True)):
        rows = score_menu(model, options, expand=expand, effects=pilot.combat.effects)
        out[label] = margin_report(rows, retreat, k=k)
        out[label]["shape"] = next(sh for i, _s, sh in rows if i == retreat)
        # The margin at EVERY width the menu can support, not only the `k` handed in: no issue derives
        # a width, so one figure would report the caller's choice as a property of the frame.
        out[label]["margin_by_k"] = {
            width: margin_report(rows, retreat, k=width)["margin_to_kth"]
            for width in range(1, out[label]["scored"] + 1)}
    return out


def cost_report(name: str) -> dict:
    """The expansion's cost in the units `board_expectation.BRANCH_CAP`'s own derivation uses — that
    header's figures are the yardstick. Per frame, because the CLASS COUNT is the board's property."""
    from common.state_model import StateModel               # noqa: PLC0415

    body, pilot = _load(name)
    obs = body["obs"]
    options = ((obs.get("select") or {}).get("option")) or []
    model = StateModel.build(obs, combat=pilot.combat, deck=list(pilot.deck or ()))
    retreat = next((i for i, o in enumerate(options)
                    if board_choice.has_deferred_target(model, o, seat_index=model.my_index)), None)
    if retreat is None:
        return {"frame": name, "deferred_target_option": None}
    started = time.perf_counter()
    expectation = board_choice.deferred_target(model, options[retreat])
    built_ms = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    for klass in expectation.classes:
        state_value(klass.model)
    leaves_ms = (time.perf_counter() - started) * 1000.0
    classes = len(expectation.classes)
    return {"frame": name, "classes": classes, "truncated": expectation.truncated,
            "cap": board_expectation.BRANCH_CAP,
            "space": len(board_choice.target_space(model, options[retreat],
                                                   seat_index=model.my_index)),
            "enumerate_ms": round(built_ms, 2), "leaves_ms": round(leaves_ms, 2),
            "ms_per_leaf": round(leaves_ms / classes, 2) if classes else None,
            "extra_leaves_vs_point": classes - 1}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--k", type=int, default=3, help="beam width the margin is reported against")
    ap.add_argument("--frame", default=None, choices=sorted(FRAMES), help="one frame only")
    ap.add_argument("--cost", action="store_true", help="report the expansion's leaf cost instead")
    args = ap.parse_args(argv)
    names = [args.frame] if args.frame else sorted(FRAMES)
    for name in names:
        print(json.dumps(cost_report(name) if args.cost else probe(name, k=args.k), indent=2))
    return 0


if __name__ == "__main__":                                  # pragma: no cover — CLI
    raise SystemExit(main())
