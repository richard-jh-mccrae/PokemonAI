"""`tools/train/reviewed_audit.py` — the **covered-disposition audit** (Issue #238, ADR-0114).

A `reviewed.json` closure is a claim about the shipped agent. When the rule it names is deleted the
claim expires — silently, because the ledger stores its justification as prose and nothing reads it
back. These tests hold up the two things that make the audit trustworthy rather than merely loud:

**The vocabulary is harvested, not remembered.** `CLAUDE.md`'s worked example is a false claim
derived from `ls`; this file's equivalent trap is a rung-name sweep that finds zero because the sweep
is broken. So every zero here is paired with a case that MUST match — `prefer-active-attach-in-setup`
and `use-acceleration` return exactly 1 each while the five rungs Issue #238 names return 0 — and the
git-history harvest is held to two structural controls: it must contain every id that is live in the
tree right now, and every name in the four decider sweeps' `RETIRED` lists.

**The matcher is curated, not a regex.** The corpus's most frequent hyphenated token is
`attack-last`, 46 occurrences, and it is not a rung. A bare `[a-z-]+` scan flags every note that
mentions it; the synthetic controls below assert it is not flagged while a real retired rung in the
same note is.

`test_the_flagged_set_equals_the_committed_allowlist` is the ratchet (ADR-0114 decision 3): the
audit reports rather than gates, and the allowlist IS the developer's worklist, so a *new* stale
closure goes red while the standing 60 do not.
"""
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
#: The POSITIVE CONTROLS. Both are authored in `src/common/strategy/baseline/baseline_energy.py` and
#: are named there as SURVIVING the same swap that deleted the six above — so a sweep that reports
#: zero for these is broken, not reporting a clean tree.
THE_SURVIVORS = ("prefer-active-attach-in-setup", "use-acceleration")


@pytest.fixture(scope="module")
def vocab():
    return load_vocabulary(DEFAULT_VOCABULARY, DEFAULT_SRC)


@pytest.fixture(scope="module")
def reviewed():
    return load_reviewed(DEFAULT_REVIEWED)


# ---------------------------------------------------------------------------
# The claim the whole issue rests on, with its controls (acceptance criterion 3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-LEDGER-0001")
def test_the_survivors_are_live_exactly_once_each():
    """THE POSITIVE CONTROL. Run first, because every zero below is worthless without it.

    "Exactly once" is asserted, not implied: `harvest_ids` keeps every definition site precisely so
    this control can count rather than merely check a key is present."""
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


# ---------------------------------------------------------------------------
# The matcher — synthetic controls (acceptance criterion 3)
# ---------------------------------------------------------------------------

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
    """The reason the vocabulary is curated. `attack-last` is the corpus's most frequent hyphenated
    token (46 occurrences) and is the Pilot's structural resequencing, not a rung — a loose
    `[a-z-]+` scan flags every note that mentions it. The live rung in the same note keeps this
    honest: the classifier is reading the note, not ignoring it."""
    note = "attack-last: real Pilot plays Pokegear first (dig-before-commit) — retest [1]->[0]=correct"
    ref = classify_note(note, vocab)
    assert ref.retired == ()
    assert "attack-last" in ref.unresolved
    assert "dig-before-commit" in ref.live
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


# ---------------------------------------------------------------------------
# The real corpus (acceptance criteria 1 and 5)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-LEDGER-0005")
def test_issue_238s_thirteen_and_its_three_refuted_re_reads_are_all_flagged(vocab, reviewed):
    """The hand-derived population is a strict SUBSET of what the mechanical check finds. If the
    audit missed even one of them it would be measuring something other than what Issue #238 read."""
    from train.reviewed_audit import ISSUE_238_BODY_13, ISSUE_238_BODY_REFUTED_3
    flagged = {e.key for e in stale_entries(reviewed, vocab)}
    assert set(ISSUE_238_BODY_13) <= flagged
    assert set(ISSUE_238_BODY_REFUTED_3) <= flagged            # decision 6: `refuted` is covered too


@pytest.mark.req("REQ-LEDGER-0005")
def test_the_flagged_keys_are_ledger_keys_not_frame_keys(vocab, reviewed):
    """ADR-0114 decision 5: `reviewed.json` is the review LEDGER, keyed `<episode>-<frame>` — a
    different store and key shape from the `Correction` record schema Issue #229 governs. The audit
    reads it through `blunder.reviewed.load_reviewed` and reports in that key shape."""
    for entry in stale_entries(reviewed, vocab):
        assert "|" not in entry.key
        assert entry.key in reviewed


