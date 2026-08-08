"""**No two committed fixtures may rule ONE frame differently** — `tests/fixtures/corrections/`
checked straight off the filesystem.

The failure mode is that a disagreement is *silent*: `composer_lab.fixture_rulings` used to flatten
the corpus walk with ``out[key] = ...``, so the winner was whichever FILENAME sorted last.

**Only DISAGREEING duplicates are rejected. Sharing a frame key is legal and load-bearing** —
`gates.claim_agreement`'s own docstring rules it, and the committed store deliberately pairs named
behavioural fixtures with their `*_t3holdout_*` siblings.

A declared ADR-0082 divergence does not exempt a fixture here. `claim_agreement` asks whether a
fixture disagrees with the RECORD, and a declaration answers that; this asks whether two fixtures
disagree with EACH OTHER, which a declaration cannot settle.
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
#: forgotten. Currently EMPTY, and that is a result: the one entry was ruled and both reconciled.
_CONFLICT_EXEMPT: dict[str, str] = {}


def _claims_by_key() -> dict:
    """``{frame key: {claim tuple: [fixture names]}}`` over the committed fixture store, read through
    `gates.iter_keyed_fixtures` — THE one corpus walk — rather than a second glob (ADR-0087)."""
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
    """The exemption list is not a place to park a stale entry: a key that no longer conflicts would
    quietly grant immunity to a frame_key that could later collide for a different reason."""
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
    """`composer_lab.fixture_rulings` must not return a claim for a frame whose fixtures disagree.
    Built on `tmp_path`: a control that evaporates when the corpus bug is fixed is not a control."""
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
    """Two fixtures making the SAME claim about one frame are legal and load-bearing, so they must still
    resolve — dropping them would turn this guard into an unruled one-fixture-per-frame policy."""
    from train.composer_lab import fixture_ruling_conflicts, fixture_rulings
    _write_fixture(tmp_path, "named_behaviour.json", "ep|0|decision|9", [5])
    _write_fixture(tmp_path, "t3holdout_sibling.json", "ep|0|decision|9", [5])
    assert fixture_rulings(tmp_path) == {"ep|0|decision|9": [5]}
    assert fixture_ruling_conflicts(tmp_path) == []


def test_the_committed_store_still_carries_agreeing_duplicates():
    """...and that the pairing above is a real convention rather than a hypothetical: the committed
    corpus pairs named fixtures with `*_t3holdout_*` siblings, and every such key must stay RULED."""
    from train.composer_lab import fixture_rulings
    rulings = fixture_rulings()
    agreeing = [key for key, by_claim in _claims_by_key().items()
                if len(by_claim) == 1 and sum(len(n) for n in by_claim.values()) > 1]
    assert agreeing, "no agreeing duplicate keys in the committed store — the convention is gone"
    missing = [key for key in agreeing if key not in rulings]
    assert not missing, f"legal duplicate keys were dropped along with the conflicts: {missing}"
