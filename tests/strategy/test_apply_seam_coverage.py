"""The POC-A2 coverage census (`tools/apply_seam_coverage.py`, Issue #269) still measures.

`docs/plans/apply-seam-coverage.md` is a committed measurement, and one that silently stops matching
its subject is worse than none. Three things rot it, one test each: a card gains clauses with no
`_covers` ruling; the deck/artifact pool stops resolving; `apply_option`'s kind table moves.
"""
from pathlib import Path

import pytest

from common import apply_option as seam
from seam_census_helpers import census_pool, load_census

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def census():
    mod, cards, effects, covers = load_census()
    return mod, cards, effects, covers, census_pool(mod)


def test_every_clause_bearing_pool_card_has_a_ruling(census):
    """An unruled entry must fail HERE rather than default to FULL and inflate the report."""
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
    """The gate is PROVABLY deterministic; this is the half of that proof the census can check."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    for s in sites:
        if s.fate == seam.ENGINE_RESOLVED:
            assert not mod._hits(s.text, mod._RNG_OR_HIDDEN), s.name
            assert not mod._hits(s.text, mod._OPPONENT_CHOICE), s.name


def test_the_engine_route_is_reached_per_option_not_per_kind(census):
    """Issue #299 made the per-option proof the gate, so MODELLED kinds must reach the route too.
    `ENGINE_ROUTE_KINDS` stays `{_ABILITY}`: the composer's pruning depends on `KIND_COVERAGE`."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    from common.strategy.context import _ABILITY, _PLAY
    assert seam.ENGINE_ROUTE_KINDS == frozenset({_ABILITY})    # the TABLE is unmoved, on purpose
    reached = {s.kind for s in sites if s.fate == seam.ENGINE_RESOLVED}
    assert _PLAY in reached, "no `_PLAY` reaches the engine route — Issue #299's ruling is not wired"
    assert reached - {_ABILITY}, "only `_ABILITY` reaches it, which is the pre-ruling behaviour"
    assert reached <= set(seam.KIND_COVERAGE) - seam.TERMINAL_KINDS


def test_a_partial_clause_set_no_longer_resolves_to_MODELLED(census):
    """A site the compendium calls partial must not carry MODELLED, or the report counts a silent
    zero as coverage. The non-empty check is the vacuity guard."""
    mod, cards, effects, covers, pool = census
    sites, _aside = mod.census(pool, cards, effects, covers)
    partial = [s for s in sites if s.report_class == mod.PARTIAL]
    assert partial, "no MODELLED-PARTIAL sites at all — the assertion below would be vacuous"
    assert not [s for s in partial if s.fate == seam.MODELLED], (
        [(s.card_id, s.name) for s in partial if s.fate == seam.MODELLED])


def test_the_gust_family_reaches_the_seam_as_a_closed_form_transition(census):
    """The two that stay PARTIAL are RULED so, and fail CLOSED rather than pricing a leg at 0. The
    on-evolve gusts land on `_EVOLVE`: a triggered Ability rides the option that played the card."""
    mod, cards, effects, covers, pool = census
    from common.strategy.context import _EVOLVE, _PLAY
    sites, _aside = mod.census(pool, cards, effects, covers)
    gust = {s.card_id: s for s in sites
            if s.card_id in (1182, 674, 310, 1088, 1204, 1218, 1124) and s.clauses}
    assert sorted(gust) == [310, 674, 1088, 1124, 1182, 1204, 1218], sorted(gust)
    for cid in (1182, 310, 1088, 1204, 674):
        assert gust[cid].fate == seam.MODELLED, (cid, gust[cid].fate)
        assert gust[cid].report_class == mod.FULL, (cid, gust[cid].report_class)
    for cid in (1218, 1124):
        assert gust[cid].report_class == mod.PARTIAL, (cid, gust[cid].report_class)
        assert gust[cid].fate != seam.MODELLED, (cid, gust[cid].fate)
    assert gust[674].kind == _EVOLVE and gust[310].kind == _EVOLVE
    assert gust[1182].kind == _PLAY
    # All that is left of the family's clause-vocabulary gap: the coin card, 0 of our copies.
    residue = [s.card_id for s in sites if s.fate == seam.REFUSED and s.cause == mod.GAP
               and s.family.startswith("gust")]
    assert residue == [1124], residue


def test_six_stadiums_reach_the_seam_closed_form_and_the_rest_stay_honestly_missing(census):
    """An unmodelled group reading as covered is worse than one reading as missing, so the unmodelled
    list is also the positive control: same run, same predicate as the six that moved."""
    mod, cards, effects, covers, pool = census
    from common.strategy.context import _PLAY
    sites, _aside = mod.census(pool, cards, effects, covers)
    stadium = {s.card_id: s for s in sites if s.category == "stadium"}
    assert len(stadium) == 22, sorted(stadium)
    assert all(s.kind == _PLAY for s in stadium.values())

    minted = (1244, 1247, 1251, 1252, 1255, 1260)
    for cid in minted:
        assert stadium[cid].clauses, cid
        assert stadium[cid].fate == seam.MODELLED, (cid, stadium[cid].fate)
        assert stadium[cid].report_class == mod.FULL, (cid, stadium[cid].report_class)

    # DELIBERATELY unmodelled, each named in the report with its reason. 1242 already had a clause
    # set and stays `partial` on the per-body scope and symmetry its `heal` cannot carry.
    unmodelled = (1248, 1249, 1254, 1257, 1259, 1262, 1263, 1267,   # per-turn granted actions
                  1264,                                            # triggered prevention
                  1245, 1246, 1256,                                # Tool / Ability suppression
                  1250, 1261, 1266)                                # rule changes
    for cid in unmodelled:
        assert not stadium[cid].clauses, (cid, stadium[cid].clauses)
        assert stadium[cid].fate != seam.MODELLED, (cid, stadium[cid].fate)
    assert stadium[1242].report_class == mod.PARTIAL
    assert set(minted) | set(unmodelled) | {1242} == set(stadium)


