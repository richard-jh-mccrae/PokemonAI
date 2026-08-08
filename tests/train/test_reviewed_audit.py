"""`tools/train/reviewed_audit.py` — the covered-disposition audit (Issue #238, ADR-0114).

A `reviewed.json` closure names a rule; when that rule is deleted the claim expires silently.
Two properties make the audit trustworthy: the vocabulary is harvested from git rather than
remembered (so every zero here is paired with a case that MUST match), and the matcher is
curated rather than a `[a-z-]+` regex. `test_the_flagged_set_equals_the_committed_allowlist`
is the ratchet (ADR-0114 decision 3)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.reviewed_audit import (DEFAULT_ALLOWLIST, DEFAULT_REPORT,  # noqa: E402
                                  DEFAULT_REVIEWED, DEFAULT_SRC, DEFAULT_VOCABULARY,
                                  allowlist_form, build_vocabulary, classify_note,
                                  fold_map_targets, git_history_available, harvest_ids,
                                  historical_rung_ids, load_vocabulary, render_report,
                                  rung_tokens, stale_entries, sweep_retired_ids,
                                  unresolved_tally, Vocabulary)
from train.blunder.reviewed import load_reviewed  # noqa: E402

#: The five rungs the 13 `covered` notes lean on, plus the one the `refuted` trio cites. The whole
#: issue rests on these being gone; if any comes back this file should say so, loudly.
THE_VANISHED = ("dont-waste-discard-energy", "concentrate-energy-on-wincon", "build-active-wincon",
                "power-up-attacker", "conserve-burst-when-no-ko", "attach-energy-last")
#: The POSITIVE CONTROLS: both are authored in `baseline/baseline_energy.py` and named there as
#: SURVIVING the swap that deleted the six above, so a zero here is a broken sweep.
THE_SURVIVORS = ("prefer-active-attach-in-setup", "use-acceleration")


@pytest.fixture(scope="module")
def vocab():
    return load_vocabulary(DEFAULT_VOCABULARY, DEFAULT_SRC)


@pytest.fixture(scope="module")
def reviewed():
    return load_reviewed(DEFAULT_REVIEWED)


# The claim the whole issue rests on, with its controls.

@pytest.mark.req("REQ-LEDGER-0001")
def test_the_survivors_are_live_exactly_once_each():
    """THE POSITIVE CONTROL. Run first, because every zero below is worthless without it."""
    live = harvest_ids(DEFAULT_SRC, "Hypothesis")
    for rung in THE_SURVIVORS:
        assert rung in live, f"{rung} should be a live Hypothesis — the harvest is broken"
        assert len(live[rung]) == 1, f"{rung} has {len(live[rung])} definition sites: {live[rung]}"
    assert "baseline_energy" in live["use-acceleration"][0]


@pytest.mark.req("REQ-LEDGER-0001")
def test_the_vanished_rungs_have_no_live_definition(vocab):
    """Issue #238's central factual claim, asserted rather than recalled."""
    for rung in THE_VANISHED:
        assert rung not in vocab.live, f"{rung} is live again — Issue #238's premise no longer holds"
        assert vocab.resolve(rung) == "retired"
    for rung in THE_SURVIVORS:
        assert vocab.resolve(rung) == "live"


@pytest.mark.req("REQ-LEDGER-0002")
def test_a_sound_rule_id_is_a_live_namespace_not_a_retired_rung(vocab):
    """`SoundRule` ids are hyphenated and were never Hypotheses. Harvested as their own namespace so
    they can never be mistaken for deleted rungs — 15 of them would be, otherwise."""
    sound = harvest_ids(DEFAULT_SRC, "SoundRule")
    assert "ko-score-band" in sound, "the SoundRule harvest is broken, not the file empty"
    assert vocab.resolve("ko-score-band") == "sound-rule"
    assert not (vocab.live & vocab.sound_rules)


# The matcher — synthetic controls.

@pytest.mark.req("REQ-LEDGER-0003")
def test_a_note_naming_a_live_rung_is_not_flagged(vocab):
    ledger = {"99999999-1": {"disposition": "covered",
                             "reason": "covered by prefer-active-attach-in-setup (+8)"}}
    assert stale_entries(ledger, vocab) == []


@pytest.mark.req("REQ-LEDGER-0003")
def test_a_note_naming_a_retired_rung_is_flagged(vocab):
    ledger = {"99999999-2": {"disposition": "covered",
                             "reason": "the intent is already handled by dont-waste-discard-energy"}}
    flagged, = stale_entries(ledger, vocab)
    assert flagged.key == "99999999-2"
    assert flagged.dead == ("dont-waste-discard-energy",)


