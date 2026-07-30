"""The registry that makes #178 a same-day failure instead of a three-week hunt.

ADR-0072 amendment C rules that a frame may gate an instrument only if its answer is reproducible.
That ruling needs somewhere it is *enforced* rather than remembered, and this is it: every correction
fixture that can drive the engine at all is classified here, by measurement, against a committed
table. Add a seeded fixture, or change a policy so an existing cascade starts drawing, and this goes
red naming the fixture — which is exactly what nothing did for ml f24.

Scope is small and that is the point: 5 of 133 correction fixtures carry a `search_begin_input`, so
only those 5 can consume engine randomness. The other 128 return None from `_simulate_line` and are
deterministic by construction.
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

#: fixture -> (agent, the channels its cascade consumes under the DEFAULT lethal pilot).
#: Measured 2026-07-27. An empty set means an exact verdict may be asserted on it; a non-empty one
#: means the verdict is a sample and the frame owes a recorded re-ruling before any gate leans on it.
CLASSIFIED = {
    "ms_lethal_recover_energy_to_win_f110":    ("mega_starmie", set()),
    "ml_lethal_recover_energy_retreat_ko_f26": ("mega_lucario", set()),
    "ml_lethal_recover_energy_via_gong_f48":   ("mega_lucario", set()),
    "ml_petrel_balloon_retreat_lethal_f15":           ("mega_lucario", set()),
    # THE ONE. Its cascade shuffles its hand back in and draws off the reshuffled deck, so its
    # verdict is whatever that shuffle allowed. Re-ruled out of the agreement gate (#178); the
    # `[correct]`-only claims in test_planner_boost_promote were rewritten around it.
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
    """The registry must cover the ground it claims to. A new fixture carrying a seed token lands
    here first — before it can be pinned by a gate — so nobody has to notice a flake to discover it
    consumes randomness."""
    assert set(_seeded_fixture_names()) == set(CLASSIFIED), (
        "a correction fixture gained or lost its engine seed token. A seeded fixture can consume "
        "engine randomness, so classify it in CLASSIFIED (measure with `cascade_reveals`) before "
        "any test pins its verdict — ADR-0072 amendment C.")


@pytest.mark.req("REQ-PLANNER-0037")
@pytest.mark.parametrize("name", sorted(CLASSIFIED), ids=lambda v: v)
def test_the_classification_still_holds(name):
    """Re-measure, don't trust the table. A policy change that makes a previously reveal-free
    cascade start drawing is exactly the #178 shape, and it must surface as this failure rather
    than as a frame that quietly starts flapping somewhere else."""
    agent, expected = CLASSIFIED[name]
    assert cascade_reveals(_fixture(name), _pilot(agent)) == expected, (
        f"{name}: what its cascade takes off the shuffle CHANGED. If it now reveals, every exact "
        f"assertion on its verdict is a sample — re-rule it, do not re-run it. If it no longer "
        f"reveals, the frame may be readmitted: update CLASSIFIED and say so in the commit.")


@pytest.mark.req("REQ-PLANNER-0037")
def test_the_registry_is_not_vacuous():
    """A registry where everything is admissible would pass while measuring nothing — the failure
    mode the `SEEDED_FIXTURES` comment had for its whole life. At least one frame must be known
    sampled, and f24 is the one we know."""
    sampled = {n for n, (_, ch) in CLASSIFIED.items() if ch}
    assert sampled, "no fixture is classified as sampled — is the probe still wired up?"
    assert "ml_lethal_retreat_boost_to_ko_f24" in sampled


@pytest.mark.req("REQ-PLANNER-0037")
def test_admissibility_is_a_property_of_the_drive_not_the_fixture():
    """Why `cascade_reveals` takes a pilot and a line rather than just a fixture name.

    ml f24 answers this question BOTH ways depending only on how it is driven. Driving one step and
    letting `decide()` play out the rest sends it through a shuffle-hand-in-and-draw card, so its
    verdict is a sample. Driving the full explicit win line leaves the cascade nothing to draw for,
    and the same board's verdict becomes a fact.

    That is not a curiosity — it is the whole reason `test_boost_lethal_f24_target_is_real` still
    asserts `is True` while the `[correct]`-only claim beside it could not (#178). A registry keyed
    on the fixture alone would have to call f24 inadmissible and would throw away the one assertion
    on it that was always sound."""
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
    """The negative control for the harness itself: no drive, no reveals. Guards against the
    context manager reporting phantom randomness (which would make every frame look inadmissible
    and quietly disable the registry)."""
    with measure_rng(0) as reveals:
        pass
    assert reveals == set()
