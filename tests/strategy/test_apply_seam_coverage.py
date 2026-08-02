"""The POC-A2 coverage census (`tools/apply_seam_coverage.py`, Issue #269) still measures.

The report `docs/plans/apply-seam-coverage.md` is a committed measurement, and a measurement that
silently stops matching its subject is worse than none. Three things can rot it, and each has a test
here:

* a card gains Effect Clauses with no `_covers` ruling in the compendium (Issue #300 moved that
  ruling out of the script and into `card_effects.json`, where the apply seam reads it too) — the
  census would then have to guess whether the clauses cover the whole card, which is the one column
  it must never fabricate;
* a deck or the scouting artifact changes and the pool no longer resolves;
* `apply_option`'s kind table moves, so the fates the report quotes are no longer the fates the seam
  returns.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from common import apply_option as seam

_ROOT = Path(__file__).resolve().parents[2]


def _load():
    """Import the script by path — `tools/` is on `sys.path` (conftest) but the module is a CLI, so
    load it explicitly rather than relying on a package that does not exist."""
    path = _ROOT / "tools" / "apply_seam_coverage.py"
    spec = importlib.util.spec_from_file_location("apply_seam_coverage", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def census():
    mod = _load()
    cards, effects, covers = mod.load_cards(), mod.load_effects(), mod.load_covers()
    decks = mod.load_our_decks()
    builds, _priors = mod.load_opponent_builds()
    pool = set().union(*[set(c) for c in decks.values()], *[set(c) for c in builds.values()])
    return mod, cards, effects, covers, pool


def test_every_clause_bearing_pool_card_has_a_ruling(census):
    """The census's own gate. A new compendium entry with no ruling fails HERE — loudly, in the
    place that can add it — rather than defaulting to FULL and quietly inflating the report."""
    mod, cards, effects, covers, pool = census
    assert mod.validate(pool, cards, effects, covers) == []


def test_sites_resolve_to_declared_fates_only(census):
    """Every site lands on one of §3b's three fates, and on one of the report's four classes."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    assert sites, "the pool produced no apply-seam sites at all"
    for s in sites:
        assert s.fate in seam.FATES, f"{s.name}: fate {s.fate!r}"
        assert s.report_class in (mod.FULL, mod.PARTIAL, seam.ENGINE_RESOLVED, seam.REFUSED)
        if s.fate == seam.REFUSED:
            assert s.cause, f"{s.name}: a refusal must name its cause"


def test_engine_resolved_sites_carry_no_rng_marker(census):
    """The fail-closed direction, asserted rather than trusted: nothing reaches ENGINE-RESOLVED with
    a shuffle / deck-read / coin / reveal / prize marker in its text. The gate is *provably
    deterministic*, and this is the half of the proof the census can check."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    for s in sites:
        if s.fate == seam.ENGINE_RESOLVED:
            assert not mod._hits(s.text, mod._RNG_OR_HIDDEN), s.name
            assert not mod._hits(s.text, mod._OPPONENT_CHOICE), s.name


def test_only_ability_can_reach_the_engine_route(census):
    """The report's finding 1, as an executable claim: `_ABILITY` is the sole engine-route kind, so
    every ENGINE-RESOLVED site is an Ability. If a later ruling widens `ENGINE_ROUTE_KINDS` (the
    report's AMBIGUOUS #1), this fails and the report's verdict needs re-reading."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    from common.strategy.context import _ABILITY
    assert seam.ENGINE_ROUTE_KINDS == frozenset({_ABILITY})
    assert {s.kind for s in sites if s.fate == seam.ENGINE_RESOLVED} <= {_ABILITY}


def test_the_completeness_ruling_has_exactly_one_store(census):
    """Issue #300's structural half. The census used to carry its own `CLAUSE_JUDGEMENT` table beside
    the compendium's — two records of one ruling, which is the second loader ADR-0087 charges for:
    they drift, and every diff that could show it reads only one side.

    Asserted from the OTHER side (the compendium), not from the script's own read: the report's
    MODELLED split is the compendium's verdicts, card for card."""
    mod, cards, effects, covers, pool = census
    assert not hasattr(mod, "CLAUSE_JUDGEMENT"), "the ruling is back in the script — one store"
    sites, _aside = mod.census(pool, cards, effects, covers)
    split = {s.card_id: s.report_class for s in sites
             if s.report_class in (mod.FULL, mod.PARTIAL) and s.clauses}
    assert split, "no clause-bearing site landed on the MODELLED split — vacuous"
    for cid, cls in split.items():
        want = mod.FULL if covers[cid]["covers"] == "full" else mod.PARTIAL
        assert cls == want, f"card {cid}: report says {cls}, compendium says {covers[cid]}"


def test_report_block_is_present_and_regenerable(census, tmp_path):
    """The committed report carries the generated markers, so a re-run refreshes the numbers instead
    of clobbering the authored verdict."""
    mod, _cards, _effects, _covers, _pool = census
    text = (_ROOT / "docs" / "plans" / "apply-seam-coverage.md").read_text(encoding="utf-8")
    assert mod.BEGIN in text and mod.END in text
    assert text.index(mod.BEGIN) < text.index(mod.END)