@pytest.mark.req("REQ-LEDGER-0006")
def test_the_flagged_set_equals_the_committed_allowlist(vocab, reviewed):
    """THE RATCHET (ADR-0114 decision 3). The audit reports; this is what makes it hold.

    Red here means one of two things and the diff says which: a NEW closure naming a dead rung (fix
    the closure, not this file), or a frame the developer has ruled and re-closed (delete its line
    from the allowlist). Bulk-refreshing the allowlist to go green defeats the entire mechanism —
    that is the failure mode `CLAUDE.md` records for auto-recaptured baselines, one layer down."""
    committed = json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]
    assert allowlist_form(stale_entries(reviewed, vocab)) == committed


@pytest.mark.req("REQ-LEDGER-0006")
def test_a_new_stale_closure_makes_the_allowlist_red(vocab, reviewed):
    """The differential control for the test above: a green assertion proves nothing unless the same
    comparison can go red. Two shapes, because both are real recurrences — a brand-new entry, and an
    existing entry re-closed against a SECOND dead rung (which a bare key list would call green)."""
    committed = json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]
    added = dict(reviewed, **{"99999999-9": {"disposition": "covered",
                                             "reason": "covered by build-active-wincon"}})
    assert allowlist_form(stale_entries(added, vocab)) != committed

    key = next(iter(committed))
    widened = dict(reviewed)
    widened[key] = dict(reviewed[key], reason=reviewed[key]["reason"] + " and power-up-attacker")
    assert allowlist_form(stale_entries(widened, vocab)) != committed


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_committed_worklist_covers_every_allowlisted_entry():
    """ADR-0114 decision 4. Deliberately NOT a byte-compare against a fresh render: the *what it
    became* column is read out of `src/` prose, so byte equality would red CI on an unrelated
    docstring edit. What has to hold is that the worklist actually lists the work."""
    report = DEFAULT_REPORT.read_text(encoding="utf-8")
    for key in json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))["entries"]:
        assert f"`{key}`" in report, f"{key} is allowlisted but absent from the generated worklist"


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_report_separates_refuted_from_the_blockers(vocab, reviewed):
    """Decision 6: a `refuted` label owes no fix, so those rows are listed but not as blockers."""
    body = render_report(stale_entries(reviewed, vocab), vocab, reviewed, DEFAULT_SRC)
    assert "NOT blockers" in body
    assert body.index("## `covered`") < body.index("## `refuted`")


@pytest.mark.req("REQ-LEDGER-0007")
def test_the_fold_map_target_comes_from_the_codes_own_fold_map():
    """The column that makes a ruling cheap. Paired with a rung the fold maps do NOT name, so the
    test distinguishes "read the fold map" from "returned something for everything"."""
    targets = fold_map_targets({"dont-waste-discard-energy", "play-energy-denial",
                                "keep-line-base-at-discard"}, DEFAULT_SRC)
    assert "BURST discipline" in targets["dont-waste-discard-energy"]
    assert "RETIRED" in targets["play-energy-denial"]
    assert targets["keep-line-base-at-discard"] == ""


@pytest.mark.req("REQ-LEDGER-0008")
def test_the_unresolved_tally_is_reported_not_suppressed(vocab, reviewed):
    """ADR-0114 decision 2's honesty clause — the vocabulary's blind spot stays visible, and its
    largest member is the token that would have made a loose scan useless."""
    tally = unresolved_tally(reviewed, vocab)
    assert tally["attack-last"] > 40
    assert not (set(tally) & (vocab.live | vocab.retired | vocab.sound_rules))


# ---------------------------------------------------------------------------
# The harvest's own controls — git history required, so SKIPPED on a shallow clone
# ---------------------------------------------------------------------------

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
    """The cache cannot drift into a DIFFERENT ANSWER. `--refresh-vocab` is the fix when this reds.

    Deliberately not `committed == fresh`. Authoring a new rung anywhere in `src/` moves
    `live_at_capture` and would red an equality test on work that has nothing to do with this audit —
    a false red teaches people to refresh the cache reflexively, which is how a ratchet dies. What
    must hold instead is that the cache invents nothing, that its git-pinned control is exact, and
    that the flagged set is IDENTICAL whether the retired half comes from the file or from a fresh
    harvest. If those three hold, staleness is invisible to the finding, which is the only property
    the audit rests on."""
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
