"""Prose in `src/` may not name a Hypothesis id that no longer exists, unless the ledger says where it went.

The 2026-08-07 documentation audit read 6,471 comments and docstrings and found 194 confirmed false
claims. The largest single family was prose naming a deleted rung: `pilot.py:399` says a field "Gates
``grab-what-i-can-play-now``" and no such Hypothesis exists anywhere in the repo; `pilot.py:458` names
``hold-line-piece-dont-shuffle``, retired 2026-07-18 by ADR-0065, on a `Board` field nothing reads.

Those are cheap to detect and nothing was detecting them. A Hypothesis id is a kebab-case string in an
`id=` kwarg, so the live set is exactly harvestable, and a backticked kebab token in a comment is exactly
a claim about it. This test closes the loop: live, or ledgered, or red.

Scope is `src/**/*.py` — the implementation, where a wrong comment does the most damage because it is
read next to the code it lies about. Markdown is deliberately out of scope for now: 119 further dead ids
live only in docs, and most of those files are already on the audit's delete list, so policing them
before the reduction pass would fail on files that are about to disappear.

Prior art for the shape: `tests/test_import_hygiene.py` (a repo invariant asserted straight off the
filesystem, scanned via `git ls-files` rather than a walk) and `tests/test_adr_index.py` (a known gap
carried as data with its reason so a NEW one fails).
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from retired_rung_ids import MAX_RETIRED, RETIRED

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")

#: Three or more segments, so ordinary hyphenated English in prose ("closed-form", "engine-verified")
#: cannot trip the scan. Two-segment ids do not exist in the shipped set.
_KEBAB = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+){2,})`")

_CONTROLS_LIVE = ("use-acceleration", "dig-before-commit", "prefer-rush-evolve-tutor")
_CONTROL_DEAD = "this-rung-was-never-real"


def _tracked() -> list[str]:
    if GIT is None:
        pytest.skip("git unavailable; cannot determine the scan set")
    out = subprocess.run(
        [GIT, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, encoding="utf-8", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return [p.replace("\\", "/") for p in out.splitlines() if (REPO / p).is_file()]


def _live_strings(tracked: list[str]) -> set[str]:
    """Every string constant reachable in `src/` — the authoritative set of names that still exist."""
    live: set[str] = set()

    def eat(obj: object) -> None:
        if isinstance(obj, str):
            live.add(obj)
        elif isinstance(obj, dict):
            for key, value in obj.items():
                live.add(key)
                eat(value)
        elif isinstance(obj, list):
            for value in obj:
                eat(value)

    for rel in tracked:
        if not rel.startswith("src/"):
            continue
        path = REPO / rel
        if rel.endswith(".py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    live.add(node.value)
        elif rel.endswith(".json"):
            try:
                eat(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    return live


def _mentions(tracked: list[str], live: set[str], stems: set[str]) -> dict[str, list[str]]:
    """Backticked kebab tokens in `src/**/*.py` that resolve to nothing, keyed to their sites."""
    found: dict[str, list[str]] = defaultdict(list)
    for rel in tracked:
        if not (rel.startswith("src/") and rel.endswith(".py")):
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for match in _KEBAB.finditer(line):
                token = match.group(1)
                if token in live or token in stems:
                    continue
                found[token].append(f"{rel}:{number}")
    return dict(found)


@pytest.fixture(scope="module")
def scan() -> tuple[set[str], dict[str, list[str]]]:
    tracked = _tracked()
    live = _live_strings(tracked)
    stems = {Path(rel).stem for rel in tracked}
    return live, _mentions(tracked, live, stems)


def test_the_harvest_finds_live_ids_and_not_invented_ones(scan) -> None:
    """A negative result needs a positive control: prove the instrument can see a rung before trusting a miss."""
    live, _ = scan
    missing = [control for control in _CONTROLS_LIVE if control not in live]
    assert not missing, (
        f"positive control failed — {missing} should be live Hypothesis ids. "
        "The harvest is broken, so every 'dead id' this module reports is meaningless."
    )
    assert _CONTROL_DEAD not in live, "negative control failed — the harvest is matching anything"


def test_every_retired_id_names_a_module_that_explains_it(scan) -> None:
    """The ledger's value is the redirect, so a pointer that does not mention the id is worse than none."""
    live, _ = scan
    broken = []
    for rung, owner in RETIRED.items():
        path = REPO / owner
        if not path.is_file():
            broken.append(f"{rung}: owner {owner} does not exist")
        elif rung not in path.read_text(encoding="utf-8", errors="replace"):
            broken.append(f"{rung}: owner {owner} never mentions it")
    assert not broken, "ledger pointers must resolve:\n  " + "\n  ".join(broken)


def test_no_source_comment_names_a_rung_that_does_not_exist(scan) -> None:
    live, dead = scan
    unledgered = {rung: sites for rung, sites in dead.items() if rung not in RETIRED}
    assert not unledgered, (
        "prose in src/ names Hypothesis ids that do not exist and are not in the retirement ledger.\n"
        "Either the rung is live (then this test is wrong), or the prose is stale — DELETE it. Add to\n"
        "tests/retired_rung_ids.py only when the mention is a deliberate tombstone.\n  "
        + "\n  ".join(f"{rung}: {', '.join(sites[:4])}" for rung, sites in sorted(unledgered.items()))
    )


def test_the_ledger_carries_no_entry_that_is_no_longer_needed(scan) -> None:
    """A ledger that only grows becomes the backlog it was meant to prevent."""
    live, dead = scan
    stale = sorted(set(RETIRED) - set(dead))
    assert not stale, (
        "these ids are no longer named by any src/ comment (or have come back to life), so their\n"
        "ledger entries are dead weight — delete them from tests/retired_rung_ids.py:\n  "
        + "\n  ".join(stale)
    )


def test_the_ledger_only_shrinks() -> None:
    assert len(RETIRED) <= MAX_RETIRED, (
        f"the retirement ledger grew to {len(RETIRED)} against a ceiling of {MAX_RETIRED}. "
        "Stale prose should be deleted, not registered."
    )
