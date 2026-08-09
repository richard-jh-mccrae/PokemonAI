"""The registries in `tools/rung_registry.py` must describe the repo that exists, not the one that was.

Every leg is asserted here, because an entry nothing verifies is a false claim that now looks
authoritative. The unverifiable leg is `note`, which is why it is capped at one line.

* The resolver needs its own controls: `getattr` chains fail quietly, and a `default_factory`
  dataclass field is invisible to `getattr` alone — both reachable shapes get one.
* `FOLDED` is PERMANENT (pruning it would destroy the records it preserves); what shrinks is the
  `MAX_MENTIONS` ratchet. `NOT_A_RUNG` only protects a mention, so an entry with no mention IS dead.
* `_mentions` sees only BACKTICKED tokens, so `_bare_mentions` rescans the registered retired ids
  bare — the prose fold maps wrote their ids bare and were invisible to the ratchet.
* An id-keyed frozenset is a CONSUMER: a stale id can never match, and it also reads as LIVE to
  `_live_strings`, suppressing the dead-id alarm on the prose naming it.
"""
from __future__ import annotations

import ast
import importlib
import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from tools.rung_registry import (DECIDERS, EMERGENT, FOLDED, MAX_MENTIONS, NOT_A_RUNG, REVERTED, SUBSUMED,
                                 LEGACY_DECK_RUNTIME_RUNG_IDS, SHARED_RUNTIME_RETIRED, UNRECORDED, UNREPLACED)

REPO = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")

