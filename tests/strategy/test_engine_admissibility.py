"""Which correction fixtures can consume engine randomness, classified by measurement.

ADR-0072 amendment C: a frame may gate an instrument only if its answer is reproducible. Only
fixtures carrying a `search_begin_input` can consume randomness at all.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("cg")

from common.cards import CardFunctions                           # noqa: E402
from common.effects import CardEffects                           # noqa: E402
from common.pilot import Pilot                                   # noqa: E402
from common.scouting.provider import EngineCardStatProvider      # noqa: E402
from common.strategy import Strategy                             # noqa: E402
from common.strategy.general_strategy import GENERAL_STRATEGY    # noqa: E402
from engine_admissibility import cascade_reveals, measure_rng    # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

#: fixture -> (agent, channels its cascade consumes under the DEFAULT lethal pilot). Empty set = an
#: exact verdict may be asserted on it; non-empty = the verdict is a sample, and owes a re-ruling.
CLASSIFIED = {
    "ms_lethal_recover_energy_to_win_f110":    ("mega_starmie", set()),
    "ml_lethal_recover_energy_retreat_ko_f26": ("mega_lucario", set()),
    "ml_lethal_recover_energy_via_gong_f48":   ("mega_lucario", set()),
    "ml_petrel_balloon_retreat_lethal_f15":           ("mega_lucario", set()),
    # its cascade shuffles the hand in and draws, so the verdict is a sample (Issue #178)
    "ml_lethal_retreat_boost_to_ko_f24":       ("mega_lucario", {"DRAW"}),
}


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _pilot(agent):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), _deck(agent), general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


def _seeded_fixture_names():
    return sorted(p.stem for p in FIXTURES.glob("*.json")
                  if "search_begin_input" in p.read_text(encoding="utf-8"))


@pytest.mark.req("REQ-PLANNER-0037")
def test_every_engine_capable_fixture_is_classified():
    assert set(_seeded_fixture_names()) == set(CLASSIFIED), (
        "a correction fixture gained or lost its engine seed token. A seeded fixture can consume "
        "engine randomness, so classify it in CLASSIFIED (measure with `cascade_reveals`) before "
        "any test pins its verdict — ADR-0072 amendment C.")


@pytest.mark.req("REQ-PLANNER-0037")
@pytest.mark.parametrize("name", sorted(CLASSIFIED), ids=lambda v: v)
def test_the_classification_still_holds(name):
    agent, expected = CLASSIFIED[name]
    assert cascade_reveals(_fixture(name), _pilot(agent)) == expected, (
        f"{name}: what its cascade takes off the shuffle CHANGED. If it now reveals, every exact "
        f"assertion on its verdict is a sample — re-rule it, do not re-run it. If it no longer "
        f"reveals, the frame may be readmitted: update CLASSIFIED and say so in the commit.")


@pytest.mark.req("REQ-PLANNER-0037")
def test_the_registry_is_not_vacuous():
    """A registry where everything is admissible would pass while measuring nothing."""
    sampled = {n for n, (_, ch) in CLASSIFIED.items() if ch}
    assert sampled, "no fixture is classified as sampled — is the probe still wired up?"
    assert "ml_lethal_retreat_boost_to_ko_f24" in sampled


@pytest.mark.req("REQ-PLANNER-0037")
def test_admissibility_is_a_property_of_the_drive_not_the_fixture():
    """Why `cascade_reveals` takes a pilot and a line, not just a fixture name."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    explicit_win_line = [[5], [1], [1], [2], [0], [0], [2]]

    sampled = cascade_reveals(fx, _pilot("mega_lucario"))
    exact = cascade_reveals(fx, _pilot("mega_lucario"), line=explicit_win_line)

    assert sampled == {"DRAW"}, "the [correct]-only drive should still ride the shuffle"
    assert exact == set(), (
        "the fully explicit win line started consuming randomness — "
        "`test_boost_lethal_f24_target_is_real` pins an exact verdict on this drive and would now "
        "be pinning a sample. Re-measure both before touching either.")


@pytest.mark.req("REQ-PLANNER-0037")
def test_measure_rng_reports_nothing_when_no_search_runs():
    """Negative control: phantom reveals would make every frame look inadmissible."""
    with measure_rng(0) as reveals:
        pass
    assert reveals == set()
