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
from pathlib import Path

import pytest

from common import apply_option as seam
from seam_census_helpers import census_pool, load_census

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def census():
    """The census plus its pool. The by-path load lives in `tests/seam_census_helpers.py` so the two
    modules that assert against the census share one loader (see Issue #305)."""
    mod, cards, effects, covers = load_census()
    return mod, cards, effects, covers, census_pool(mod)


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


def test_the_engine_route_is_reached_per_option_not_per_kind(census):
    """The report's finding 1, as an executable claim — **inverted by Issue #299's ruling**, which
    this test existed to make visible.

    It used to assert `_ABILITY` was the sole engine-route kind. That was the defect: the bridge was
    pointed at the one kind whose live population is all deck-reading draw engines, so it resolved
    ZERO live options, while deterministic-shaped sites on MODELLED kinds had nowhere to be sent.
    Since the ruling the gate is the per-option proof, so the assertion is the opposite one — the
    route must be reached from MODELLED kinds too, or the ruling did not land.

    `ENGINE_ROUTE_KINDS` is deliberately still `{_ABILITY}`: the ruling promoted and demoted no kind
    (the composer's pruning depends on `KIND_COVERAGE`), it stopped the table from being the gate."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    from common.strategy.context import _ABILITY, _PLAY
    assert seam.ENGINE_ROUTE_KINDS == frozenset({_ABILITY})    # the TABLE is unmoved, on purpose
    reached = {s.kind for s in sites if s.fate == seam.ENGINE_RESOLVED}
    assert _PLAY in reached, "no `_PLAY` reaches the engine route — Issue #299's ruling is not wired"
    assert reached - {_ABILITY}, "only `_ABILITY` reaches it, which is the pre-ruling behaviour"
    assert reached <= set(seam.KIND_COVERAGE) - seam.TERMINAL_KINDS


def test_a_partial_clause_set_no_longer_resolves_to_MODELLED(census):
    """Issue #300 declared the `_covers: partial` verdict; Issue #299 wired it into `fate`. The join
    that matters is that the census AGREES: a site the compendium calls partial must not carry the
    MODELLED fate, or the report would still be counting a silent zero as coverage.

    Positive control in the same assertion: the partial set must be non-empty, otherwise this passes
    vacuously on a census that produced no partial sites at all."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    partial = [s for s in sites if s.report_class == mod.PARTIAL]
    assert partial, "no MODELLED-PARTIAL sites at all — the assertion below would be vacuous"
    assert not [s for s in partial if s.fate == seam.MODELLED], (
        [(s.card_id, s.name) for s in partial if s.fate == seam.MODELLED])


def test_the_census_asks_the_seam_for_the_fate_rather_than_re_deriving_it(census):
    """One store for the resolution order (Issue #299). The census used to mirror `fate`'s cascade by
    hand, because `fate` demanded two inputs nothing produces; now it supplies those judgements and
    calls the function, so the report cannot claim a fate the seam would not return.

    Asserted by re-driving every site through `seam.fate` with the census's own inputs — an
    independent recomputation, not a re-read of what `resolve` stored."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    for s in sites:
        want = seam.fate({"type": s.kind}, depth=0, search_api=mod._ENGINE_SEAM,
                         deterministic=not mod.refusal_cause(s.text, rng_refuses=True),
                         clauses_cover=mod.clauses_cover(s, covers))
        assert s.fate == want, (s.card_id, s.name, s.label, s.fate, want)


def _report_text() -> str:
    return (_ROOT / "docs" / "plans" / "apply-seam-coverage.md").read_text(encoding="utf-8")


def _partial_rows(text: str) -> dict[int, str]:
    """``{card id: what the clauses miss}`` parsed out of the COMMITTED report's MODELLED-PARTIAL
    table. Read as text, so this is a genuinely independent record of the ruling — a second committed
    artifact to join the compendium against, rather than the census's own return value.

    Keyed off the LAST cell rather than a fixed index: the table grew a `fate now` column in Issue
    #299 (a partial set no longer resolves to MODELLED, so where it lands is worth printing), and a
    parser pinned to column 4 would have silently joined the wrong field."""
    section = text.split("### MODELLED-PARTIAL")[1].split("\n### ")[0]
    rows: dict[int, str] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].isdigit():
            rows[int(cells[0])] = cells[-1]
    return rows


def test_the_completeness_ruling_has_exactly_one_store(census):
    """Issue #300's structural half. The census used to carry its own `CLAUSE_JUDGEMENT` table beside
    the compendium's — two records of one ruling, which is the second loader ADR-0087 charges for:
    they drift, and every diff that could show it reads only one side.

    Walked from the REPORT's committed text to the compendium, deliberately. Comparing the census's
    own `Site.report_class` against the `covers` dict it was just built from could never fail — a
    join asserted from the side that built it is vacuous by construction, and this repo has already
    paid for that lesson once (Issue #250)."""
    mod, _cards, _effects, covers, _pool = census
    assert not hasattr(mod, "CLAUSE_JUDGEMENT"), "the ruling is back in the script — one store"
    rows = _partial_rows(_report_text())
    assert rows, "parsed no MODELLED-PARTIAL rows out of the report — the join would be vacuous"
    for cid, missing in rows.items():
        assert cid in covers, f"card {cid} is PARTIAL in the report and unruled in the compendium"
        assert covers[cid]["covers"] == "partial", (
            f"card {cid}: report says partial, compendium says {covers[cid]['covers']!r}")
        assert covers[cid]["reason"] == missing, (
            f"card {cid}: the report and the compendium disagree about what the clauses miss")


def test_the_committed_report_is_a_fresh_run_of_the_census(census):
    """The other direction, and the one that catches a compendium edit landing without a re-run: the
    committed generated block must equal what the census produces from today's inputs, byte for byte.

    This is the parent track's standing discipline (*"re-run the census at the end of each
    sub-issue"*) made executable rather than remembered. It also closes the gap the join above cannot
    see — a card that BECAME partial and never reached the report has no row to walk from."""
    mod, cards, effects, covers, pool = census
    sites, aside = mod.census(pool, cards, effects, covers)
    decks = mod.load_our_decks()
    builds, priors = mod.load_opponent_builds()
    fresh = mod.build_report(sites, aside, mod.our_copies(decks), mod.meta_copies(builds, priors),
                             decks, len(builds), mod.load_strategy_names(), cards)
    text = _report_text()
    committed = text[text.index(mod.BEGIN) + len(mod.BEGIN):text.index(mod.END)]
    assert committed.strip() == fresh.strip(), (
        "docs/plans/apply-seam-coverage.md's generated block is stale — re-run "
        "`python tools/apply_seam_coverage.py`")


def test_report_block_is_present_and_regenerable(census, tmp_path):
    """The committed report carries the generated markers, so a re-run refreshes the numbers instead
    of clobbering the authored verdict."""
    mod, _cards, _effects, _covers, _pool = census
    text = (_ROOT / "docs" / "plans" / "apply-seam-coverage.md").read_text(encoding="utf-8")
    assert mod.BEGIN in text and mod.END in text
    assert text.index(mod.BEGIN) < text.index(mod.END)
