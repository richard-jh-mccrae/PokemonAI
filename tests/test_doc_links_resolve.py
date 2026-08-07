"""A Markdown link in a committed doc must point at a file that exists.

The 2026-08-07 documentation audit found 283 file references across the repo that resolve to nothing.
Most turned out to be legitimate: `pilot.py:10055` names ``tools/train/probes/deny_gate217.py`` and
says in the same breath that Issue #243 deleted it, which is accurate prose about a dead thing. Policing
every backticked filename would therefore fail on correct writing.

A **link target** is different. Nobody writes a tombstone as a hyperlink — a link is a navigational
promise, so a broken one is always a defect. That makes it the one file-reference claim worth asserting,
and it is cheap: 997 targets across the repo, 34 of them broken when this landed.

The failures are the ordinary kind: ADR cross-links naming a title that was later renamed
(`0031-the-turn-planner.md` for what is really `0031-turn-planner-is-goal-directed-...`), links into a
`demos/` directory that no longer exists, and `../plans/ml-training-build.md` after that file moved into
`plans/ml/`.

Scope notes:

* Targets must look like paths — containing `/` or a suffix. Bare `[x](plan)` is prose, not a link.
* `.claude/skills/` is excluded: the vendored Matt Pocock skills ship template placeholders
  (`./src/ordering/CONTEXT.md`) that are examples, not references into this repo.
* Gitignored trees (`data/meta/`, `reports/`) are excluded — absent locally, present in a real run.
* The scan set is `git ls-files`, never a filesystem walk. `tests/test_import_hygiene.py` documents
  why at length: `.venv/` and `.claude/worktrees/` otherwise pull in other branches' files and the
  guard reports a foreign checkout's defect as this tree's.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_SKIP_TARGET = ("http://", "https://", "mailto:", "#", "<")

#: `path/to/file.py:26` is the repo's own clickable convention; the line number is not part of the path.
_LINE_SUFFIX = re.compile(r":\d+$")

#: Excluded from `.gitignore`, so they are absent here and present in a real run.
_GITIGNORED = ("data/meta/", "reports/", "data/probe/", "data/strategy/raw/", "data/strategy/transcripts/")

#: Vendored external skills carry example paths for a fictional repo, not references into this one.
_VENDORED = ".claude/skills/"

_CONTROL_LIVE = "docs/rules.md"
_CONTROL_DEAD = "docs/this-doc-does-not-exist.md"


def _tracked() -> list[str]:
    if GIT is None:
        pytest.skip("git unavailable; cannot determine the scan set")
    out = subprocess.run(
        [GIT, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, encoding="utf-8", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return [p.replace("\\", "/") for p in out.splitlines() if (REPO / p).is_file()]


def _resolves(doc: str, target: str) -> bool:
    """A target resolves relative to its own document first, then to the repo root."""
    bare = _LINE_SUFFIX.sub("", target.split("#")[0].split("?")[0])
    if not bare:
        return True
    if (REPO / doc).parent.joinpath(bare).exists():
        return True
    return (REPO / bare.lstrip("./")).exists()


def _is_path_like(target: str) -> bool:
    bare = _LINE_SUFFIX.sub("", target.split("#")[0])
    return "/" in bare or bool(Path(bare).suffix)


def _broken(tracked: list[str]) -> list[str]:
    out: list[str] = []
    for rel in tracked:
        if not rel.endswith(".md") or rel.startswith(_VENDORED):
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for match in _LINK.finditer(line):
                target = match.group(1)
                if target.startswith(_SKIP_TARGET) or not _is_path_like(target):
                    continue
                if any(target.lstrip("./").startswith(g) for g in _GITIGNORED):
                    continue
                if not _resolves(rel, target):
                    out.append(f"{rel}:{number} -> {target}")
    return out


def test_the_resolver_accepts_a_real_path_and_rejects_an_invented_one() -> None:
    """A negative result needs a positive control: an always-false resolver would pass this file silently."""
    assert _resolves("docs/ci.md", _CONTROL_LIVE), "positive control failed — the resolver cannot see a real file"
    assert _resolves("docs/adr/README.md", "../rules.md"), "positive control failed — relative resolution is broken"
    assert _resolves("docs/ci.md", "src/common/pilot.py:399"), "positive control failed — the file:line form is broken"
    assert not _resolves("docs/ci.md", _CONTROL_DEAD), "negative control failed — the resolver accepts anything"


def test_every_markdown_link_points_at_a_file_that_exists() -> None:
    broken = _broken(_tracked())
    assert not broken, (
        f"{len(broken)} Markdown links point at files that do not exist. A link is a navigational\n"
        "promise; if the target is gone, drop the link rather than leaving it dangling.\n  "
        + "\n  ".join(broken)
    )
