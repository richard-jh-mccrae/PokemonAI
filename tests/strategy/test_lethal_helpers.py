"""ADR-0050 Phase 2(D) — the reusable end-to-end lethal gate ``engine_confirms(fixture, pilot)``.

Skips cleanly when the native lib is absent, and is a no-op (None) on an unseeded fixture, so the
offline suite stays green cross-platform.
"""
import json
from pathlib import Path

import pytest

from lethal_helpers import engine_confirms, require_cg

REPO = Path(__file__).resolve().parents[2]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _pilot(agent="mega_starmie"):
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    deck = [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051)
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_returns_none_without_a_seed():
    fx = {"obs": {"current": {"yourIndex": 0, "players": [{}, {}]}}, "correct": [0]}
    assert engine_confirms(fx, pilot=None) is None


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_a_shipped_lethal_wins_end_to_end():
    require_cg()
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    assert engine_confirms(fx, _pilot("mega_starmie")) is True


# attach {F}->Solrock, 2x Premium Power Pro, retreat Lunatone, promote Solrock, Cosmic Beam 130 for
# a bench-empty win (ADR-0050 DoD#3); decide() then handles the trailing prize cascade.
_F24_WIN_LINE = [[5], [1], [1], [2], [0], [0], [2]]


# The engine's RNG stream is process-global and unseedable, so ONE drive is a sample: both claims
# below are existence claims over K independent streams (ADR-0050).
_F24_STREAMS = 5


def _verdicts(fx, agent, line=None, k=_F24_STREAMS):
    return [engine_confirms(fx, _pilot(agent), line=line) for _ in range(k)]


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_multi_step_line_proves_a_real_missed_win():
    """decide()'s follow-up steering hooks are UNBUILT, so the [correct]-only form refutes; once they
    ship it goes green on its own and this capability-gap gate should be retired."""
    require_cg()
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    driven = _verdicts(fx, "mega_lucario", line=_F24_WIN_LINE)
    assert True in driven, f"the explicitly driven win line never confirmed: {driven}"
    composed = _verdicts(fx, "mega_lucario")
    assert False in composed, (
        f"[correct]+decide() confirmed the win on every stream ({composed}) — the follow-up steering "
        f"hooks now compose the line, so this capability-gap gate has been met and should be retired")
