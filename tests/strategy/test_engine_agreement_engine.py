"""M3 verdict-agreement gate (ADR-0050): the planner's engine drivers must reach the SAME
verdict on the native engine and on the cgpy twin, on every seeded correction fixture.

`_engine_confirms_win` is the sound Solver hook (a phantom win loses the game), so the
agreement rule is strict where it matters: whenever cgpy reaches a verdict it must equal
native's; cgpy may return None (undetermined) where native decides — None never lies — but
the suite also pins the known-decidable fixtures so the twin can't silently degrade to
all-None. Imports the committed native lib (skips cleanly without it); the cgpy side runs
through `cgpy.alias` in the same process — the planner's per-call ``from cg import api``
resolves whichever engine the alias maps at call time.
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

# The seeded fixtures (search_begin_input + own_prizes backfilled — the recorded
# planner-call corpus) whose cascade is DRAW-FREE, so the verdict is prediction-invariant
# and the two engines must agree. f15 is deliberately absent: its recorded step is the
# retired dead-hand framing (Lillie's = shuffle-hand-in, draw 6), whose outcome hinges on
# WHICH cards the fork deals — order-dependent by the planner's own doctrine (its native
# verdict varies with the process's prior searches). Its Petrel win line is gated
# deterministically in test_lethal_cgpy.py instead.
SEEDED_FIXTURES = [
    ("ms_lethal_recover_energy_to_win_f110", "mega_starmie"),
    ("ml_lethal_recover_energy_retreat_ko_f26", "mega_lucario"),
    ("ml_lethal_recover_energy_via_gong_f48", "mega_lucario"),
    ("ml_lethal_retreat_boost_to_ko_f24", "mega_lucario"),
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
    # attack facts flow through the provider (ADR-0051); it lazily builds off whichever engine
    # the cgpy alias maps at call time, so native/twin parity is preserved.
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
    """The twin must actually decide the decidable: the shipped recover-energy win (f110)
    confirms True on BOTH engines — the whole fetch->attach->retreat->promote->attack->win
    cascade drives through cgpy to the same verdict."""
    native, py = _both_verdicts("ms_lethal_recover_energy_to_win_f110", "mega_starmie")
    assert native is True and py is True


@pytest.mark.req("REQ-CGPY-M3-0013")
def test_simulate_line_runs_on_both_engines():
    """The heuristic ranker (`_simulate_line`) is order-DEPENDENT by design (coins
    auto-resolve, draws differ per shuffle), so only availability is asserted: where the
    native path returns an end-board value, the cgpy path must return one too."""
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
