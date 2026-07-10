"""ADR-0050 Phase 2(A) — backfill a captured frame's engine seed + exact prize split from its replay,
so a single-frame correction fixture becomes cascade-ready. Offline: (1) content-joins the
seed-stripped agent obs to the step observation carrying ``search_begin_input`` (the seed lives on the
step obs, NOT the film obs the correction stores), and (2) replays the seat's history through
``OwnCardModel`` for the exact ``own_prizes``.

Ground truth = the committed ``match-replay.json`` full-information film, seat 0 at step 6: an anchored
frame that also carries a seed. The prize multiset is read from the film (independent of how backfill
computes it), so the assertion is a spec, not a recomputation.
"""
import copy
import json
from pathlib import Path

import pytest

from train.backfill_seed import backfill_seed

REPO = Path(__file__).resolve().parents[2]
_REPLAY = REPO / "tests" / "fixtures" / "match-replay.json"
_STEP = 6
_GT_PRIZES = {4: 3, 269: 1, 271: 1, 1086: 1}   # seat-0 prizes from the full-info film at step 6


def _replay():
    return json.loads(_REPLAY.read_text(encoding="utf-8"))


def _seat0_step_obs(replay, step):
    for s in replay["steps"]:
        for a in s:
            o = a.get("observation") or {}
            if (isinstance(o, dict) and isinstance(o.get("current"), dict)
                    and o["current"].get("yourIndex") == 0 and o.get("step") == step):
                return o
    raise AssertionError(f"no seat-0 step-{step} observation")


def _stripped(replay, step):
    o = copy.deepcopy(_seat0_step_obs(replay, step))
    o.pop("search_begin_input", None)
    o.pop("own_prizes", None)
    return o


@pytest.mark.req("REQ-LETHAL-SEED-0002")
def test_backfill_restores_the_seed_by_content_join():
    """The seed is recovered by joining the correction's (seed-stripped) obs to the step observation
    with the SAME select+current — proving the join lands on the right frame, not a neighbour."""
    replay = _replay()
    want_sbi = _seat0_step_obs(replay, _STEP)["search_begin_input"]
    out = backfill_seed(_stripped(replay, _STEP), replay)
    assert out["search_begin_input"] == want_sbi


@pytest.mark.req("REQ-LETHAL-SEED-0002")
def test_backfill_attaches_the_exact_prize_split():
    """own_prizes is the EXACT prize multiset from replaying the seat's history — it must equal the
    full-info film's actual seat-0 prizes (the deck/prize split the exact seeding then consumes)."""
    out = backfill_seed(_stripped(_replay(), _STEP), _replay())
    assert out["own_prizes"] == _GT_PRIZES
