import pytest
from pathlib import Path

from cgpy.experiment import TurnSearchEnvironment
from common.decision.puct import PuctOutcome
from common.puct import PuctConfiguration, build_puct_coordinator
from real_engine_helpers import BodySpec, lock_main_allowances, scenario


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "98a582d49a32146b18e59beed0019041ce1745fd653e94f7d9c86f8cf0aec92d"


@pytest.mark.parametrize("hand,energy_spent,expected", (
    ((1227, 1159), True, "prepare"),
    ((1227,), True, "play"),
    ((1227, 1030, 1031, 3, 17, 1121, 1145, 1086, 1189), True, "attack"),
))
def test_lillie_sequencing_with_frozen_ledger(hand, energy_spent, expected):
    engine, runtime = scenario(
        "mega_starmie", me_active=BodySpec((1030,) if expected == "prepare" else (1030, 1031),
                                         energies=() if expected == "play" else (3,),
                                         hp=30 if expected == "prepare" else 330), me_hand=hand,
        them_active=BodySpec((1030, 1031), hp=30 if expected == "attack" else 300, energies=(3,)),
        them_bench=())
    lock_main_allowances(engine, supporter=False, energy=energy_spent)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    coordinator = build_puct_coordinator(
        runtime.ledger.ctx, baseline_identity=BASELINE,
        baseline_path=ROOT / "data" / "ledger-baselines" / BASELINE / "manifest.json",
        calibration_path=ROOT / "data" / "ledger-policy-calibrations" / f"{BASELINE}.json",
        prior_mode="uniform", provider_identity="turn-search-v1",
        configuration=PuctConfiguration(simulation_limit=512, batch_size=4, worker_count=2,
                                        chance_samples=8, exploration=32.0))

    result = coordinator.decide(environment.root, provider=environment, strict=True)

    assert result.search.puct.outcome is PuctOutcome.SEARCHED, result.search.failure
    assert result.chosen.identity.kind == ("attach" if expected == "prepare" else expected)
    if expected == "prepare":
        assert "1159" in str(result.chosen.identity.parts)
        assert any(step.action is not None and step.action.kind == "play" and "1227" in str(step.action.parts)
                   for step in result.search.puct.principal_variation)
