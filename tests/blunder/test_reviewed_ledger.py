"""The reviewed-corrections ledger: already-assessed blunders excluded from fresh blunder-busting.

Covers the loader/partition (`tools/train/blunder/reviewed.py`) and the maintenance CLI
(`tools/train/review_correction.py`). Lib-free: Corrections are stubbed to (episode_id, frame)."""
import json

import pytest

from corrections_helpers import correction_record, corrections_store
from train.blunder.reviewed import (
    DISPOSITIONS, load_reviewed, near_misses, partition_reviewed, resolve_locator, review_key,
)
from train.review_correction import main as cli


class _Corr:
    """Minimal Correction stub — partition only reads episode_id, seat, scope, subject, frame;
    the resolver additionally reads ``id``."""
    def __init__(self, episode_id, frame, *, scope="decision", subject=None, seat=0, id=None):
        self.episode_id = episode_id
        self.decision = {"frame": frame}
        self.scope = scope
        self.subject = frame if scope == "decision" and subject is None else subject
        self.seat = seat
        self.id = id or f"id{episode_id}x{frame}"


def _keyed(*corrs):
    """`keyed_corrections()`'s shape — ``[(Frame Key, Correction), ...]`` — from stubs. The Frame
    Key is spelled out rather than derived, so these tests never depend on `gates` (the layering
    `resolve_locator`'s injected-corpus signature exists to protect)."""
    return [(f"{c.episode_id}|{c.seat}|{c.scope}|{c.subject}", c) for c in corrs]


@pytest.mark.req("REQ-TUNE-0030")
def test_review_key_matches_the_report_id():
    assert review_key(_Corr(81904451, 37)) == "81904451-37"


@pytest.mark.req("REQ-TUNE-0034")
def test_review_key_is_scope_aware():
    """ADR-0049: a scoped Correction is ledgered by its Scope's subject, so disposing of a Turn
    Correction never retires the Decision Corrections inside that Turn (and vice versa)."""
    turn = _Corr(81904451, 37, scope="turn", subject=12, seat=1)
    match = _Corr(81904451, 37, scope="match", subject=None, seat=1)
    assert review_key(turn) == "81904451-t12s1"
    assert review_key(match) == "81904451-m1"
    assert len({review_key(turn), review_key(match), review_key(_Corr(81904451, 37))}) == 3


@pytest.mark.req("REQ-TUNE-0031")
def test_load_reviewed_drops_comment_keys_and_missing_is_empty(tmp_path):
    p = tmp_path / "reviewed.json"
    p.write_text(json.dumps({
        "_note": "a comment",
        "81904451-37": {"disposition": "refuted", "reason": "forgoes a KO"},
    }), encoding="utf-8")
    led = load_reviewed(p)
    assert set(led) == {"81904451-37"}                       # _note gone
    assert led["81904451-37"]["disposition"] == "refuted"
    assert load_reviewed(tmp_path / "nope.json") == {}        # missing -> {}


@pytest.mark.req("REQ-TUNE-0032")
def test_partition_splits_active_from_dispositioned():
    reviewed = {"81904451-37": {"disposition": "refuted", "reason": "forgoes a KO"}}
    corrs = [_Corr(81904451, 37), _Corr(81904451, 99)]       # 1 reviewed, 1 new
    active, dispositioned = partition_reviewed(corrs, reviewed)
    assert [c.episode_id for c in active] == [81904451] and active[0].decision["frame"] == 99
    assert len(dispositioned) == 1
    c, entry = dispositioned[0]
    assert review_key(c) == "81904451-37" and entry["disposition"] == "refuted"


# ── the Ruling Locator (ADR-0090, Issue #250) ─────────────────────────────────────────────────
#
# Both orphans `gates.orphan_rulings` found named LIVE committed records under the wrong name:
# `85046350-10` had the wrong EPISODE (the record is ep 85045840 f10), `86091435-119` the wrong key
# SHAPE (the record is turn-scoped, so its `review_key` is `86091435-t14s0` — 119 is the Anchor
# frame the report printed). Neither was stale. A hand-typed ledger key IS a hand-built key.
#
# Stub-driven and corpus-free by design: `resolve_locator` takes the corpus as an ARGUMENT, so its
# tests need no JSONL on disk. That is decision 5's injected-corpus signature paying for itself.

_TURN = _Corr(86091435, 119, scope="turn", subject=14, id="948537a24fb2")     # the real orphan 2
_DEC = _Corr(85045840, 10, id="d374430e9bc7")                                # the real orphan 1


@pytest.mark.req("REQ-TUNE-0035")
def test_every_locator_form_resolves_to_the_one_canonical_review_key():
    """Four ways to name a record, ONE key written. The operator supplies a way to FIND the record;
    the key is still derived from it (ADR-0087 decision 2) — a locator is that rule applied to the
    writer, not a relaxation of it."""
    keyed = _keyed(_TURN, _DEC)
    for locator in ("86091435-t14s0",              # the canonical review_key
                    "86091435|0|turn|14",          # the Frame Key, as a gate readout prints it
                    "948537a24fb2",                # the Correction id
                    "86091435-119"):               # the ANCHOR form — what the report printed
        assert resolve_locator(locator, keyed) == "86091435-t14s0", locator


