"""`train.blunder.off_policy` — is this follow-up frame gradeable at all? (Issue #412, ADR-0123).

A follow-up select is gradeable only if the decision that opened it was correct. `candidates`
is the mechanical scan and `RULINGS` is the human's verdict on each candidate. Every census
assertion below is paired with its POSITIVE CONTROL."""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder import off_policy as op  # noqa: E402


# ── synthetic records ────────────────────────────────────────────────────────────────────────────


@dataclass
class FakeCorrection:
    agent: str = "mega_starmie"
    episode_id: int | None = 1
    decision: dict = field(default_factory=lambda: {"frame": 10, "turn": 3})
    obs: dict = field(default_factory=lambda: {"select": {"context": 7}})
    chosen: list = field(default_factory=lambda: [0])
    correct: list = field(default_factory=lambda: [1])
    chosen_label: str = "played"
    correct_label: str = "should"
    category: str = "wasted_resource"
    rationale: str = ""


def _rec(**kw) -> FakeCorrection:
    ctx = kw.pop("ctx", 7)
    frame = kw.pop("frame", 10)
    turn = kw.pop("turn", 3)
    rec = FakeCorrection(**kw)
    rec.decision = {"frame": frame, "turn": turn}
    rec.obs = {"select": {"context": ctx}} if ctx is not None else {}
    return rec


# ── the mechanical scan ──────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-OFFPOLICY-0001")
def test_an_earlier_ruled_decision_in_the_same_turn_is_a_CANDIDATE():
    follow_up = _rec(frame=10, turn=3)
    opener = _rec(frame=8, turn=3, ctx=0)
    by_ep = op.episode_index([follow_up, opener])
    found = op.candidates(follow_up, by_ep)
    assert [c.frame for c in found] == [8]
    assert found[0].context == 0


@pytest.mark.req("REQ-OFFPOLICY-0001")
def test_a_LATER_frame_and_a_DIFFERENT_turn_are_not_predecessors():
    """The doctrine is about what opened THIS select. A later frame cannot have opened it, and a
    different turn is `retest_span`'s across-turn job (ADR-0049), not this one's."""
    follow_up = _rec(frame=10, turn=3)
    by_ep = op.episode_index([follow_up, _rec(frame=12, turn=3, ctx=0),
                              _rec(frame=8, turn=2, ctx=0)])
    assert op.candidates(follow_up, by_ep) == []


@pytest.mark.req("REQ-OFFPOLICY-0002")
def test_an_ENDORSEMENT_predecessor_is_not_a_blunder():
    follow_up = _rec(frame=10, turn=3)
    endorsement = _rec(frame=8, turn=3, ctx=0, chosen=[2], correct=[2])
    assert op.candidates(follow_up, op.episode_index([follow_up, endorsement])) == []

    blunder = _rec(frame=8, turn=3, ctx=0, chosen=[2], correct=[3])
    assert [c.frame for c in
            op.candidates(follow_up, op.episode_index([follow_up, blunder]))] == [8]


@pytest.mark.req("REQ-OFFPOLICY-0002")
def test_an_endorsement_is_compared_as_a_SET_not_a_sequence():
    """`correct` order was never ruled on (ADR-0086), so `[1, 4]` and `[4, 1]` are one ruling."""
    assert op.endorses_the_play(_rec(chosen=[4, 1], correct=[1, 4]))
    assert not op.endorses_the_play(_rec(chosen=[4, 1], correct=[1, 5]))


@pytest.mark.req("REQ-OFFPOLICY-0003")
def test_a_NULL_episode_asserts_no_predecessor_relation_at_all():
    """Engine-parity captures carry no episode; keyed `(agent, None)` they all collide into one bucket."""
    follow_up = _rec(frame=100, turn=19, episode_id=None, ctx=17)
    other = _rec(frame=82, turn=19, episode_id=None, ctx=17, chosen=[0], correct=[1])
    assert op.candidates(follow_up, op.episode_index([follow_up, other])) == []

    real = _rec(frame=100, turn=19, episode_id=77, ctx=17)
    real_other = _rec(frame=82, turn=19, episode_id=77, ctx=17, chosen=[0], correct=[1])
    assert op.candidates(real, op.episode_index([real, real_other])) != []


# ── the scan proposes; only a human disposes ─────────────────────────────────────────────────────


@pytest.mark.req("REQ-OFFPOLICY-0004")
def test_an_unruled_candidate_is_UNRULED_and_never_OFF_POLICY():
    follow_up = _rec(frame=10, turn=3)
    by_ep = op.episode_index([follow_up, _rec(frame=8, turn=3, ctx=0)])
    assert op.classify(follow_up, by_ep) == op.UNRULED
    assert op.reasons(follow_up, by_ep)          # reported, never silently dropped