#: Three or more segments, so ordinary hyphenated English in prose ("closed-form", "engine-verified")
#: cannot trip the scan. Two-segment ids do not exist in the shipped set.
_KEBAB = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+){2,})`")

_SENTINELS = {EMERGENT, SUBSUMED, REVERTED, UNRECORDED, UNREPLACED}
#: One live id from each of three DIFFERENT modules, so deleting any one cluster cannot silently
#: retire the whole control.
_CONTROLS_LIVE = ("dont-search-an-empty-deck", "fire-lunar-cycle", "bench-the-comeback-drawer")
_CONTROL_DEAD = "this-rung-was-never-real"
_CONTROL_SYMBOL_ABSENT = "common.pilot:Pilot._this_method_was_never_written"
_MAX_NOTE = 120


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


def _live_hypothesis_ids(tracked: list[str]) -> set[str]:
    ids: set[str] = set()
    for rel in tracked:
        if not (rel.startswith("src/") and rel.endswith(".py")):
            continue
        try:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "Hypothesis":
                continue
            ids |= {keyword.value.value for keyword in node.keywords
                    if keyword.arg == "id" and isinstance(keyword.value, ast.Constant)}
    return ids


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
                if token not in live and token not in stems:
                    found[token].append(f"{rel}:{number}")
    return dict(found)


def _bare_mentions(tracked: list[str]) -> dict[str, list[str]]:
    """Sites naming a REGISTERED retired id, backticked or not — an exact scan, so no regex guessing.
    See the module docstring for why the backticked scan alone was blind to the prose fold maps."""
    patterns = {rung: re.compile(rf"(?<![a-z0-9-]){re.escape(rung)}(?![a-z0-9-])") for rung in FOLDED}
    found: dict[str, list[str]] = defaultdict(list)
    for rel in tracked:
        if not (rel.startswith("src/") and rel.endswith(".py")):
            continue
        for number, line in enumerate((REPO / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for rung, pattern in patterns.items():
                if pattern.search(line):
                    found[rung].append(f"{rel}:{number}")
    return dict(found)


def _resolves(target: str) -> bool:
    """True when `module:Qual.name` names something that exists; import errors are failures. The
    `__dataclass_fields__` fallback catches a `default_factory` field, which is not a class attribute."""
    module_name, _, attribute_path = target.partition(":")
    try:
        obj = importlib.import_module(module_name)
    except ImportError:
        return False
    for attribute in attribute_path.split("."):
        if attribute in getattr(obj, "__dataclass_fields__", ()):
            obj = obj.__dataclass_fields__[attribute]
            continue
        obj = getattr(obj, attribute, None)
        if obj is None:
            return False
    return True


def _adr_exists(number: str) -> bool:
    return any(REPO.joinpath("docs/adr").glob(f"{number}-*.md"))


@pytest.fixture(scope="module")
def scan() -> tuple[set[str], dict[str, list[str]], dict[str, list[str]]]:
    tracked = _tracked()
    live = _live_strings(tracked)
    stems = {Path(rel).stem for rel in tracked}
    return live, _mentions(tracked, live, stems), _bare_mentions(tracked)


def test_the_harvest_finds_live_ids_and_not_invented_ones(scan) -> None:
    """A negative result needs a positive control: prove the instrument can see a rung before trusting a miss."""
    live = _live_hypothesis_ids(_tracked())
    missing = [control for control in _CONTROLS_LIVE if control not in live]
    assert not missing, (
        f"positive control failed — {missing} should be live Hypothesis ids. "
        "The harvest is broken, so every 'dead id' this module reports is meaningless."
    )
    assert _CONTROL_DEAD not in live, "negative control failed — the harvest is matching anything"


def test_the_resolver_rejects_a_symbol_that_does_not_exist() -> None:
    """Same discipline for the resolver: a `getattr` chain that never fails would pass every entry.
    Both reachable shapes get a control — see the module docstring."""
    assert _resolves("common.pilot:Pilot._attach_value"), "positive control failed — the resolver sees no method"
    assert _resolves("common.strategy.strategy:Strategy.starter_priority"), (
        "positive control failed — the resolver sees no default_factory dataclass field"
    )
    assert not _resolves(_CONTROL_SYMBOL_ABSENT), "negative control failed — the resolver accepts anything"
    assert not _resolves("common.strategy.strategy:Strategy.no_such_field"), (
        "negative control failed — the __dataclass_fields__ fallback accepts anything"
    )


def test_every_fold_destination_exists(scan) -> None:
    """The whole value of a fold entry is the redirect. One that points nowhere is worse than no entry."""
    live = _live_hypothesis_ids(_tracked())
    broken = []
    for rung, fold in FOLDED.items():
        if fold.into in _SENTINELS:
            continue
        if ":" in fold.into:
            if not _resolves(fold.into):
                broken.append(f"{rung}: symbol {fold.into} does not resolve")
        elif fold.into not in live:
            broken.append(f"{rung}: {fold.into} is not a live rung id either")
    assert not broken, (
        "fold destinations must resolve — a moved or renamed symbol means the entry needs updating,\n"
        "not deleting (the rung is still retired):\n  " + "\n  ".join(broken)
    )


def test_every_recorded_adr_exists() -> None:
    missing = sorted(
        f"{name}: ADR-{record.adr}"
        for name, record in list(FOLDED.items()) + list(DECIDERS.items())
        if record.adr and not _adr_exists(record.adr)
    )
    assert not missing, (
        "these registry entries cite an ADR with no file under docs/adr/. Use \"\" when nothing records\n"
        "the decision rather than citing a number that does not exist:\n  " + "\n  ".join(missing)
    )


def test_every_decider_seam_resolves_and_names_a_real_kill_switch() -> None:
    """The index a new issue reads first. A wrong owner sends the next build to the wrong file."""
    from common.runtime import PROFILE

    broken = []
    for seam, decider in DECIDERS.items():
        if not _resolves(decider.owner):
            broken.append(f"{seam}: owner {decider.owner} does not resolve")
        if decider.flag and decider.flag not in PROFILE:
            broken.append(f"{seam}: flag {decider.flag!r} is not a runtime.PROFILE key")
    assert not broken, "the decider index must describe the shipped build:\n  " + "\n  ".join(broken)


def test_no_id_keyed_set_names_a_hypothesis_that_does_not_exist() -> None:
    """A frozenset of rung ids is a CONSUMER, and one keyed on a dead id is inert config nothing reports.
    `planner._CLASS_B_SPEND_IDS` held seven — see the module docstring for what that masked."""
    authored: set[str] = set()
    consumers: dict[str, set[str]] = {}
    for rel in _tracked():
        if not (rel.startswith("src/") and rel.endswith(".py")):
            continue
        try:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Hypothesis":
                for keyword in node.keywords:
                    if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                        authored.add(keyword.value.value)
        # Discovered, not hardcoded: a third consumer set added later must be gated too, and a list of
        # two names would have gone silently narrow. `HYPOTHESES` is the DEFINITION site, not a consumer.
        for node in tree.body:
            name = getattr(node.targets[0], "id", "") if isinstance(node, ast.Assign) else ""
            if not name.isupper() or name == "HYPOTHESES":
                continue
            strings = {c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
            if strings:
                consumers[f"{rel}::{name}"] = strings

    assert "dont-search-an-empty-deck" in authored, "positive control failed — no Hypothesis ids were harvested"
    consumers = {where: ids for where, ids in consumers.items() if ids & authored}
    assert consumers, "positive control failed — no id-keyed consumer set was discovered at all"
    inert = sorted(f"{where}: {sorted(ids - authored)}" for where, ids in consumers.items() if ids - authored)
    assert not inert, (
        "these id-keyed sets name Hypotheses that do not exist, so the entries can never match and the\n"
        "consumer silently loses the term:\n  " + "\n  ".join(inert)
    )


def test_no_source_comment_names_a_rung_that_does_not_exist(scan) -> None:
    live, dead, _bare = scan
    unregistered = {rung: sites for rung, sites in dead.items() if rung not in FOLDED and rung not in NOT_A_RUNG}
    assert not unregistered, (
        "prose in src/ names Hypothesis ids that do not exist and are not registered.\n"
        "Either the rung is live (then this test is wrong), or the prose is stale — DELETE it. Add to\n"
        "FOLDED only when the mention is a deliberate tombstone, and to NOT_A_RUNG only when the token\n"
        "was never a rung at all.\n  "
        + "\n  ".join(f"{rung}: {', '.join(sites[:4])}" for rung, sites in sorted(unregistered.items()))
    )


def test_no_folded_rung_has_come_back_to_life(scan) -> None:
    """`FOLDED` is PERMANENT — deliberately not pruned when the last mention goes (module docstring).
    The one real error is a LIVE rung claiming to be folded: the fold was reverted, or the id reused."""
    live = _live_hypothesis_ids(_tracked())
    resurrected = sorted(set(FOLDED) & live)
    assert not resurrected, (
        "these ids are registered as retired but are live Hypothesis ids again. A reused id silently\n"
        "inherits a retirement record that is now false:\n  " + "\n  ".join(resurrected)
    )


def test_not_a_rung_carries_no_entry_that_is_no_longer_needed(scan) -> None:
    """`NOT_A_RUNG` exists only to protect a MENTION, so an entry with no mention left is dead weight."""
    live, dead, _bare = scan
    stale = sorted(set(NOT_A_RUNG) - set(dead))
    assert not stale, (
        "these tokens are no longer named by any src/ comment, so the protection is moot — delete them\n"
        "from NOT_A_RUNG in tools/rung_registry.py:\n  " + "\n  ".join(stale)
    )


def test_no_id_is_both_folded_and_not_a_rung() -> None:
    """The two dicts answer contradictory questions, so an id in both makes the registry say both."""
    overlap = sorted(set(FOLDED) & set(NOT_A_RUNG))
    assert not overlap, f"registered as both a retired rung and never-a-rung: {overlap}"


def test_shared_runtime_retirements_are_globally_folded() -> None:
    """Issue #459 retires every listed shared valuation, not only the Kaggle package view."""
    from common.strategy.general_strategy import GENERAL_STRATEGY

    general = {hypothesis.id for hypothesis in GENERAL_STRATEGY.hypotheses}
    assert SHARED_RUNTIME_RETIRED <= set(FOLDED)
    assert not general & SHARED_RUNTIME_RETIRED


def test_retained_third_deck_rungs_match_the_declared_out_of_competition_scope() -> None:
    # `kaggle_environments` has its own top-level `agents` module in CI, so load the actual
    # strategies through the same shipped builder used by runtime code.
    from train.tune import _build_pilot

    lucario = _build_pilot("mega_lucario")[0].strategy
    dragapult = _build_pilot("dragapult_ex")[0].strategy

    assert {hypothesis.id for hypothesis in lucario.hypotheses} == LEGACY_DECK_RUNTIME_RUNG_IDS["mega_lucario"]
    assert {hypothesis.id for hypothesis in dragapult.hypotheses} == LEGACY_DECK_RUNTIME_RUNG_IDS["dragapult_ex"]


def test_notes_stay_one_readable_line() -> None:
    """A note that grows into a paragraph is the prose fold map coming back through the registry."""
    over = sorted(
        f"{rung}: {len(fold.note)} chars"
        for rung, fold in FOLDED.items()
        if len(fold.note) > _MAX_NOTE or "\n" in fold.note
    )
    assert not over, (
        f"fold notes must be one line of at most {_MAX_NOTE} chars — the reasoning belongs in the ADR:\n  "
        + "\n  ".join(over)
    )


def test_the_stale_mention_count_only_shrinks(scan) -> None:
    """The ratchet is on SITES, not entries — a tombstone is legitimate, but this many is prose nobody re-read."""
    live, _dead, bare = scan
    total = sum(len(sites) for sites in bare.values())
    assert total <= MAX_MENTIONS, (
        f"src/ prose now names retired rungs at {total} sites against a ceiling of {MAX_MENTIONS}. "
        "Stale prose should be deleted, not registered."
    )