@pytest.mark.req("REQ-TUNE-0035")
def test_a_decision_scoped_records_anchor_and_key_are_the_same_string():
    """On a decision-scope record the anchor form IS the review_key, so the four forms collapse to
    three and nothing special-cases scope."""
    keyed = _keyed(_TURN, _DEC)
    assert resolve_locator("85045840-10", keyed) == "85045840-10"
    assert resolve_locator("85045840|0|decision|10", keyed) == "85045840-10"
    assert resolve_locator("d374430e9bc7", keyed) == "85045840-10"


@pytest.mark.req("REQ-TUNE-0035")
def test_an_unknown_locator_resolves_to_nothing():
    """The property the whole build exists for: a locator naming no committed Correction must NOT
    become a ledger entry. `85046350-10` is the real orphan — right frame, wrong episode."""
    keyed = _keyed(_TURN, _DEC)
    assert resolve_locator("85046350-10", keyed) is None
    assert resolve_locator("", keyed) is None
    assert resolve_locator("nonsense", keyed) is None


@pytest.mark.req("REQ-TUNE-0035")
def test_the_canonical_key_outranks_a_colliding_anchor_form():
    """A string that is simultaneously one record's `review_key` and a DIFFERENT record's anchor
    form resolves to the key. Contrived, but the ranking must be decided somewhere, and resolving to
    the anchor would silently re-point a ruling at a record the operator did not name."""
    ruled = _Corr(7, 3)                                                  # review_key "7-3"
    anchored = _Corr(7, 3, scope="turn", subject=99)                     # anchor form ALSO "7-3"
    assert resolve_locator("7-3", _keyed(ruled, anchored)) == "7-3"
    assert resolve_locator("7-3", _keyed(anchored, ruled)) == "7-3"      # order-independent


@pytest.mark.req("REQ-TUNE-0036")
def test_a_near_miss_names_the_same_frame_under_a_different_episode():
    """Rule 1, read off orphan 1: `85046350-10` is one digit-group away from `85045840-10`, and both
    episodes live in the same store file. Deterministic — the frame number matches exactly."""
    assert near_misses("85046350-10", _keyed(_TURN, _DEC)) == ["85045840-10"]


@pytest.mark.req("REQ-TUNE-0036")
def test_a_near_miss_names_the_episodes_own_rulings_when_the_subject_is_unknown():
    """Rule 2 — the generalised anchor↔Scope-subject case. Orphan 2's LITERAL spelling
    (`86091435-119`) now *resolves* via the anchor form rather than being suggested, which is that
    rule succeeding instead of guessing; what remains for it to catch is a locator naming a known
    episode and an unknown subject."""
    keyed = _keyed(_TURN, _DEC, _Corr(86091435, 60))
    assert near_misses("86091435-120", keyed) == ["86091435-60", "86091435-t14s0"]


@pytest.mark.req("REQ-TUNE-0036")
def test_the_two_near_miss_rules_UNION_and_the_operators_own_episode_leads():
    """The rules must never suppress each other, and the episode the operator got RIGHT is the
    stronger signal.

    Found by review, reproduced on the real corpus: with the rules as a fallback chain
    (``same_frame or same_episode``), `near_misses("86091435-120")` returned
    ``['82753102-120', '83667237-120']`` — two UNRELATED episodes that happen to carry a frame 120 —
    while all eleven rulings in the operator's OWN episode were suppressed. Confident, wrong, and
    hiding the right candidate: precisely the failure the no-fuzzy-matching rule exists to prevent,
    arrived at from the other direction.

    The stub that first covered rule 2 passed only because its corpus had no other episode carrying
    that frame, i.e. the setup guaranteed the result. This one supplies exactly that other episode."""
    keyed = _keyed(_TURN, _DEC, _Corr(86091435, 60), _Corr(82753102, 120), _Corr(83667237, 120))
    assert near_misses("86091435-120", keyed) == [
        "86091435-60", "86091435-t14s0",          # the operator's OWN episode, first
        "82753102-120", "83667237-120",           # then the same-frame candidates
    ]


@pytest.mark.req("REQ-TUNE-0036")
def test_a_near_miss_is_silent_rather_than_wrong():
    """No edit distance, no fuzzy matching. A confident wrong suggestion points at SOMEONE ELSE's
    human ruling, and the entry it produces would be correctly-formed and therefore invisible to
    `gates.orphan_rulings` — strictly worse than saying nothing."""
    keyed = _keyed(_TURN, _DEC)
    assert near_misses("99999999-42", keyed) == []          # unknown episode AND unknown frame
    assert near_misses("nonsense", keyed) == []
    assert near_misses("85045840-10", keyed) == []          # it RESOLVES; nothing to suggest


def _cli_store(tmp_path):
    """A `tmp_path` corpus the CLI can resolve against — one decision-scope record (`81904451-37`)
    and one TURN-scope one whose Anchor frame is 119 but whose ledger key is `86091435-t14s0`."""
    return corrections_store(tmp_path / "corpus", [
        correction_record(81904451, 37),
        correction_record(86091435, 119, scope="turn", subject=14, corr_id="948537a24fb2"),
    ])