@pytest.mark.req("REQ-LEDGER-0004")
def test_prose_that_is_not_a_rung_is_never_flagged(vocab):
    """The reason the vocabulary is curated: `attack-last` is the corpus's most frequent hyphenated
    token and is the Pilot's structural resequencing, not a rung — a loose scan flags every note."""
    live = sorted(vocab.live)[0]
    note = f"attack-last: real Pilot plays Pokegear first ({live}) — retest [1]->[0]=correct"
    ref = classify_note(note, vocab)
    assert ref.retired == ()
    assert "attack-last" in ref.unresolved
    assert live in ref.live
    assert stale_entries({"99999999-3": {"disposition": "covered", "reason": note}}, vocab) == []


@pytest.mark.req("REQ-LEDGER-0004")
def test_dates_damage_and_frame_ids_are_not_tokens():
    """A hyphenated run that starts with a digit is never a rung, and treating it as one would put
    `2026-08-02` and `81785223-32` into the unresolved tally as if they were vocabulary gaps."""
    tokens = rung_tokens("re-ruled 2026-08-02 on 81785223-32 for 120-dmg; see dont-waste-discard-energy")
    assert tokens == ["re-ruled", "dont-waste-discard-energy"]


@pytest.mark.req("REQ-LEDGER-0004")
def test_a_longer_id_never_yields_a_shorter_false_hit():
    v = Vocabulary(retired=frozenset({"power-up"}))
    assert classify_note("power-up-attacker fires", v).retired == ()


# The real corpus.

@pytest.mark.req("REQ-LEDGER-0005")
def test_stale_entries_include_covered_and_refuted_dispositions():
    """The audit reads all reviewed dispositions, including `refuted`: decision 6 says a refuted
    label owes no fix, but a vanished premise in its note is still reported."""
    v = Vocabulary(retired=frozenset({"dead-rung"}))
    sample = {
        "1-1": {"disposition": "covered", "reason": "covered by dead-rung"},
        "1-2": {"disposition": "refuted", "reason": "refuted by dead-rung"},
        "1-3": {"disposition": "covered", "reason": "covered by live prose"},
    }
    flagged = {e.key for e in stale_entries(sample, v)}
    assert flagged == {"1-1", "1-2"}


@pytest.mark.req("REQ-LEDGER-0005")
def test_the_flagged_keys_are_ledger_keys_not_frame_keys(vocab, reviewed):
    """ADR-0114 decision 5: `reviewed.json` is the review LEDGER, keyed `<episode>-<frame>`."""
    for entry in stale_entries(reviewed, vocab):
        assert "|" not in entry.key
        assert entry.key in reviewed


@pytest.mark.req("REQ-LEDGER-0006")
def test_the_flagged_set_equals_the_committed_allowlist(vocab, reviewed):
    """THE RATCHET (ADR-0114 decision 3). Red means a NEW closure naming a dead rung, or a frame the
    developer re-closed. Bulk-refreshing the allowlist to go green defeats the whole mechanism."""
    committed = json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]
    assert allowlist_form(stale_entries(reviewed, vocab)) == committed


@pytest.mark.req("REQ-LEDGER-0006")
def test_a_new_stale_closure_makes_the_allowlist_red(vocab, reviewed):
    """The differential control for the test above: a green assertion proves nothing unless it can red."""
    committed = json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]
    added = dict(reviewed, **{"99999999-9": {"disposition": "covered",
                                             "reason": "covered by build-active-wincon"}})
    assert allowlist_form(stale_entries(added, vocab)) != committed

    v = Vocabulary(retired=frozenset({"dead-rung", "second-dead-rung"}))
    before = {"1-1": {"disposition": "covered", "reason": "covered by dead-rung"}}
    after = {"1-1": {"disposition": "covered",
                     "reason": "covered by dead-rung and second-dead-rung"}}
    assert allowlist_form(stale_entries(before, v)) != allowlist_form(stale_entries(after, v))


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_committed_worklist_covers_every_allowlisted_entry():
    """ADR-0114 decision 4: not a byte-compare, since the column reads `src/` prose that moves freely."""
    report = DEFAULT_REPORT.read_text(encoding="utf-8")
    for key in json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]:
        assert f"`{key}`" in report, f"{key} is allowlisted but absent from the generated worklist"


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_report_separates_refuted_from_the_blockers(vocab, reviewed):
    """Decision 6: a `refuted` label owes no fix, so those rows are listed but not as blockers."""
    v = Vocabulary(retired=frozenset({"dead-rung"}))
    sample = {
        "1-1": {"disposition": "covered", "reason": "covered by dead-rung"},
        "1-2": {"disposition": "refuted", "reason": "refuted by dead-rung"},
    }
    body = render_report(stale_entries(sample, v), v, sample, DEFAULT_SRC)
    assert "NOT blockers" in body
    assert body.index("## `covered`") < body.index("## `refuted`")


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_fold_map_target_comes_from_the_retirement_registry():
    """Paired with a rung the registry does NOT carry, so an always-answering implementation fails."""
    targets = fold_map_targets({"dont-waste-discard-energy", "play-energy-denial",
                                "keep-line-base-at-discard"}, DEFAULT_SRC)
    assert "_attach_value" in targets["dont-waste-discard-energy"]
    assert "_DENIAL_PLAY_W" in targets["play-energy-denial"]
    assert targets["keep-line-base-at-discard"] == ""


