"""`CardStat.stage` is POPULATED, in the canonical vocabulary, for the whole pool (Issue #408).

The field was declared and never written. Every test that touched it hand-built its own `CardStat`,
so the fixtures supplied what production did not and the two readers — the FETCH closure's
`stage1`/`stage2` classes and the Skyliner retreat grant — compared against None on every board.

The missing assertion was never a claim about FIXTURES; it is a claim about PRODUCTION, which is why
it lives here rather than in the fixture audit. These run the SHIPPED transform (`_build_cache`) over
the SHIPPED tables (cgpy's committed snapshot, minted from the DLL) — not a second reading of either.
"""
import csv
from pathlib import Path

import pytest

from common.scouting.provider import _build_cache, stage_from_card

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "EN_Card_Data.csv"

#: Pool-wide census, pinned. A silent re-slice of the card pool should fail loudly here rather than
#: quietly change what the `stage1` / `stage2` FETCH classes reach.
EXPECTED_CENSUS = {"basic": 600, "stage1": 345, "stage2": 116, None: 206}

#: `cardType` ITEM, yet the engine reports `basic=True` — and it is right: *"Play this card as if it
#: were a 60-HP Basic {C} Pokémon."* They are why the partition below is `hp > 0` and not
#: `cardType == POKEMON`, and why the fixture audit maps the CSV's `Item` label through the effect
#: text instead of straight to None.
FOSSILS = (1099, 1136, 1138, 1150, 1151)


@pytest.fixture(scope="module")
def pool():
    """`{cardId: CardStat}` over the real card tables, DLL-free (the `apply_parity` lane's seam)."""
    from cgpy.compat import api as cgapi
    return _build_cache(cgapi.all_card_data(), cgapi.all_attack())


@pytest.fixture(scope="module")
def cards():
    from cgpy.compat import api as cgapi
    return {c.cardId: c for c in cgapi.all_card_data()}


def test_every_card_carries_the_engines_own_stage(pool, cards):
    """The assertion that would have caught the bug on day one: for all 1267 cards the built
    `CardStat.stage` equals the engine's own answer. Fails on a pool with any card unwritten."""
    wrong = {cid: (stat.stage, stage_from_card(cards[cid]))
             for cid, stat in pool.items() if stat.stage != stage_from_card(cards[cid])}
    assert wrong == {}
    assert len(pool) == 1267


def test_the_stage_census_matches_the_pool(pool):
    """Positive control on the test above: `stage == stage_from_card(...)` is also satisfied by a
    pool where BOTH sides are None, which is exactly the state this issue found. Pin the counts so
    an all-None pool — the regression — cannot pass."""
    census = {}
    for stat in pool.values():
        census[stat.stage] = census.get(stat.stage, 0) + 1
    assert census == EXPECTED_CENSUS


def test_stage_is_populated_for_exactly_the_bodies(pool):
    """The partition: a card with HP has a stage, a card without has none. `CardStat.is_pokemon` is
    `hp > 0`, and over this pool that agrees with the stage flags exactly — including the Fossils,
    which `cardType` would misfile."""
    assert [s.cardId for s in pool.values() if s.is_pokemon and s.stage is None] == []
    assert [s.cardId for s in pool.values() if not s.is_pokemon and s.stage is not None] == []


def test_the_fossils_are_basics_despite_printing_as_items(pool):
    """The five-card edge the `cardType == POKEMON` reading gets wrong."""
    for cid in FOSSILS:
        stat = pool[cid]
        assert (stat.stage, stat.is_item, stat.is_pokemon) == ("basic", True, True), stat.name


def test_a_stage_is_never_ambiguous(cards):
    """`stage_from_card` returns the FIRST flag set, so two flags on one card would silently pick
    basic over stage2. Nothing in the pool sets two — pinned, so the day one does, this fails
    instead of the closure quietly under-reaching."""
    multi = [c.cardId for c in cards.values()
             if (bool(c.basic) + bool(c.stage1) + bool(c.stage2)) > 1]
    assert multi == []


def test_dump_cards_stage_of_delegates_rather_than_respelling(cards):
    """ADR-0087's drift charge: `tools/meta_tracker/dump_cards.stage_of` and the provider must not be
    two readings of the same question. Asserted by AGREEMENT over the whole pool, not by reading the
    source — a delegation that stopped delegating would still have to keep answering identically."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from meta_tracker.dump_cards import stage_of
    assert all(stage_of(c) == stage_from_card(c) for c in cards.values())


def test_csv_stage_truth_matches_the_engine_pool(cards):
    """The fixture audit's CSV-side mapping (`_stage_flags`) is INDEPENDENT ground truth, so it has
    to be checked against the engine rather than assumed. Zero mismatches over all 1267 cards.

    Without the Fossil leg this fails on exactly five rows — the CSV files them under `Item`."""
    from test_cardstat_fixture_facts import _csv_truth        # sibling module (no tests package)
    truth = _csv_truth()
    missing = [cid for cid in cards if cid not in truth]
    assert missing == []
    wrong = {cid: (truth[cid]["stage"], stage_from_card(c))
             for cid, c in cards.items() if truth[cid]["stage"] != stage_from_card(c)}
    assert wrong == {}


def test_the_csv_carries_a_row_for_every_card(cards):
    """Positive control for the test above: it compares only ids present in BOTH sources, so a CSV
    that had drifted to a handful of rows would agree vacuously."""
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        ids = {int(row["Card ID"]) for row in csv.DictReader(handle)
               if (row.get("Card ID") or "").strip()}
    assert len(ids) == len(cards) == 1267
