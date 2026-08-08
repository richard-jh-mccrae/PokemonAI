"""M3 verdict-agreement gate (ADR-0050): native and the cgpy twin must reach the SAME verdict.

cgpy may return None (undetermined) where native decides — None never lies — so the known-decidable
fixtures are asserted too, or the twin could degrade to all-None unnoticed.
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
from lethal_helpers import engine_confirms                       # noqa: E402

from cgpy import alias                                           # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# Only a DRAW-FREE cascade has a prediction-invariant verdict the two engines must agree on.
# f15 is deliberately absent too; its Petrel win line is gated in test_lethal_cgpy.py instead.
EXCLUDED_FIXTURES = {
    "ml_lethal_retreat_boost_to_ko_f24": "cascade draws off the shuffled deck (#178)",
}

SEEDED_FIXTURES = [
    ("ms_lethal_recover_energy_to_win_f110", "mega_starmie"),
    ("ml_lethal_recover_energy_retreat_ko_f26", "mega_lucario"),
    ("ml_lethal_recover_energy_via_gong_f48", "mega_lucario"),
]


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _pilot(deck):
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # the provider builds lazily off whichever engine the cgpy alias maps at call time (ADR-0051)
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


def _both_verdicts(name, agent):
    fx = _fixture(name)
    native = engine_confirms(fx, _pilot(_deck(agent)))
    alias.install()
    try:
        py = engine_confirms(fx, _pilot(_deck(agent)))
    finally:
        alias.uninstall()
    return native, py


@pytest.mark.req("REQ-CGPY-M3-0012")
@pytest.mark.parametrize("name,agent", SEEDED_FIXTURES, ids=lambda v: v)
def test_engine_confirms_win_verdicts_agree(name, agent):
    native, py = _both_verdicts(name, agent)
    assert native is not None, f"{name}: native verdict unavailable — fixture seed broken?"
    assert py == native or py is None, (
        f"{name}: cgpy verdict {py!r} contradicts native {native!r}")


@pytest.mark.req("REQ-CGPY-M3-0012")
def test_agreement_is_not_vacuous():
    """The twin must decide the decidable, or the agreement gate passes while proving nothing."""
    native, py = _both_verdicts("ms_lethal_recover_energy_to_win_f110", "mega_starmie")
    assert native is True and py is True


def _cascade_reveals(name, agent):
    """The membership criterion for `SEEDED_FIXTURES`, measured instead of assumed. Defers to
    `planner._rng_probe`, the rule the planner itself applies, so the two cannot drift."""
    from engine_admissibility import cascade_reveals

    return cascade_reveals(_fixture(name), _pilot(_deck(agent)))


@pytest.mark.req("REQ-CGPY-M3-0012")
@pytest.mark.parametrize("name,agent", SEEDED_FIXTURES, ids=lambda v: v)
def test_every_seeded_cascade_is_really_draw_free(name, agent):
    assert not _cascade_reveals(name, agent), (
        f"{name}: this cascade consumes engine randomness, so its verdict is a sample of the "
        f"shuffle — it cannot gate native/cgpy agreement. Exclude it like ml f24 and f15.")


@pytest.mark.req("REQ-CGPY-M3-0012")
def test_the_excluded_fixture_really_does_draw():
    """Negative control: if f24 stops drawing, it belongs back in `SEEDED_FIXTURES`."""
    assert "ml_lethal_retreat_boost_to_ko_f24" in EXCLUDED_FIXTURES
    assert _cascade_reveals("ml_lethal_retreat_boost_to_ko_f24", "mega_lucario") >= {"DRAW"}


@pytest.mark.req("REQ-CGPY-M3-0013")
def test_simulate_line_runs_on_both_engines():
    """`_simulate_line` is order-DEPENDENT by design, so only availability is asserted."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")     # a MAIN-select seeded fixture
    obs, first = fx["obs"], fx["correct"]
    native = _pilot(_deck("mega_lucario"))._simulate_line(obs, list(first))
    alias.install()
    try:
        py = _pilot(_deck("mega_lucario"))._simulate_line(obs, list(first))
    finally:
        alias.uninstall()
    assert (native is None) == (py is None)
    if native is not None:
        assert py is not None