def test_the_conditional_draw_supporters_move_and_the_symmetric_ones_honestly_do_not(census):
    """The four SYMMETRIC refreshes must NOT become MODELLED — each stays `partial` on the opponent's
    shuffle-and-redraw — and are the positive control for the nine that moved. 1239 left the POOL."""
    mod, cards, effects, covers, pool = census
    from common.strategy.context import _PLAY
    sites, _aside = mod.census(pool, cards, effects, covers)
    the_13 = (1227, 1213, 1080, 1223, 1192, 1216, 1187, 1208, 1199, 1200, 1181, 1237, 1203)
    draw = {s.card_id: s for s in sites if s.card_id in the_13}
    assert sorted(draw) == sorted(the_13), sorted(draw)
    assert all(s.kind == _PLAY and s.clauses for s in draw.values())
    # the fourteenth is absent from the POOL, not refused by the seam — so a Naveen that quietly
    # returns to a deck reddens here rather than slipping past the walk above unmeasured
    assert 1239 not in pool, "Naveen is back in the pool — restore it to the conditional-draw walk"
    assert covers[1239]["covers"] == "partial", "Naveen's declared error is still the ruling"

    fixed = (1181, 1187, 1192, 1199, 1200, 1203, 1208, 1216, 1227)
    for cid in fixed:
        assert draw[cid].fate == seam.MODELLED, (cid, draw[cid].fate)
        assert draw[cid].report_class == mod.FULL, (cid, draw[cid].report_class)
    # The symmetric four: still PARTIAL, each with the leg it misses quoted in its verdict.
    for cid in (1213, 1080, 1223, 1237):
        assert draw[cid].report_class == mod.PARTIAL, (cid, draw[cid].report_class)
        assert draw[cid].fate != seam.MODELLED, (cid, draw[cid].fate)
        assert draw[cid].note.strip(), cid
    assert set(fixed) | {1213, 1080, 1223, 1237} == set(the_13)

    # Lillie's alone outweighs the whole residual partial table. Read off the census's own deck
    # load rather than restated, so a deck edit moves it.
    ours = mod.our_copies(mod.load_our_decks())
    assert ours[1227] == 20, ours[1227]
    residue = [s for s in sites if s.report_class == mod.PARTIAL]
    assert sum(ours.get(s.card_id, 0) for s in residue) < ours[1227]


def test_the_census_asks_the_seam_for_the_fate_rather_than_re_deriving_it(census):
    """One store for the resolution order (Issue #299), asserted by re-driving every site through
    `seam.fate` — an independent recomputation, not a re-read of what `resolve` stored."""
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
    """``{card id: what the clauses miss}``, read as TEXT out of the committed report so the join
    below has an independent second record. Keyed off the LAST cell — the table gains columns."""
    section = text.split("### MODELLED-PARTIAL")[1].split("\n### ")[0]
    rows: dict[int, str] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 6 and cells[0].isdigit():
            rows[int(cells[0])] = cells[-1]
    return rows


def test_the_completeness_ruling_has_exactly_one_store(census):
    """Walked from the REPORT's committed text to the compendium, deliberately: a join asserted from
    the side that built it is vacuous by construction (ADR-0087, Issue #250)."""
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
    """Closes the gap the join above cannot see: a card that BECAME partial and never reached the
    report has no row to walk from."""
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
    """The markers are what let a re-run refresh the numbers without clobbering the authored verdict."""
    mod, _cards, _effects, _covers, _pool = census
    text = (_ROOT / "docs" / "plans" / "apply-seam-coverage.md").read_text(encoding="utf-8")
    assert mod.BEGIN in text and mod.END in text
    assert text.index(mod.BEGIN) < text.index(mod.END)


def test_the_deferred_target_vocabulary_is_closed_over_the_SHIPPED_compendium():
    """`test_board_choice.py` closes the registries over `CHOICE_CLAUSES`; this closes `CHOICE_CLAUSES`
    over the COMPENDIUM, the direction a fixture cannot check (Issue #392)."""
    from common import board_choice as bc
    from common import snapshot_coverage as sc
    from common.effects import CardEffects

    effects = CardEffects.load()

    def kinds_of(card_id):
        return {c.get("kind") for c in effects.clauses(card_id)}

    assert bc.CHOICE_CLAUSES, "vacuity guard: an empty vocabulary passes every assertion below"
    assert bc.CHOICE_CLAUSES <= set(sc.CLAUSE_WRITES), sorted(
        bc.CHOICE_CLAUSES - set(sc.CLAUSE_WRITES))

    shipped = set()
    for card_id in (1182, 1198, 1229, 1240):                 # the census, by card
        shipped |= kinds_of(card_id)
    assert shipped == set(bc.CHOICE_CLAUSES), sorted(shipped ^ set(bc.CHOICE_CLAUSES))

    # A REVEALING kind is `board_expectation`'s chance node, its target named on the spot rather
    # than deferred — and finding it here proves this walk reads the store at all.
    assert kinds_of(1125) == {"fetch"}
    assert not (kinds_of(1125) & bc.CHOICE_CLAUSES)
