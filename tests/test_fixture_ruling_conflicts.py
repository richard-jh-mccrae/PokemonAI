"""**No two committed fixtures may rule ONE frame differently** — `tests/fixtures/corrections/`
checked straight off the filesystem.

Written 2026-08-06, after `85164605|1|decision|41` was found ruled `[3]` by one fixture and `[4]` by
another with nothing anywhere reporting it. The failure mode is that a disagreement is *silent*:
`gates.iter_keyed_fixtures` walks `sorted(glob("*.json"))`, and `composer_lab.fixture_rulings` used to
flatten the walk with ``out[key] = ...``, so the winner was whichever FILENAME sorted last —
"ms_prefer_cheap..." beat "ms_item_over...", and every Issue #400 measurement graded that frame
against a claim the Correction record does not make.

**Only DISAGREEING duplicates are rejected. Sharing a frame key is legal and load-bearing**, and that
is not a judgement call made here — `gates.claim_agreement`'s own docstring rules it: *"Several
fixtures may share one key — legal and load-bearing — so each is judged independently."* Five keys
are duplicated with AGREEING claims (`86091435|0|decision|35`, `84071010|0|decision|64`,
`81904064|0|decision|44`, `85163079|0|decision|51`, `85163634|1|decision|17`) and every one is a
deliberate pairing of a named behavioural fixture with its `*_t3holdout_*` sibling. Rejecting those
would delete a real convention to catch a real bug, so the test rejects exactly the bug.

A declared ADR-0082 divergence does **not** exempt a fixture here, and that distinction is the whole
point. `claim_agreement` asks *"does this fixture disagree with the RECORD, undeclared?"* and a
declared divergence is a legitimate answer to it. This asks a different question — *"do two fixtures
disagree with EACH OTHER?"* — and a declaration cannot settle that, because both fixtures may be
individually well-formed while the machinery can still only carry one ruling per key.

These are cheap structural checks, not a review of fixture content. Prior art for the style:
`tests/test_adr_index.py`, a repo-shape invariant asserted straight off the filesystem after a
duplicate ADR number sat unnoticed for five days — including its exemption-as-DATA convention, so a
NEW conflict fails this test instead of joining a silent backlog.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_REPO / "tools"), str(_REPO / "src")]

#: Frame keys whose fixtures are KNOWN to disagree, each with the reason it is owed rather than
#: forgotten. Declared as data so a NEW conflict fails this test instead of joining a silent
#: backlog — `test_adr_index.py::_INDEX_EXEMPT`'s convention, and for the same reason. Emptying this
#: needs a developer ruling on the frame, not a code change.
#:
#: **Currently EMPTY, and that is a result rather than a default.** Its one entry —
#: `85164605|1|decision|41` — was ruled by the developer on 2026-08-06 to `[4]`, the free
#: direct-evolve, and both fixtures were reconciled to it. The list is kept because the mechanism it
#: guards is permanent even when the backlog is not.
_CONFLICT_EXEMPT: dict[str, str] = {}


def _claims_by_key() -> dict:
    """``{frame key: {claim tuple: [fixture names]}}`` over the committed fixture store.

    Read through `gates.iter_keyed_fixtures` — *"THE one corpus walk"* — rather than a second glob,
    so this test cannot drift from what the graders actually see (ADR-0087)."""
    from train.gates import iter_keyed_fixtures
    out: dict = {}
    for path, _fx, key, claims in iter_keyed_fixtures():
        if claims.decision and claims.decision.correct:
            out.setdefault(key, collections.defaultdict(list))[
                tuple(claims.decision.correct)].append(path.name)
    return out


def test_no_two_fixtures_rule_one_frame_DIFFERENTLY():
    """The invariant. Duplicated keys are fine; CONTRADICTORY ones are not."""
    conflicts = {key: dict(by_claim) for key, by_claim in _claims_by_key().items()
                 if len(by_claim) > 1 and key not in _CONFLICT_EXEMPT}
    assert not conflicts, (
        "two committed fixtures rule one frame differently, and every consumer that flattens the "
        "corpus walk into a dict will resolve it by FILENAME:\n"
        + "\n".join(f"  {key}\n" + "\n".join(f"    correct={list(c)}  <- {', '.join(sorted(n))}"
                                             for c, n in sorted(by_claim.items()))
                    for key, by_claim in sorted(conflicts.items()))
        + "\n\nRule the frame and reconcile to one claim, or add it to `_CONFLICT_EXEMPT` with the "
          "reason it is owed.")


@pytest.mark.parametrize("key", sorted(_CONFLICT_EXEMPT))
def test_every_exemption_still_names_a_REAL_conflict(key):
    """The exemption list is not a place to park a stale entry. A key that no longer conflicts — the
    fixtures reconciled, or one deleted — must be removed, or the list quietly grants immunity to a
    frame_key that could later collide again for a different reason."""
    by_claim = _claims_by_key().get(key)
    assert by_claim is not None and len(by_claim) > 1, (
        f"{key} is exempted as a known conflict but no longer has one — delete its "
        f"`_CONFLICT_EXEMPT` entry.\n  reason on file: {_CONFLICT_EXEMPT[key]}")


def _write_fixture(directory, name, frame_key, correct):
    """One minimal keyed fixture — `iter_keyed_fixtures` needs only `frame_key` plus a Decision
    Claim, and `parse_claims` synthesises the claim from a bare `correct`."""
    (directory / name).write_text(
        json.dumps({"frame_key": frame_key, "correct": list(correct)}), encoding="utf-8")


def test_a_conflicting_frame_is_DROPPED_from_the_lab_ruling_index_not_resolved_by_filename(tmp_path):
    """The consumer half, proved against a SYNTHETIC corpus.

    `composer_lab.fixture_rulings` must not return a claim for a frame whose fixtures disagree — its
    contract is *"the authoritative ruling where one exists"*, and where two live claims disagree
    there is none. Dropping it makes the lab fall back to the Correction record (the human's own)
    instead of to whichever filename sorted last.

    ⚠️ **Built on `tmp_path` deliberately, and the first version of this test was not.** It asserted
    against the committed store and opened with *"the probe found no conflicts at all"* as its
    instrument check — which passed only while the corpus still HELD a conflict. The moment
    `85164605|1|decision|41` was ruled, that check failed and the real assertion below had nothing
    left to run on. A control that evaporates when the bug is fixed is not a control; the corpus is
    the thing under test, never the instrument that proves the test works."""
    from train.composer_lab import fixture_ruling_conflicts, fixture_rulings
    # "a" sorts before "z", so a filename-order collapse would resolve this to [9], never to [1].
    _write_fixture(tmp_path, "a_claims_one.json", "ep|0|decision|7", [1])
    _write_fixture(tmp_path, "z_claims_nine.json", "ep|0|decision|7", [9])
    _write_fixture(tmp_path, "b_uncontested.json", "ep|0|decision|8", [2])

    rulings = fixture_rulings(tmp_path)
    conflicts = fixture_ruling_conflicts(tmp_path)

    assert "ep|0|decision|7" not in rulings, (
        f"the conflicted frame resolved to {rulings.get('ep|0|decision|7')} — the filename-order "
        f"collapse is back")
    assert rulings.get("ep|0|decision|8") == [2], "an uncontested frame must still be ruled"
    assert [c["frame_key"] for c in conflicts] == ["ep|0|decision|7"]
    assert conflicts[0]["claims"] == {(1,): ["a_claims_one.json"], (9,): ["z_claims_nine.json"]}, (
        "the report must name BOTH claims and the fixture each came from — a conflict a human "
        "cannot act on is the silence this replaces")


def test_two_fixtures_that_AGREE_are_not_collateral_damage(tmp_path):
    """The other direction, and the reason this file rejects only DISAGREEING duplicates. Two
    fixtures making the SAME claim about one frame are legal and load-bearing (`gates.claim_agreement`),
    so they must still resolve — dropping them would turn this guard into an unruled "one fixture per
    frame" policy."""
    from train.composer_lab import fixture_ruling_conflicts, fixture_rulings
    _write_fixture(tmp_path, "named_behaviour.json", "ep|0|decision|9", [5])
    _write_fixture(tmp_path, "t3holdout_sibling.json", "ep|0|decision|9", [5])
    assert fixture_rulings(tmp_path) == {"ep|0|decision|9": [5]}
    assert fixture_ruling_conflicts(tmp_path) == []


def test_the_committed_store_still_carries_agreeing_duplicates():
    """...and that the pairing above is a real convention rather than a hypothetical this test
    invented: the committed corpus pairs named behavioural fixtures with `*_t3holdout_*` siblings,
    and every one of those keys must still be RULED."""
    from train.composer_lab import fixture_rulings
    rulings = fixture_rulings()
    agreeing = [key for key, by_claim in _claims_by_key().items()
                if len(by_claim) == 1 and sum(len(n) for n in by_claim.values()) > 1]
    assert agreeing, "no agreeing duplicate keys in the committed store — the convention is gone"
    missing = [key for key in agreeing if key not in rulings]
    assert not missing, f"legal duplicate keys were dropped along with the conflicts: {missing}"