@pytest.mark.req("REQ-OFFPOLICY-0004")
def test_a_frame_with_no_candidate_is_GRADEABLE():
    follow_up = _rec(frame=10, turn=3)
    assert op.classify(follow_up, op.episode_index([follow_up])) == op.GRADEABLE
    assert op.reasons(follow_up, op.episode_index([follow_up])) == []


@pytest.mark.req("REQ-OFFPOLICY-0005")
def test_a_ruled_GRADEABLE_frame_reports_NO_reasons_despite_its_candidates(monkeypatch):
    follow_up = _rec(frame=10, turn=3)
    by_ep = op.episode_index([follow_up, _rec(frame=8, turn=3, ctx=0)])
    monkeypatch.setitem(op.RULINGS, op.ruling_key(follow_up),
                        op.Ruling(op.GRADEABLE, "orthogonal: the predecessor touches no named fact"))
    assert op.candidates(follow_up, by_ep), "the candidate must still be THERE — only the verdict moves"
    assert op.classify(follow_up, by_ep) == op.GRADEABLE
    assert op.reasons(follow_up, by_ep) == []


@pytest.mark.req("REQ-OFFPOLICY-0005")
def test_a_ruling_is_honoured_on_a_frame_the_SCAN_cannot_see():
    """The ledger is keyed on the FRAME, not on a candidate, so a ruling needs no detectable predecessor."""
    key = ("mega_lucario", 84889011, 7)
    assert op.RULINGS[key].verdict == op.OFF_POLICY
    ghost = _rec(agent="mega_lucario", episode_id=84889011, frame=7, turn=1)
    assert op.candidates(ghost, op.episode_index([ghost])) == [], "nothing for the scan to find"
    assert op.classify(ghost, op.episode_index([ghost])) == op.OFF_POLICY


# ── the live corpus ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def corpus():
    from train.blunder.store import DEFAULT_ROOT, load_corrections
    return load_corrections(DEFAULT_ROOT)


@pytest.mark.req("REQ-OFFPOLICY-0006")
def test_the_positive_control_still_fires_on_the_ctx7_base(corpus):
    """Counts CANDIDATES, not verdicts: a verdict-keyed control fades to zero exactly as review succeeds."""
    control = op.control(corpus)
    assert control["population"] >= 30, "the ctx-7 base Issue #412 ruled on must still be readable"
    assert control["healthy"], (
        "the scan fires on NO ctx-7 frame — the instrument is broken, so every census number it "
        "reports is an artifact rather than a finding")
    assert control["flagged"] >= 14


@pytest.mark.req("REQ-OFFPOLICY-0006")
def test_every_non_MAIN_context_has_been_censused_and_nothing_is_left_UNRULED(corpus):
    """A new UNRULED frame failing here is INTENDED — it routes to `off_policy_census.py --review`."""
    census = op.census(corpus)
    assert census, "no non-MAIN frames found at all — the census is reading nothing"
    assert set(census) >= {7, 15, 8, 21}, "the four largest non-MAIN populations must be censused"
    assert 0 not in census, "MAIN is not a follow-up; nothing opened it"

    unruled = {ctx: row["unruled"] for ctx, row in census.items() if row["unruled"]}
    assert not unruled, (
        f"{unruled} — a flagged follow-up frame nobody has ruled is grading on an unexamined "
        f"premise. Rule it: `python tools/train/off_policy_census.py --review`")


@pytest.mark.req("REQ-OFFPOLICY-0006")
def test_the_dependency_test_kept_more_than_half_the_flagged_frames(corpus):
    """An inequality, not a pair: the corpus grows, and pinned counts would fail on the next Correction."""
    census = op.census(corpus)
    flagged = sum(row["candidates"] for row in census.values())
    off = sum(row["off_policy"] for row in census.values())
    assert flagged >= 30, "the naive same-turn scan must still flag the population it flagged"
    assert off < flagged, "no candidate was ruled gradeable — the dependency test is a no-op"
    assert off <= flagged // 2, (
        f"{off}/{flagged} candidates ruled off-policy — the dependency test has drifted back "
        f"towards the naive same-turn rule it replaced")


@pytest.mark.req("REQ-OFFPOLICY-0007")
def test_every_ruling_names_a_real_frame_and_carries_a_reason(corpus):
    live = {op.ruling_key(c) for c in corpus}
    orphans = sorted(k for k in op.RULINGS if k not in live)
    assert not orphans, f"{orphans} rule on no committed Correction — re-key or delete them"

    assert all(r.verdict in (op.OFF_POLICY, op.GRADEABLE) for r in op.RULINGS.values())
    thin = sorted(k for k, r in op.RULINGS.items() if len(r.reason.split()) < 8)
    assert not thin, f"{thin} carry no reason a later reader could check the ruling against"


