"""ADR-0050 Phase 2(D) — the reusable end-to-end lethal gate ``engine_confirms(fixture, pilot)``.

It drives a seeded correction fixture's win line through the real engine cascade
(``pilot._engine_confirms_win``) and returns the engine's verdict, so a multi-step lethal proposal is
gated on 'real play completes the line', not just closed-form recognition. Skips cleanly when the
native lib is absent, and is a no-op (None) on a fixture with no seed — the offline suite stays green.
"""
import json
from pathlib import Path

import pytest

from lethal_helpers import engine_confirms, require_cg

REPO = Path(__file__).resolve().parents[2]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _mega_starmie_pilot():
    from cg.api import all_attack
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import (
        EngineCardStatProvider, build_attack_stats, load_attack_overrides,
        parse_attack_bench_snipe, parse_attack_recoil)
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    deck = [int(x) for x in (REPO / "src" / "agents" / "mega_starmie" / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]
    atk = all_attack()
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 attacks={a.attackId: a.damage for a in atk},
                 attack_costs={a.attackId: len(a.energies) for a in atk},
                 recoil={a.attackId: parse_attack_recoil(a.text) for a in atk},
                 bench_snipe={a.attackId: parse_attack_bench_snipe(a.text) for a in atk},
                 attack_stats=build_attack_stats(atk, load_attack_overrides()),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_returns_none_without_a_seed():
    """The gate is a no-op on an unseeded fixture — returns None (keep the closed-form verdict), never
    raises and never needs the native lib. This is what keeps the offline suite green cross-platform."""
    fx = {"obs": {"current": {"yourIndex": 0, "players": [{}, {}]}}, "correct": [0]}
    assert engine_confirms(fx, pilot=None) is None


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_a_shipped_lethal_wins_end_to_end():
    """Proof-of-life: the applied recover-energy lethal f110 (seeded) drives to a real engine WIN
    verdict through the cascade — the gate's positive case, independent of any new steering hook."""
    require_cg()
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    assert engine_confirms(fx, _mega_starmie_pilot()) is True
