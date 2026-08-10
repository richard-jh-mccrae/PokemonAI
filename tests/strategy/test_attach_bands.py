"""Band constraints on the shipped attach-decider constants (ADR-0069).

Builds no board: the one world fact needed — the size of a real build step — is computed from the
shipped decks' win-condition Lines and card data, so the bands follow whatever deck ships.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from common.card_worth import ENERGY_TIER, TAG_TIER
from common.pilot import (_ATTACH_ABILITY_FUEL, _ATTACH_RESOURCE_TIEBREAK,
                          _ATTACH_RETREAT_EQUITY, _ATTACH_VALUE_SCALE)
from common.grading import halve
from common.scouting.provider import EngineCardStatProvider
from common.strategy.baseline.baseline_energy import HYPOTHESES

REPO = Path(__file__).resolve().parents[2]
AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")


def _weight(hid: str) -> float:
    return next(h.weight for h in HYPOTHESES if h.id == hid)


def _strategies():
    out = []
    for agent in AGENTS:
        path = REPO / "src" / "agents" / agent / "strategy.py"
        if not path.exists():
            continue
        spec = importlib.util.spec_from_file_location(f"{agent}_bands_strategy", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out.append((agent, mod.STRATEGY))
    return out


def _build_steps():
    """``{"min": …, "max_preevo": …}`` in damage units over all shipped decks — `Pilot._attach_build_delta`
    re-derived from card data, so the bands check the arithmetic rather than a copy of it."""
    stats = EngineCardStatProvider()
    stats.warm()
    steps, preevo_steps = [], []
    for _agent, strategy in _strategies():
        for line in strategy.lines or ():
            if getattr(line, "role", None) not in (None, "win_condition"):
                continue
            payoff = stats.get(line.payoff)
            if payoff is None or not payoff.attacks:
                continue
            biggest = max(payoff.attacks, key=lambda a: getattr(stats.attack(a), "damage", 0))
            record = stats.attack(biggest)
            slots, damage = int(getattr(record, "cost", 0) or 0), float(record.damage or 0)
            if slots <= 0 or damage <= 0:
                continue
            raw = [((k + 1) ** 2 - k ** 2) / slots ** 2 * damage for k in range(slots)]
            steps.extend(raw)
            path = tuple(line.path or ())
            for index, cid in enumerate(path):
                if cid == line.payoff:
                    continue
                discounted = [s * halve(max(1, len(path) - index - 1)) for s in raw]
                steps.extend(discounted)
                preevo_steps.extend(discounted)
    assert steps, "no shipped win-condition Line resolved a payoff attack — the bands are unchecked"
    return {"min": min(steps), "max_preevo": max(preevo_steps or steps)}


@pytest.fixture(scope="module")
def steps():
    return _build_steps()


@pytest.mark.req("REQ-ATTACH-BANDS-0001")
def test_the_desperation_floor_clears_ending_the_turn(steps):
    """End scores 0, so the floor is the mobility channel: scaled Retreat Equity minus the worst
    tie-break a reusable Basic can pay (zero — the tie-break charges only worth ABOVE a Basic)."""
    basic_penalty = _ATTACH_RESOURCE_TIEBREAK * max(0.0, ENERGY_TIER - ENERGY_TIER)
    assert _ATTACH_RETREAT_EQUITY * _ATTACH_VALUE_SCALE - basic_penalty > 0
    assert all(h.weight >= 0 for h in HYPOTHESES), \
        "a NEGATIVE surviving rung would put the desperation floor back in competition"


@pytest.mark.req("REQ-ATTACH-BANDS-0002")
def test_the_channels_sit_below_one_real_build_step(steps):
    """Both channels are in DAMAGE units BEFORE the scale, so the constraint is scale-invariant."""
    assert 0 < _ATTACH_RETREAT_EQUITY < steps["min"]
    assert 0 < _ATTACH_ABILITY_FUEL < steps["min"]


@pytest.mark.req("REQ-ATTACH-BANDS-0003")
def test_the_resource_tiebreak_orders_equals_and_nothing_more(steps):
    """The widest charge reusable-over-burst can make is a one-shot's worth above a reusable Basic."""
    widest = _ATTACH_RESOURCE_TIEBREAK * (TAG_TIER["discard_eot"] - ENERGY_TIER)
    assert 0 < widest < _ATTACH_VALUE_SCALE * steps["min"]


def _effective(hid: str):
    """``[(agent, weight), …]`` — the tuned.json override where one exists (ADR-0018), else the seed."""
    out = []
    for agent, _strategy in _strategies():
        tuned = REPO / "src" / "agents" / agent / "tuned.json"
        overrides = json.loads(tuned.read_text(encoding="utf-8")) if tuned.exists() else {}
        out.append((agent, float(overrides.get(hid, _weight(hid)))))
    return out