@pytest.mark.req("REQ-LEDGER-0008")
def test_the_unresolved_tally_is_reported_not_suppressed(vocab, reviewed):
    """ADR-0114 decision 2's honesty clause — the vocabulary's blind spot stays visible, and its
    most important control is the token that would have made a loose scan useless."""
    sample = {"k": {"reason": "attack-last attack-last dont-waste-discard-energy"}}
    tally = unresolved_tally(sample, vocab)
    assert tally["attack-last"] == 1
    assert not (set(tally) & (vocab.live | vocab.retired | vocab.sound_rules))


# The harvest's own controls — git history required, so SKIPPED on a shallow clone.

_needs_git = pytest.mark.skipif(
    not git_history_available(REPO),
    reason="shallow clone or missing sweep revisions: the retired vocabulary cannot be re-derived "
           "here, which is exactly why data/corrections/rung_vocabulary.json is committed "
           "(.github/workflows/ci.yml checks out at actions/checkout@v4's default depth)")


@pytest.mark.req("REQ-LEDGER-0009")
@_needs_git
def test_every_live_rung_appears_in_the_historical_harvest():
    """STRUCTURAL CONTROL 1. A diff scan that cannot see a rung sitting in the tree right now cannot
    be believed about one that left."""
    historical = historical_rung_ids(REPO)
    missing = sorted(set(harvest_ids(DEFAULT_SRC, "Hypothesis")) - historical)
    assert missing == []


@pytest.mark.req("REQ-LEDGER-0009")
@_needs_git
def test_every_sweep_retired_name_appears_in_the_historical_harvest():
    """STRUCTURAL CONTROL 2. The four decider sweeps' `RETIRED` tuples are the authoritative deletion
    lists Issue #238 cross-referenced by hand. Every name in them must turn up."""
    historical, sweeps = historical_rung_ids(REPO), sweep_retired_ids(REPO)
    assert len(sweeps) > 40, "the sweep harvest is broken — those tuples are not empty"
    assert sorted(sweeps - historical) == []


@pytest.mark.req("REQ-LEDGER-0010")
@_needs_git
def test_the_cached_vocabulary_cannot_change_the_finding(reviewed):
    """Deliberately not `committed == fresh`: authoring any new rung moves `live_at_capture` and would
    red this on unrelated work. What must hold is that the cache cannot change the FINDING."""
    fresh = build_vocabulary(REPO, DEFAULT_SRC)
    committed = json.loads(DEFAULT_VOCABULARY.read_text(encoding="utf-8"))
    assert committed["sweep_retired"] == fresh["sweep_retired"]      # pinned SHAs: can never drift
    assert set(committed["retired"]) <= set(fresh["retired"]), "the cache names rungs history does not"

    live = set(harvest_ids(DEFAULT_SRC, "Hypothesis"))
    sound = set(harvest_ids(DEFAULT_SRC, "SoundRule"))
    fresh_vocab = Vocabulary(live=frozenset(live), sound_rules=frozenset(sound),
                             retired=frozenset(set(fresh["retired"]) - live - sound))
    cached_vocab = load_vocabulary(DEFAULT_VOCABULARY, DEFAULT_SRC)
    assert allowlist_form(stale_entries(reviewed, fresh_vocab)) == \
           allowlist_form(stale_entries(reviewed, cached_vocab))


@pytest.mark.req("REQ-LEDGER-0010")
def test_a_rung_deleted_since_the_capture_is_retired_without_git(tmp_path):
    """How the snapshot stays correct on a checkout with no history: anything that was live at
    capture and is not live now joins the retired set, no git access involved."""
    snapshot = tmp_path / "vocab.json"
    snapshot.write_bytes(json.dumps({
        "head": "deadbeef", "retired": [], "sweep_retired": [],
        "live_at_capture": ["use-acceleration", "a-rung-deleted-yesterday"],
        "sound_rules_at_capture": [],
    }).encode("utf-8"))
    v = load_vocabulary(snapshot, DEFAULT_SRC)
    assert v.resolve("a-rung-deleted-yesterday") == "retired"
    assert v.resolve("use-acceleration") == "live"           # control: still live, still not retired
