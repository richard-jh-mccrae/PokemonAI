"""**One Corpus Reader** — the contract, ENFORCED (ADR-0087 decision 4; widened by ADR-TEMP-243).

The Decision Gate lost 40 records and mis-keyed 163 more because it kept a private raw-JSONL walk
instead of constructing Corrections. Fixing that one module fixes one module. What stops it
recurring is this file.

Issue #241 shipped it as an allowlist: a reader that globbed ``corrections.jsonl`` had to be listed
with a live issue owning its disposition, because `decider_lab` was not the *second* raw reader but
the **twelfth**. Issue #243 paid that queue to **empty** — five probe modules deleted, five routed —
so the dict is gone. A work queue that empties is supposed to disappear; one kept alive past its
work becomes a set of permanent exemptions nobody can distinguish from real ones.

**What Issue #243 changed about the rule itself, and why it matters more than the count.** The
original check scanned ``tools/`` and matched ``glob(``. Both bounds were occupied:

* nine files under ``tests/strategy/`` globbed the corpus (one carrying the identical
  ``d.get("obs") and d.get("agent")`` filter, short the same 40 records), and
* two more reached it by naming a build directory outright —
  ``REPO/"data"/"corrections"/"dragapult_ex_20260715_32530b9"/"corrections.jsonl"`` — which no glob
  pattern can see, and which breaks *silently* the day that directory is renamed.

So the rule now forbids **reaching the corrections log**, not one spelling of it, across ``tools/``
**and** ``tests/``. A check that names a spelling teaches people to find another spelling, and two
files found one without anyone doing it deliberately.

The prose guard below is load-bearing for the same reason it always was: a check that cannot tell a
mention from a read trains people to widen the exemption, which is how an allowlist dies.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The store module IS the reader — it is the one place allowed to open the files.
_READER_HOME = "tools/train/blunder/store.py"

#: This file names every forbidden shape in its own source, so it must exempt itself.
_SELF = "tests/train/test_corpus_readers.py"

#: A glob/rglob of the log. The shape Issue #241 enforced against.
_GLOB_RE = re.compile(r"""(?:r?)glob\(\s*["'][^"']*corrections\.jsonl["']""")

#: A FIXED path that reaches the log — the shape Issue #241's regex was blind to. Deliberately
#: requires the `data`/`corrections` segments AND the filename on one line, so it matches a real
#: corpus-log path and not the many legitimate `data/corrections` constructions that address
#: something else entirely: the reviewed ledger (`reviewed.json`), the tuner proposals dir
#: (`tuner/*.json`), the machine store, and every CLI `--store` default that hands the directory to
#: `train.blunder.store`. Those are not the corpus log and must not be flagged.
#:
#: It also must NOT match a `tmp_path / "corrections.jsonl"` synthetic store — fourteen test files
#: build one, they are the store's own unit tests, and they carry no `data`/`corrections` segments.
_FIXED_PATH_RE = re.compile(
    r"""["']data["']\s*/\s*["']corrections["'][^\n]*corrections\.jsonl""")

#: The slash-string spelling of the same thing. Only counts when the line also BUILDS or OPENS the
#: path, because naming that string is not always reaching it: `tests/label/test_category.py` passes
#: `"data/corrections/machine/corrections.jsonl"` to `git check-ignore` to assert the machine store
#: stays untracked. That test never opens the file, and flagging it would push a correct assertion
#: into an exemption — the precise decay ADR-TEMP-243 decision 4 removed the allowlist to stop.
_SLASH_PATH_RE = re.compile(r"""["'][^"'\n]*data/corrections/[^"'\n]*corrections\.jsonl["']""")
_OPENS_RE = re.compile(r"Path\(|open\(|read_text|read_bytes|open_text")

_MENTION_RE = re.compile(r"corrections\.jsonl")


def _reaches_the_log(text: str) -> bool:
    """The one predicate. Every spelling counts; none is privileged."""
    if _GLOB_RE.search(text) or _FIXED_PATH_RE.search(text):
        return True
    return any(_SLASH_PATH_RE.search(line) and _OPENS_RE.search(line)
               for line in text.splitlines())


def _python_sources():
    """`tools/` AND `tests/`. Scanning only the first was how eleven readers hid in the second."""
    for root in ("tools", "tests"):
        for path in sorted((REPO / root).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path, path.relative_to(REPO).as_posix()


@pytest.mark.req("REQ-GATE-0009")
def test_no_module_outside_the_store_reaches_the_corrections_log():
    """THE enforcement, and there is no longer an allowlist to land on. A new raw reader turns this
    red instead of silently shipping a thirteenth idea of what a record is."""
    offenders = sorted(rel for path, rel in _python_sources()
                       if rel not in (_READER_HOME, _SELF)
                       and _reaches_the_log(path.read_text(encoding="utf-8")))
    assert offenders == [], (
        "these reach data/corrections/ directly instead of via train.blunder.store / "
        "gates.keyed_corrections (ADR-0087 decision 1). Route them through the Corpus Reader — "
        f"tests have `tests/corpus_helpers.py` for exactly this: {offenders}")


@pytest.mark.req("REQ-GATE-0009")
def test_a_fixed_build_path_is_caught_not_just_a_glob():
    """The widening, asserted directly rather than left implicit in an empty offender list.

    `test_attach_target_priority.py` and `test_counter_mover_attach.py` both hardcoded
    `dragapult_ex_20260715_32530b9`, and the glob-only check waved them through for four months. A
    hardcoded build directory is arguably WORSE than a glob: it is a second idea of where the corpus
    lives that also breaks silently on a rename."""
    assert _reaches_the_log(
        'corr = REPO / "data" / "corrections" / "dragapult_ex_20260715_32530b9" / "corrections.jsonl"')
    assert _reaches_the_log('for jf in CORR.glob("*/corrections.jsonl"):')


@pytest.mark.req("REQ-GATE-0009")
def test_the_two_gates_and_the_viewer_go_through_the_corpus_reader():
    """The point of the exercise, asserted directly. If any of these reappears as a raw reader, the
    fix has been reverted and the 40 records are gone again."""
    for rel in ("tools/train/decider_lab.py", "tools/train/leaf_lab.py",
                "tools/train/blunder/frame_view.py"):
        assert not _reaches_the_log((REPO / rel).read_text(encoding="utf-8")), rel


@pytest.mark.req("REQ-GATE-0009")
def test_the_probe_dispositions_landed():
    """ADR-TEMP-243's disposition table, as an assertion. Five probes were DELETED (four one-shot
    rulings plus the vacuous gate) and five ROUTED; a probe reappearing under either name means a
    ruling was reverted without one being recorded."""
    probes = REPO / "tools" / "train" / "probes"
    for gone in ("deploy_decider_sweep", "deny_gate1", "deny_gate217", "deploy_anchor_sweep"):
        assert not (probes / f"{gone}.py").exists(), f"{gone} was deleted by Issue #243"
    for kept in ("attach_decider_sweep", "evolve_decider_sweep", "promote_retreat_decider_sweep",
                 "needs_sweep", "threat_sweep", "snipe_decider_sweep"):
        assert (probes / f"{kept}.py").exists(), kept


@pytest.mark.req("REQ-GATE-0009")
def test_threat_sweep_no_longer_offers_the_vacuous_modes():
    """`--slots` compared the shipped PROFILE against `_forced(gust_target_slots=True)` while the
    PROFILE has shipped that flag ON since 2026-07-27 — same-vs-same, 0 flips BY CONSTRUCTION. Its
    sibling `sweep_rank` forced both sides and its docstring said why, so the mistake sat next to its
    own correction. `--rank` was answered (ADR-0083) and is pinned by `test_scaled_rank_corpus.py`.
    Asserted here because a re-added mode reads as new coverage rather than as a returning defect."""
    text = (REPO / "tools" / "train" / "probes" / "threat_sweep.py").read_text(encoding="utf-8")
    assert "def sweep_slots" not in text and "def sweep_rank" not in text
    assert '"--slots"' not in text and '"--rank"' not in text


@pytest.mark.req("REQ-GATE-0009")
def test_modules_that_only_mention_the_log_in_prose_are_not_flagged():
    """The check targets a read, not the filename. `tools/train/blunder_report.py` names the path in
    its module docstring and never opens it directly — a check that could not tell those apart would
    train people to route around it, which is how the allowlist this replaced started."""
    rel = "tools/train/blunder_report.py"
    text = (REPO / rel).read_text(encoding="utf-8")
    assert _MENTION_RE.search(text)                 # it does name the log...
    assert not _reaches_the_log(text)               # ...and does not reach it


@pytest.mark.req("REQ-GATE-0009")
def test_a_synthetic_tmp_path_store_is_not_a_corpus_read():
    """The store's own unit tests build `tmp_path / "corrections.jsonl"` — fourteen files do. That is
    a fixture, not the committed corpus, and a widened pattern that swept them up would have made the
    rule unusable in exactly the directory it was widened to cover."""
    assert not _reaches_the_log('store = tmp_path / "corrections.jsonl"')
    assert not _reaches_the_log('path = tmp_path / "machine" / "corrections.jsonl"')


@pytest.mark.req("REQ-GATE-0009")
def test_addressing_the_corrections_dir_for_something_else_is_not_a_corpus_read():
    """The other over-match to stay clear of. `data/corrections/` also holds the reviewed ledger and
    the tuner's proposals, and every gate CLI defaults `--store` to that directory before handing it
    to `train.blunder.store` — which is the contract being followed, not broken."""
    assert not _reaches_the_log('ap.add_argument("--store", default=str(REPO / "data" / "corrections"))')
    assert not _reaches_the_log('REPO / "data" / "corrections" / "reviewed.json"')
    assert not _reaches_the_log('prop_out = REPO / "data" / "corrections" / "tuner" / f"{agent}.json"')


@pytest.mark.req("REQ-GATE-0009")
def test_naming_the_log_to_a_subprocess_is_not_reaching_it():
    """The real over-match the widening turned up, kept as a case rather than an exemption.

    `tests/label/test_category.py` hands `"data/corrections/machine/corrections.jsonl"` to
    `git check-ignore` to prove the machine store stays untracked. It never opens the file. Flagging
    it would have forced a correct assertion onto an allowlist — restarting the decay that removing
    the allowlist was meant to end. So the slash-string spelling only counts when the same line also
    builds or opens the path."""
    assert not _reaches_the_log(
        'out = subprocess.run(["git", "check-ignore", "data/corrections/machine/corrections.jsonl"],')
    assert _reaches_the_log(
        'rec = Path("data/corrections/mega_starmie_20260627_93a70be/corrections.jsonl").read_text()')


@pytest.mark.req("REQ-GATE-0009")
def test_constructing_records_is_not_enough_the_layout_is_the_stores_too():
    """`tools/sim/score_diff.py` was the near-miss worth asserting on: it CONSTRUCTED its records
    through `load_corrections` — decision 1 satisfied — while still `rglob`-ing for the files itself.
    That is a second idea of what the corpus *is*, one level below the second idea of what a *record*
    is, and it is the shape a future reader is most likely to get half-right. Both halves come from
    the store: `jsonl_files` for where, `load_corrections` for what."""
    text = (REPO / "tools/sim/score_diff.py").read_text(encoding="utf-8")
    assert "jsonl_files" in text and not _reaches_the_log(text)


@pytest.mark.req("REQ-GATE-0009")
def test_the_shared_test_helper_is_the_one_door_for_tests():
    """Eleven near-identical private loaders became one. Asserted so a twelfth is a deliberate act:
    the helper exists precisely so that routing a new corpus test is easier than re-inventing a walk,
    which is the only durable way an enforcement like this stays green."""
    text = (REPO / "tests" / "corpus_helpers.py").read_text(encoding="utf-8")
    assert "keyed_corrections" in text and not _reaches_the_log(text)
