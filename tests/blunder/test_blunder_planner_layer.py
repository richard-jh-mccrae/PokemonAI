"""Planner/Solver layer flags: live planned/lethal verdicts route corrections to code fixes.

A non-null ``planned`` (ADR-0031) / ``lethal`` (ADR-0030) in a Correction's embedded live trace
means that layer short-circuited scoring at the decision -- no weight or ``when()`` can fix it.
The pipeline surfaces the flags (proposal -> durable snapshot -> tune.py banner -> tagging shell)
so /blunder-buster routes these to planner.py / lethal.py. See .claude/skills/blunder-buster.
"""
import json

from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import build_correction
from train.blunder.decisions import iter_decisions
from train.tuner.io import write_proposals
from train.tuner.propose import propose_hypothesis

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"
PLANNED = {"step": [1], "goal": "ko_for_prizes", "why": "retreat->attach->KO"}
LETHAL = {"step": [3], "kind": "direct", "why": "attack wins"}


def _main():
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == "Main")


def _c(live_trace=None):
    return build_correction(_main(), source="own", agent="mega_starmie", correct=[4],
                            category="sequencing_error", rationale="r", live_trace=live_trace)


def test_proposal_carries_layer_flags():
    """REQ-BLUNDER-0016: a proposal derives planner_committed/lethal_locked from the live trace."""
    p = propose_hypothesis(_c({"chosen": [0], "planned": PLANNED, "lethal": None}))
    assert p.planner_committed and not p.lethal_locked
    q = propose_hypothesis(_c({"chosen": [0], "lethal": LETHAL}))
    assert q.lethal_locked and not q.planner_committed
    r = propose_hypothesis(_c(None))                       # no live trace -> both False
    assert not r.planner_committed and not r.lethal_locked


def test_proposals_snapshot_serializes_layer_flags(tmp_path):
    """REQ-BLUNDER-0016: the durable open[]/skipped[] snapshot carries the layer flags so
    /blunder-buster routes planner/solver-layer blunders straight from it."""
    p = propose_hypothesis(_c({"chosen": [0], "planned": PLANNED}))
    out = write_proposals(tmp_path / "m.json", "m", [p],
                          [(_c({"chosen": [0], "lethal": LETHAL}), "tactical")],
                          generated_at="2026-07-02T00:00:00")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["open"][0]["planner_committed"] is True
    assert data["open"][0]["lethal_locked"] is False
    assert data["skipped"][0]["lethal_locked"] is True
    assert data["skipped"][0]["planner_committed"] is False


def test_shell_ui_renders_live_layer_verdicts():
    """REQ-BLUNDER-0016: the tagging shell shows the live @T verdicts (lethal/planned) at the
    decision, so the human tags knowing which layer drove the shipped pick."""
    from train.blunder.shell import _SHELL_HTML
    assert "f.live" in _SHELL_HTML and 'class="live"' in _SHELL_HTML
    assert "L.planned" in _SHELL_HTML and "L.lethal" in _SHELL_HTML
    assert "planner drove this pick" in _SHELL_HTML        # the wrong-layer warning
