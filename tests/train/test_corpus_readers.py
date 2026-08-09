"""**One Corpus Reader** — the contract, ENFORCED (ADR-0087 decision 4; widened by ADR-0089).

The Decision Gate lost 40 records and mis-keyed 163 more because it kept a private raw-JSONL walk
instead of constructing Corrections. Issue #241 shipped an allowlist; Issue #243 paid that queue to
empty, so the dict is gone — a work queue kept past its work becomes permanent exemptions.

The rule now forbids **reaching the corrections log**, not one spelling of it, across ``tools/``
**and** ``tests/``. Both original bounds were occupied: nine files under ``tests/strategy/`` globbed
the corpus, and two more named a build directory outright — which no glob pattern can see, and which
breaks silently the day that directory is renamed.

The prose guard below is load-bearing for the same reason it always was: a check that cannot tell a
mention from a read trains people to widen the exemption, which is how an allowlist dies.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]

#: The store module IS the reader — it is the one place allowed to open the files.
_READER_HOME = "tools/train/blunder/store.py"

#: This file names every forbidden shape in its own source, so it must exempt itself.
_SELF = "tests/train/test_corpus_readers.py"

#: A glob/rglob of the log. The shape Issue #241 enforced against.
_GLOB_RE = re.compile(r"""(?:r?)glob\(\s*["'][^"']*corrections\.jsonl["']""")

#: A FIXED path that reaches the log. Deliberately requires the `data`/`corrections` segments AND
#: the filename on one line, so the ledger, the tuner dir and a `--store` default are not flagged.
_FIXED_PATH_RE = re.compile(
    r"""["']data["']\s*/\s*["']corrections["'][^\n]*corrections\.jsonl""")

#: The slash-string spelling. Only counts when the line also BUILDS or OPENS the path, because
#: naming that string is not always reaching it — one test hands it to `git check-ignore`.
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
    """The widening, asserted directly rather than left implicit in an empty offender list: a hardcoded
    build directory is arguably WORSE than a glob, since it also breaks silently on a rename."""
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
    """ADR-0089's disposition table as an assertion — a probe reappearing under a deleted name means a
    ruling was reverted without one being recorded. A RULING's script dies with its answer."""
    probes = REPO / "tools" / "train" / "probes"
    for gone in ("deploy_decider_sweep", "deny_gate1", "deny_gate217", "deploy_anchor_sweep"):
        assert not (probes / f"{gone}.py").exists(), f"{gone} was deleted by Issue #243"
    for gone in ("needs_sweep", "threat_sweep", "doom_audit"):
        assert not (probes / f"{gone}.py").exists(), f"{gone} was deleted by Issue #261 item 2h"
    for kept in ("attach_decider_sweep", "evolve_decider_sweep", "promote_retreat_decider_sweep",
                 "snipe_decider_sweep"):
        assert (probes / f"{kept}.py").exists(), kept


@pytest.mark.req("REQ-GATE-0009")
def test_modules_that_only_mention_the_log_in_prose_are_not_flagged():
    """The check targets a read, not the filename: a module can name the log in its docstring and never
    open it, and a check that could not tell those apart would train people to route around it."""
    rel = "tools/train/blunder_report.py"
    text = (REPO / rel).read_text(encoding="utf-8")
    assert _MENTION_RE.search(text)                 # it does name the log...
    assert not _reaches_the_log(text)               # ...and does not reach it


@pytest.mark.req("REQ-GATE-0009")
def test_a_synthetic_tmp_path_store_is_not_a_corpus_read():
    """Fourteen files build a synthetic store under `tmp_path`. That is a fixture, not the committed
    corpus, and a widened pattern sweeping them up would make the rule unusable."""
    assert not _reaches_the_log('store = tmp_path / "corrections.jsonl"')
    assert not _reaches_the_log('path = tmp_path / "machine" / "corrections.jsonl"')


@pytest.mark.req("REQ-GATE-0009")
def test_addressing_the_corrections_dir_for_something_else_is_not_a_corpus_read():
    """That directory also holds the reviewed ledger and the tuner's proposals, and every gate CLI
    defaults `--store` to it before handing it to `train.blunder.store` — the contract, not a breach."""
    assert not _reaches_the_log('ap.add_argument("--store", default=str(REPO / "data" / "corrections"))')
    assert not _reaches_the_log('REPO / "data" / "corrections" / "reviewed.json"')
    assert not _reaches_the_log('prop_out = REPO / "data" / "corrections" / "tuner" / f"{agent}.json"')


@pytest.mark.req("REQ-GATE-0009")
def test_naming_the_log_to_a_subprocess_is_not_reaching_it():
    """The real over-match the widening turned up, kept as a case rather than an exemption: naming the
    log to a subprocess never opens it, so the slash spelling counts only when the line builds it too."""
    assert not _reaches_the_log(
        'out = subprocess.run(["git", "check-ignore", "data/corrections/machine/corrections.jsonl"],')
    assert _reaches_the_log(
        'rec = Path("data/corrections/mega_starmie_20260627_93a70be/corrections.jsonl").read_text()')


@pytest.mark.req("REQ-GATE-0009")
def test_constructing_records_is_not_enough_the_layout_is_the_stores_too():
    """`tools/sim/score_diff.py` CONSTRUCTED its records through `load_corrections` while still
    `rglob`-ing for the files itself — a second idea of what the corpus IS, one level below a record."""
    text = (REPO / "tools/sim/score_diff.py").read_text(encoding="utf-8")
    assert "jsonl_files" in text and not _reaches_the_log(text)


@pytest.mark.req("REQ-GATE-0009")
def test_the_shared_test_helper_is_the_one_door_for_tests():
    """Eleven near-identical private loaders became one, asserted so a twelfth is a deliberate act:
    routing a new corpus test must stay easier than re-inventing a walk."""
    text = (REPO / "tests" / "corpus_helpers.py").read_text(encoding="utf-8")
    assert "keyed_corrections" in text and not _reaches_the_log(text)


@pytest.mark.req("REQ-GATE-0009")
def test_static_corpus_reads_exclude_regenerable_machine_labels(monkeypatch):
    """A label run may create ignored ``machine/`` output during pytest; static census pins may not
    inherit it, while the operational reader deliberately still can."""
    import corpus_helpers

    human = SimpleNamespace(provenance="human")
    machine = SimpleNamespace(provenance="machine")

    def fake_reader(_store, *, predicate=None):
        return [("human", human), ("machine", machine)] if predicate is None else [
            (key, correction) for key, correction in (("human", human), ("machine", machine))
            if predicate(correction)]

    monkeypatch.setattr(corpus_helpers, "keyed_corrections", fake_reader)
    assert corpus_helpers.committed_keyed_corrections() == [("human", human)]