@pytest.mark.req("REQ-TUNE-0033")
def test_cli_records_lists_and_removes(tmp_path, capsys):
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    assert cli(["81904451-37", "refuted", "forgoes a KO", "--path", str(p), "--store", str(store)]) == 0
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["81904451-37"]["disposition"] == "refuted"
    assert saved["81904451-37"]["reason"] == "forgoes a KO"
    assert "round" in saved["81904451-37"]

    capsys.readouterr()
    assert cli(["--list", "--path", str(p)]) == 0            # --list needs NO corpus
    assert "81904451-37" in capsys.readouterr().out

    assert cli(["--remove", "81904451-37", "--path", str(p), "--store", str(store)]) == 0
    assert "81904451-37" not in json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.req("REQ-TUNE-0033")
def test_cli_rejects_an_unknown_disposition(tmp_path):
    with pytest.raises(SystemExit):                          # argparse choices= guard
        cli(["81904451-37", "bogus", "x", "--path", str(tmp_path / "r.json")])
    assert "refuted" in DISPOSITIONS and "deferred" in DISPOSITIONS and "covered" in DISPOSITIONS


@pytest.mark.req("REQ-TUNE-0035")
def test_cli_writes_the_canonical_key_not_the_one_typed(tmp_path):
    """The whole repair, end to end. An operator copying `ep 86091435 f119` off the report gets the
    ruling filed under `86091435-t14s0` — the key that actually reaches the record."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    assert cli(["86091435-119", "refuted", "better line", "--path", str(p), "--store", str(store)]) == 0
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert list(saved) == ["86091435-t14s0"]                 # NOT "86091435-119"


@pytest.mark.req("REQ-TUNE-0035")
def test_cli_refuses_an_unresolvable_locator_and_writes_nothing(tmp_path, capsys):
    """Non-zero AND no write. Asserting the ledger is untouched is the property that matters — a
    tool that reports failure but files the entry anyway is the defect, not the exit code."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    p.write_text(json.dumps({"81904451-37": {"disposition": "covered", "reason": "", "round": "x"}}),
                 encoding="utf-8")
    before = p.read_text(encoding="utf-8")

    assert cli(["85046350-10", "covered", "typo", "--path", str(p), "--store", str(store)]) != 0
    assert p.read_text(encoding="utf-8") == before            # nothing written


@pytest.mark.req("REQ-TUNE-0036")
def test_cli_names_the_near_miss_it_found(tmp_path, capsys):
    """A digit slip is a one-line fix, not a manual corpus search — so the refusal has to name the
    record the operator probably meant."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    capsys.readouterr()
    assert cli(["99999999-37", "covered", "x", "--path", str(p), "--store", str(store)]) != 0
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "81904451-37" in out                               # same frame, different episode


@pytest.mark.req("REQ-TUNE-0035")
def test_cli_remove_resolves_a_locator_too(tmp_path):
    """Un-ruling is exactly as safe as ruling: `--remove` given the anchor form deletes the entry
    filed under the canonical key, rather than reporting 'no ledger entry' and leaving it behind."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    p.write_text(json.dumps({"86091435-t14s0": {"disposition": "refuted", "reason": "", "round": "x"}}),
                 encoding="utf-8")
    assert cli(["--remove", "86091435-119", "--path", str(p), "--store", str(store)]) == 0
    assert json.loads(p.read_text(encoding="utf-8")) == {}


@pytest.mark.req("REQ-TUNE-0035")
def test_cli_remove_can_still_delete_an_ORPHANED_entry(tmp_path):
    """Found by review. Resolving `--remove` against the corpus made the one entry that most needs
    deleting — an ORPHAN, the thing `gates.orphan_rulings` exists to surface — un-deletable, because
    by definition no Correction resolves it.

    Removal is an operation on the LEDGER, so the ledger's own keys are a legitimate second source
    for it. Resolution still wins when it succeeds (that is what makes the Anchor form work); the
    literal key is the fallback, not the other way round."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    p.write_text(json.dumps({"85046350-10": {"disposition": "covered", "reason": "", "round": "x"}}),
                 encoding="utf-8")
    assert cli(["--remove", "85046350-10", "--path", str(p), "--store", str(store)]) == 0
    assert json.loads(p.read_text(encoding="utf-8")) == {}


@pytest.mark.req("REQ-TUNE-0035")
def test_cli_still_refuses_to_RECORD_under_an_unresolvable_key(tmp_path):
    """The ledger-key fallback is scoped to `--remove` alone. Recording must never accept a key the
    corpus cannot reach, or the whole guard is back to free text — including the case where the
    operator is 'correcting' an existing orphan in place."""
    p, store = tmp_path / "reviewed.json", _cli_store(tmp_path)
    p.write_text(json.dumps({"85046350-10": {"disposition": "covered", "reason": "", "round": "x"}}),
                 encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    assert cli(["85046350-10", "refuted", "x", "--path", str(p), "--store", str(store)]) != 0
    assert p.read_text(encoding="utf-8") == before
