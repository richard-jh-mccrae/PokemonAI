"""**One Corpus Reader** — the contract, ENFORCED (ADR-0087 decision 4, Issue #241).

The Decision Gate lost 40 records and mis-keyed 163 more because it kept a private raw-JSONL walk
instead of constructing Corrections. Fixing that one module fixes one module. What stops it
recurring is this file: a reader that globs ``corrections.jsonl`` for itself must be on a list, and
every entry on that list must name a live issue.

Why an allowlist and not a bulk fix. `decider_lab` was not the *second* raw reader, it was the
**twelfth** — eleven probe scripts carry the identical ``v.get("obs") and v.get("agent")`` filter and
are short the same 40 records. Four of those eleven are the ``*_decider_sweep.py`` that ADR-0085
Amendment I declared **vacuous and replaced**: with each phase's rung pile deleted, their
kill-switch-OFF arm scores an empty pile, so they can only ever report FIX. Swapping their loader
would be investment in a retired instrument, and the honest disposition is probably deletion. So
they are RECORDED here with an owner rather than silently fixed or silently tolerated, and the
thirteenth reader cannot appear without turning this test red.

The entries name a live issue as part of the entry, never as a comment beside it — an exemption
whose justification rots is exactly the failure `reviewed.json`'s expired ``covered`` claims already
demonstrated (Issue #238), one store over.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Files permitted to read ``corrections.jsonl`` without going through
#: ``train.blunder.store``/``gates.keyed_corrections`` — each mapped to the issue that owns its
#: disposition. Removing a file from this dict is how the debt gets paid; adding one needs a reason
#: a reviewer will read.
ALLOWED_RAW_READERS = {
    # The eleven diagnostic sweeps. Every one is short the same 40 records. Issue #243 asks fix-or-delete
    # per reader; for the four `*_decider_sweep.py` the expected answer is DELETE (ADR-0085
    # Amendment I already replaced them, and a gate that can only report FIX is worse than absent).
    "tools/train/probes/attach_decider_sweep.py": "#243",
    "tools/train/probes/budget_sweep.py": "#243",
    "tools/train/probes/deny_gate1.py": "#243",
    "tools/train/probes/deny_gate217.py": "#243",
    "tools/train/probes/deploy_anchor_sweep.py": "#243",
    "tools/train/probes/deploy_decider_sweep.py": "#243",
    "tools/train/probes/evolve_decider_sweep.py": "#243",
    "tools/train/probes/needs_sweep.py": "#243",
    "tools/train/probes/promote_retreat_decider_sweep.py": "#243",
    "tools/train/probes/threat_sweep.py": "#243",
    # `snipe_decider_sweep.py` PAID this debt (Issue #239, ADR-TEMP-239 decision 5): retiring its
    # private RECORDED_MISSES store meant it had to join the Ruling Index by Frame Key, which a
    # hand-built `<ep>-<frame>` key cannot do — so the raw walk went with it. That is the intended
    # shape of a payoff: an entry leaves this dict, and the census below moves deliberately.
}

#: The store module IS the reader — it is the one place allowed to open the files.
_READER_HOME = "tools/train/blunder/store.py"

#: A glob/rglob of the log file. Matches the shapes actually used in the tree; a new reader inventing
#: a different spelling is caught by the second test, which looks for the filename at all.
_GLOB_RE = re.compile(r"""(?:r?)glob\(\s*["'][^"']*corrections\.jsonl["']""")
_MENTION_RE = re.compile(r"corrections\.jsonl")

_ISSUE_RE = re.compile(r"^#\d+$")


def _python_sources():
    for path in sorted((REPO / "tools").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, path.relative_to(REPO).as_posix()


@pytest.mark.req("REQ-GATE-0009")
def test_no_unlisted_module_globs_the_corrections_log():
    """THE enforcement. A new raw reader turns this red instead of silently shipping a thirteenth
    idea of what a record is."""
    offenders = sorted(rel for path, rel in _python_sources()
                       if rel != _READER_HOME
                       and rel not in ALLOWED_RAW_READERS
                       and _GLOB_RE.search(path.read_text(encoding="utf-8")))
    assert offenders == [], (
        "these read data/corrections/ directly instead of via train.blunder.store / "
        "gates.keyed_corrections (ADR-0087 decision 1). Route them through the Corpus Reader, "
        f"or add them to ALLOWED_RAW_READERS with the issue that owns them: {offenders}")


@pytest.mark.req("REQ-GATE-0009")
def test_every_allowlisted_reader_exists_and_still_reads_raw():
    """The list is a work queue, not scenery. An entry whose file is gone, or which has since been
    routed through the Corpus Reader, must be DELETED from the list — otherwise the allowlist slowly
    becomes a set of permanent exemptions nobody can distinguish from real ones."""
    stale = []
    for rel in ALLOWED_RAW_READERS:
        path = REPO / rel
        if not path.exists():
            stale.append(f"{rel} (file is gone)")
        elif not _GLOB_RE.search(path.read_text(encoding="utf-8")):
            stale.append(f"{rel} (no longer reads raw — delete the entry)")
    assert stale == [], f"stale ALLOWED_RAW_READERS entries: {stale}"


@pytest.mark.req("REQ-GATE-0009")
def test_every_allowlist_entry_names_an_issue():
    """The owner is part of the entry, so the debt is attributable. Same discipline the Held-out
    Ledger applies to a ruled frame (ADR-0072 decision 4): an exemption with no owner is a leak."""
    bad = sorted(f"{rel} -> {owner!r}" for rel, owner in ALLOWED_RAW_READERS.items()
                 if not (isinstance(owner, str) and _ISSUE_RE.match(owner)))
    assert bad == [], f"allowlist entries must name an issue like '#243': {bad}"


@pytest.mark.req("REQ-GATE-0009")
def test_the_two_gates_are_not_on_the_allowlist():
    """The point of the exercise, asserted directly rather than left implicit in the list's absence
    of two names. Both gates go through the Corpus Reader; if either reappears here, the fix has been
    reverted and the 40 records are gone again."""
    for rel in ("tools/train/decider_lab.py", "tools/train/leaf_lab.py",
                "tools/train/blunder/frame_view.py"):
        assert rel not in ALLOWED_RAW_READERS
        assert not _GLOB_RE.search((REPO / rel).read_text(encoding="utf-8"))


@pytest.mark.req("REQ-GATE-0009")
def test_the_allowlist_census_matches_what_the_grill_measured():
    """TEN — the eleven Issue #241 named, less `snipe_decider_sweep.py`, which Issue #239 converted
    to `keyed_corrections` when it retired that file's private ruling store. A silent change to this
    number means either the debt was paid (delete the entry) or a new reader was waved through
    (don't) — both are worth a deliberate edit rather than a quiet drift."""
    assert len(ALLOWED_RAW_READERS) == 10
    assert "tools/train/probes/snipe_decider_sweep.py" not in ALLOWED_RAW_READERS
    assert all(rel.startswith("tools/train/probes/") for rel in ALLOWED_RAW_READERS)


@pytest.mark.req("REQ-GATE-0009")
def test_modules_that_only_mention_the_log_in_prose_are_not_flagged():
    """The regex targets an actual glob, not the filename. `tools/train/blunder_report.py` names the
    path in its module docstring and never opens it directly — a check that could not tell those
    apart would train people to widen the allowlist, which is how an allowlist dies."""
    rel = "tools/train/blunder_report.py"
    text = (REPO / rel).read_text(encoding="utf-8")
    assert _MENTION_RE.search(text)                 # it does name the log...
    assert rel not in ALLOWED_RAW_READERS           # ...and is not exempted


@pytest.mark.req("REQ-GATE-0009")
def test_constructing_records_is_not_enough_the_layout_is_the_stores_too():
    """`tools/sim/score_diff.py` was the near-miss worth asserting on: it CONSTRUCTED its records through
    `load_corrections` — decision 1 satisfied — while still `rglob`-ing for the files itself. That is
    a second idea of what the corpus *is*, one level below the second idea of what a *record* is, and
    it is the shape a future reader is most likely to get half-right. Both halves come from the
    store: `jsonl_files` for where, `load_corrections` for what."""
    text = (REPO / "tools/sim/score_diff.py").read_text(encoding="utf-8")
    assert "jsonl_files" in text and not _GLOB_RE.search(text)