@pytest.mark.req("REQ-OFFPOLICY-0007")
def test_a_ruling_only_ever_addresses_a_FOLLOW_UP_frame(corpus):
    by_key = {op.ruling_key(c): c for c in corpus}
    main = sorted(k for k in op.RULINGS if k in by_key and not op.is_follow_up(by_key[k]))
    assert not main, f"{main} rule a MAIN decision, which no earlier play opened"


# ── the gates consume it, and it never reaches a verdict ─────────────────────────────────────────


@pytest.mark.req("REQ-OFFPOLICY-0008")
def test_the_gate_join_resolves_to_real_frame_keys():
    from train.gates import off_policy_frames

    joined = off_policy_frames()
    assert len(joined) == sum(1 for r in op.RULINGS.values() if r.verdict == op.OFF_POLICY)
    assert all("|decision|" in key for key in joined), "these are all decision-scope frames"
    assert all(reason for reason in joined.values())


@pytest.mark.req("REQ-OFFPOLICY-0008")
def test_neither_gate_verdict_consults_the_off_policy_set():
    """Issue #412 decision 3: flag and warn, never drop. Asserted structurally, because "does the
    verdict consult it" cannot be seen in a count."""
    import inspect

    from train import gates

    for fn in (gates.decision_gate_verdict, gates.discrimination_gate_verdict):
        source = inspect.getsource(fn)
        assert "off_policy" not in source, (
            f"{fn.__name__} consults the off-policy set — Issue #412 ruled it reports only")


@pytest.mark.req("REQ-OFFPOLICY-0008")
def test_the_readout_is_silent_at_zero_and_names_only_the_frames_that_MOVED(capsys):
    from train.gates import print_off_policy_readout

    ledger = {"ep|0|decision|9": "the search should not have been played",
              "ep|0|decision|31": "the recipient set moves under the correct line"}

    print_off_policy_readout(ledger, present=[])
    assert capsys.readouterr().out == "", "a clean run must print a clean report"

    print_off_policy_readout(ledger, present=list(ledger), moved=[])
    tally_only = capsys.readouterr().out
    assert "OFF-POLICY (2)" in tally_only
    assert "MOVED" not in tally_only, "nothing moved — the actionable section must stay closed"

    print_off_policy_readout(ledger, present=list(ledger), moved=["ep|0|decision|9"])
    moved = capsys.readouterr().out
    assert "1 of them MOVED" in moved
    assert "ep|0|decision|9" in moved
    assert "ep|0|decision|31" not in moved.split("MOVED", 1)[1], (
        "a frame that did not move must not appear in the actionable list")


@pytest.mark.req("REQ-OFFPOLICY-0008")
def test_the_DISCRIMINATION_gate_has_no_off_policy_exposure_today_and_this_is_a_tripwire():
    """The silence is structural: the leaf population is all MAIN and off-policy frames are non-MAIN.
    A TRIPWIRE, not a certificate — if it fails, check the readout fires before deleting it."""
    import json

    from train.blunder.store import DEFAULT_ROOT, load_corrections
    from train.gates import _scorable, correction_frame_key, off_policy_frames, rows_by_key

    joined = off_policy_frames()
    leaf = json.loads((REPO / "data" / "leaf_lab" / "baseline.json").read_text(encoding="utf-8"))
    leaf_rows = rows_by_key(leaf, keep=_scorable)
    assert leaf_rows, "the leaf baseline is unreadable — this proves nothing about the gate"

    contexts = {op.select_context(c) for c in load_corrections(DEFAULT_ROOT)
                if correction_frame_key(c) in leaf_rows}
    assert contexts <= {op._CONTEXT_MAIN}, (
        f"the leaf population now admits {sorted(contexts - {op._CONTEXT_MAIN})} — a non-MAIN "
        f"context. Check that `print_off_policy_readout` fires in the leaf gate before touching "
        f"this assertion")
    assert not (set(leaf_rows) & set(joined))

    decider = json.loads((REPO / "data" / "decider_lab" / "baseline.json").read_text(encoding="utf-8"))
    assert set(rows_by_key(decider)) & set(joined), (
        "the join is empty against the Decision Gate's baseline too — `off_policy_frames` is "
        "broken, so the leaf reading above is an artifact rather than a finding")


@pytest.mark.req("REQ-OFFPOLICY-0008")
def test_a_moved_key_that_is_not_off_policy_is_never_named(capsys):
    from train.gates import print_off_policy_readout

    print_off_policy_readout({"ep|0|decision|9": "ruled off-policy"},
                             present=["ep|0|decision|9"], moved=["ep|0|decision|55"])
    out = capsys.readouterr().out
    assert "OFF-POLICY (1)" in out
    assert "ep|0|decision|55" not in out
    assert "MOVED" not in out
