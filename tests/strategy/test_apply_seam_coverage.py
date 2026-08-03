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


def test_the_gust_family_reaches_the_seam_as_a_closed_form_transition(census):
    """**Issue #303's acceptance, as a measurement.** Before the mint, all 7 gust sites in the pool
    carried no clause at all: the two with RNG or no determinism proof were REFUSED and the rest sat
    as engine-route *candidates*, which is not the same as priced — a candidate needs a
    `deterministic=True` proof and a wired `search_api`, and nothing produces either.

    Five now resolve MODELLED-FULL, and they carry every copy of the family we actually shuffle
    (Boss's Orders 11, Hariyama 2). The two that do not are RULED `partial`, not left unbuilt, so
    they fail CLOSED rather than pricing an undeclared leg at 0 — and the coin one is the whole
    residue of the family's gap row, asserted here so "the row dropped to its 0-copy tail" is a
    check rather than a claim in the prose.

    Also pinned: the two on-evolve gusts land on the `_EVOLVE` site. That is the shape requirement
    Issue #305's measurement forced — a triggered Ability rides the option that played the card and
    poses no `_ABILITY` of its own — and it is carried by the clause's `trigger`, so a routing
    regression fails here instead of silently filing the clause on a site the engine never poses."""
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
    # What is left of the family's clause-vocabulary gap: the coin card alone, 0 of our copies. The
    # `Expectation` it waits on is 1120 Crushing Hammer's, not a gust-shaped hole.
    residue = [s.card_id for s in sites if s.fate == seam.REFUSED and s.cause == mod.GAP
               and s.family.startswith("gust")]
    assert residue == [1124], residue


def test_six_stadiums_reach_the_seam_closed_form_and_the_rest_stay_honestly_missing(census):
    """**Issue #304's acceptance, as a measurement, in both directions.**

    Six Stadiums now resolve MODELLED-FULL, including the two with live copies behind them —
    1252 Gravity Mountain (2, `mega_lucario`) and 1260 Risky Ruins (2, `dragapult_ex`), the second
    of which taxes bench development on BOTH sides and so was over-valuing every deploy the Deploy
    Marginal (ADR-0086) prices.

    The other direction is the half that matters more, per *no silent caps*: an unmodelled group
    that reads as covered is worse than one that reads as missing. So this also asserts that the
    granted-action Stadiums, the suppression Stadiums and the rule-change Stadiums did **not**
    quietly become MODELLED — they carry no clauses and stay engine-route candidates or refusals.
    Two of them have four copies each behind them (1248 Academy at Night in `slowking`, 1259
    Spikemuth Gym in `grimmsnarl_ex`) and are cross-posted to Issue #289 and Issue #301 rather than
    built here, because they are those tracks' problems wearing a Stadium.

    The unmodelled assertion is the POSITIVE CONTROL for the modelled one: both lists are read off
    the same census run through the same predicate, so "six moved" cannot be an artefact of a walk
    that reaches nothing."""
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

    # DELIBERATELY unmodelled, each named in the report with its reason. 1242 Community Center is
    # the one Stadium that already had a clause set, and it stays `partial` on the per-body scope
    # and the symmetry its `heal` clause cannot carry.
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
    """**Issue #302's acceptance, as a measurement, in both directions.**

    NINE of the 14 conditional draw Supporters now resolve MODELLED-FULL, and the exposure is
    concentrated in one of them: 1227 Lillie's Determination is 24 copies across our decks, named by
    three authored doctrines, and its clause stated the card's MAXIMUM (8) on every board where the
    real number is 6.

    The ninth arrived at Issue #349: 1187 Morty's Conviction was one of Issue #302's declared errors
    — *"the MAGNITUDE is one card per opponent BENCHED Pokemon, a board-scaled count no clause field
    expresses"* — and `amount_per` is that field. It is the only one of the six that a later
    sub-issue could close, because its missing leg was VOCABULARY rather than an accepted unknown.

    The other direction is the half that matters more, per *no silent caps*. The four SYMMETRIC
    refreshes — Judge, Unfair Stamp, Harlequin, Lucian — did **not** quietly become MODELLED. Each
    carries its own leg exactly and stays `partial` on the opponent's shuffle-and-redraw, which needs
    a `state_value` term that prices their hand and which the seam already refuses as an accepted POC
    unknown. Naveen keeps its optional pre-discard. Five declared errors are the deliverable as much
    as the nine fixes are.

    Both lists are read off the SAME census run through the same predicate, so "nine moved" cannot be
    an artefact of a walk that reaches nothing — the five that stayed are the positive control."""
    mod, cards, effects, covers, pool = census
    from common.strategy.context import _PLAY
    sites, _aside = mod.census(pool, cards, effects, covers)
    the_14 = (1227, 1213, 1080, 1223, 1239, 1192, 1216, 1187, 1208, 1199, 1200, 1181, 1237, 1203)
    draw = {s.card_id: s for s in sites if s.card_id in the_14}
    assert sorted(draw) == sorted(the_14), sorted(draw)
    assert all(s.kind == _PLAY and s.clauses for s in draw.values())

    fixed = (1181, 1187, 1192, 1199, 1200, 1203, 1208, 1216, 1227)
    for cid in fixed:
        assert draw[cid].fate == seam.MODELLED, (cid, draw[cid].fate)
        assert draw[cid].report_class == mod.FULL, (cid, draw[cid].report_class)
    # The symmetric four, plus Naveen's optional pre-discard. Still PARTIAL, still failing closed,
    # each with the leg it misses quoted in its verdict.
    for cid in (1213, 1080, 1223, 1237, 1239):
        assert draw[cid].report_class == mod.PARTIAL, (cid, draw[cid].report_class)
        assert draw[cid].fate != seam.MODELLED, (cid, draw[cid].fate)
        assert draw[cid].note.strip(), cid
    assert set(fixed) | {1213, 1080, 1223, 1237, 1239} == set(the_14)

    # Where the exposure actually is: Lillie's alone is more copies than the whole residual partial
    # table. Read off the census's own deck load rather than restated, so a deck edit moves it.
    ours = mod.our_copies(mod.load_our_decks())
    assert ours[1227] == 24, ours[1227]
    residue = [s for s in sites if s.report_class == mod.PARTIAL]
    assert sum(ours.get(s.card_id, 0) for s in residue) < ours[1227]


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
