"""**The beam-margin probe** — where a Deferred-Target Option ranks at 1-ply ordering, unexpanded and
expanded, and what that costs (POC-T4/5, Issue #392).

Issue #263 § *Beam-quality package* item 3 asks for **margin telemetry**: for a named line, its rank
at 1-ply ordering relative to the beam width `k`, and its score margin to the k-th candidate. This is
that instrument, pointed at the two frames Issue #263's own acceptance corpus is built on:

* **f32** — `dragapult_hammer_over_develop_f32.json`, frame ``85046350|0|decision|32``, rationale
  `docs/plans/turn-planner-retreat-to-item-lock-wall.md`;
* **f35** — `dp_hold_evolve_until_typed_ready_f35.json`, frame ``86091435|0|decision|35``, which
  Issue #291's closeout rules *"the SAME class"*.

Both are retreat-to-wall lines. The retired `retreat-to-wall-the-line` +30 rung existed precisely
because the flat-scored world could not otherwise reach them.

## What is measured, and what is NOT claimed

**Measured:** the ordering `state_value` produces over one frame's MAIN menu, twice — once with
`apply_option` unarmed (a retreat resolves to `board_delta._retreat`'s allowance-only board, so its
delta is the near-zero this issue exists to delete) and once armed
(``expand_deferred_targets=True``, so a retreat resolves to a `common.board_choice` Expectation and
its score is the **max** over the classes, which is the choice-node reading `Expectation.expected`'s
own docstring names).

**Not claimed: that this is the composer's beam.** Issue #385 owns the beam and does not exist yet;
`rank` here is the position in a 1-ply ordering, which is the quantity Issue #263 says `k` is applied
to. When the composer lands, its beam consumes this same ordering — so a rank of 1 means the line
survives any `k >= 1`, and that IS the acceptance question. Reporting it as *ordering rank* rather
than *beam rank* keeps the two apart.

## Running it

    python tools/train/probes/choice_beam.py                 # both acceptance frames
    python tools/train/probes/choice_beam.py --k 4           # margin against a different width
    python tools/train/probes/choice_beam.py --cost          # the expansion's leaf-evaluation cost
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

#: The two acceptance frames — fixture and replaying agent, both NAMED rather than sampled or
#: inferred. The agent is spelled out because these committed fixtures carry `obs` / `chosen` /
#: `correct` and no agent field (`tests/strategy/test_blunder_20260710_split_fixes.py` hardcodes it
#: the same way); guessing it off the filename would break the moment a fixture is renamed.
FRAMES = {
    "f32": ("dragapult_hammer_over_develop_f32.json", "dragapult_ex"),
    "f35": ("dp_hold_evolve_until_typed_ready_f35.json", "dragapult_ex"),
}

FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _load(name: str):
    """``(observation, Pilot)`` for one named acceptance frame.

    The Pilot comes from `tune._build_pilot`, which resolves the ONE deployment PROFILE (ADR-0055)
    rather than a hand-kept kill-switch mirror — a probe that built its own would measure a policy no
    agent ships. Imported lazily because it maps the native library."""
    from train import tune                                # noqa: PLC0415
    fixture, agent = FRAMES[name]
    body = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    return body, tune._build_pilot(agent)[0]


def score_menu(model, options, *, expand: bool, effects=None):
    """``[(index, delta_or_None, shape)]`` — one 1-ply DELTA per option, in menu order.

    The delta, not the absolute score, because that is what Issue #263 § *The ordering heuristic*
    ranks by: *"apply the single option through the seam, evaluate `state_value` on the result, rank
    by that delta."* It is also the quantity the defect is about — an unexpanded retreat's delta is
    the retreat allowance bit alone, and a near-zero there means *never explored*.

    ``None`` is a REFUSAL, and it is kept rather than dropped: Issue #263 makes a refusal a one-action
    terminal candidate that is *ranked* (so it costs a leaf) and never transitioned through, so an
    ordering that silently omitted refusals would report a narrower menu than the composer sees.

    An `Expectation` is scored by the **max** over its classes for a choice node — never
    ``.expected()``, which is the availability-weighted average and a strict lower bound. That
    distinction is the whole reason this probe exists: averaging over decisions the player gets to
    PICK would price the expansion at its mean and leave the retreat looking mediocre rather than
    unexplored."""
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
    """Issue #263 § *Beam-quality package* item 3, for one option: its ORDERING RANK relative to ``k``
    and its score margin to the k-th candidate.

    A refused option sorts to the top (rank 1 among refusals), because `must_expand` makes a refusal
    the always-expand path — it has no *estimate*, not no *value*, and the composer explores it rather
    than pruning it. So a refusal is never "pruned"; what this reports for the unexpanded retreat is
    the position of a real, scored, near-zero number."""
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
    return out


def cost_report(name: str) -> dict:
    """The expansion's cost, in the units `board_expectation.BRANCH_CAP`'s own derivation uses.

    That header's measured figures are the yardstick, and they are the ones to compare against —
    **not** the stale 6.4 ms / 79 ms in Issue #392's original body::

        state_value leaf:          median 2.41 ms · P95 4.46 ms   (371 scored frames)
        post-OEC menu width:       P50 6 · P95 12
        derived per-decision P95:  12 x 4.46 = 53.5 ms            (leaf evaluations only)
        grader per-decision floor: >= 3.0 s                       (P95 137 decisions/match)

    A choice node costs ``len(classes)`` leaf evaluations where a point transition costs one, capped
    at :data:`~common.board_expectation.BRANCH_CAP`, so the worst case a decision holding one
    expanded option can reach is the same ``(menu - 1 + cap) x leaf`` bound that module derives for a
    chance node. Reported per frame rather than asserted, because a wall-clock number is a property of
    whoever ran it last while the CLASS COUNT is a property of the board."""
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
