"""The attach decider's BAND CONSTRAINTS, asserted over the SHIPPED constants (#139, ADR-0069).

The retune is constraint-first by ruling: the feasible region for every constant is SOLVED from
written inequalities, corpus score-diff picks inside it, and the A/B confirms. These tests are that
first step made executable, so a future retune cannot silently break the desperation floor or the
tie-break bands — no shipped number here is folklore.

Nothing here builds a board. The one thing the inequalities need from the world is the size of a
REAL build step, which is a fact about the SHIPPED decks' cards, so it is computed from their
declared win-condition Lines and the card data rather than hard-coded. If a deck changes, the bands
are re-checked against the deck that actually ships.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from common.card_worth import ENERGY_TIER, TAG_TIER
from common.pilot import (_ATTACH_ABILITY_FUEL, _ATTACH_PREEVO_DISCOUNT, _ATTACH_RESOURCE_TIEBREAK,
                          _ATTACH_RETREAT_EQUITY, _ATTACH_VALUE_SCALE)
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
    """Every single-Energy CONVEX build step a shipped win-condition Line can produce, in damage
    units — the marginal of the k-th Energy toward the payoff's biggest attack,
    ``((k+1)**2 - k**2)/M**2 * maxDamage``, with the pre-evolution discount applied on the Line's
    non-payoff bodies. Exactly what `Pilot._attach_build_delta` computes, re-derived here from card
    data so the bands are checked against the arithmetic and not against a copy of it.

    Returns ``{"min": …, "max_preevo": …}`` over all shipped decks.
    """
    stats = EngineCardStatProvider()
    stats.warm()
    steps, preevo_steps = [], []
    for _agent, strategy in _strategies():
        for line in strategy.lines or ():
            if getattr(line, "role", None) not in (None, "win_condition"):
                continue                                  # `_line_payoff_stat` reads wincon Lines only
            payoff = stats.get(line.payoff)
            if payoff is None or not payoff.attacks:
                continue
            biggest = max(payoff.attacks, key=lambda a: getattr(stats.attack(a), "damage", 0))
            record = stats.attack(biggest)
            slots, damage = int(getattr(record, "cost", 0) or 0), float(record.damage or 0)
            if slots <= 0 or damage <= 0:
                continue
            raw = [((k + 1) ** 2 - k ** 2) / slots ** 2 * damage for k in range(slots)]
            steps.extend(raw)                             # the payoff itself: no discount
            discounted = [s * _ATTACH_PREEVO_DISCOUNT for s in raw]
            if any(cid != line.payoff for cid in (line.path or ())):
                steps.extend(discounted)                  # a Line pre-evolution builds at a discount
                preevo_steps.extend(discounted)
    assert steps, "no shipped win-condition Line resolved a payoff attack — the bands are unchecked"
    return {"min": min(steps), "max_preevo": max(preevo_steps or steps)}


@pytest.fixture(scope="module")
def steps():
    return _build_steps()


@pytest.mark.req("REQ-ATTACH-BANDS-0001")
def test_the_desperation_floor_clears_ending_the_turn(steps):
    """The only-legal-home attach must out-score End. End scores 0 and no surviving rung is negative,
    so the floor is the mobility channel itself: Retreat Equity, scaled, minus the worst resource
    tie-break a reusable Basic can pay (which is zero, by construction — the tie-break charges only
    worth ABOVE a Basic). This is the inequality the old −5 sequencing weight made INFEASIBLE at any
    sane band, and which moving sequencing out of the score channel resolved structurally."""
    basic_penalty = _ATTACH_RESOURCE_TIEBREAK * max(0.0, ENERGY_TIER - ENERGY_TIER)
    assert _ATTACH_RETREAT_EQUITY * _ATTACH_VALUE_SCALE - basic_penalty > 0
    assert all(h.weight >= 0 for h in HYPOTHESES), \
        "a NEGATIVE surviving rung would put the desperation floor back in competition"


@pytest.mark.req("REQ-ATTACH-BANDS-0002")
def test_the_channels_sit_below_one_real_build_step(steps):
    """Retreat Equity and Ability Fuel break ties among build-equal options; neither may outrank one
    real build step, or a mobility/fuel signal would start deciding attacks. Both are in DAMAGE units
    BEFORE the scale, so this constraint is scale-invariant."""
    assert 0 < _ATTACH_RETREAT_EQUITY < steps["min"]
    assert 0 < _ATTACH_ABILITY_FUEL < steps["min"]


@pytest.mark.req("REQ-ATTACH-BANDS-0003")
def test_the_resource_tiebreak_orders_equals_and_nothing_more(steps):
    """Reusable-over-burst must break a tie between equal marginals without ever overturning a real
    build difference. The widest charge it can make is a one-shot's worth above a reusable Basic."""
    widest = _ATTACH_RESOURCE_TIEBREAK * (TAG_TIER["discard_eot"] - ENERGY_TIER)
    assert 0 < widest < _ATTACH_VALUE_SCALE * steps["min"]


def _effective(hid: str):
    """``[(agent, weight), …]`` — the weight each shipped agent ACTUALLY decides with: its tuned.json
    override where one exists (ADR-0018: the learned layer wins), else the authored seed."""
    out = []
    for agent, _strategy in _strategies():
        tuned = REPO / "src" / "agents" / agent / "tuned.json"
        overrides = json.loads(tuned.read_text(encoding="utf-8")) if tuned.exists() else {}
        out.append((agent, float(overrides.get(hid, _weight(hid)))))
    return out


@pytest.mark.req("REQ-ATTACH-BANDS-0004")
def test_the_active_preference_prior_cannot_override_a_build_step(steps):
    """`prefer-active-attach-in-setup` is a POSITIONAL prior: it may order a dead heat, never make a
    zero-build Active beat a body that gains real progress. Its shadow-era +8 was sized against a flat
    +15 rung floor and is worth a whole build step against a continuous marginal — the exact weight
    coincidence this swap removes."""
    assert 0 < _weight("prefer-active-attach-in-setup") < _ATTACH_VALUE_SCALE * steps["min"]


@pytest.mark.req("REQ-ATTACH-BANDS-0007")
@pytest.mark.parametrize("hid,band", [
    ("prefer-active-attach-in-setup", "below one scaled build step"),
    ("feed-the-line-for-disruptor-lock", "above one scaled max pre-evolution build step"),
])
def test_the_shipped_tuned_layer_respects_the_bands(steps, hid, band):
    """The band constraints must hold on the weight each agent DECIDES with, not just on the authored
    seed: tuned.json wins over the seed (ADR-0018), so a fit made against the old flat-rung ladder can
    reintroduce exactly the weight coincidence the swap removed. mega_starmie shipped
    `prefer-active-attach-in-setup` at 11.0 — nearly two full build steps — until this pin existed.
    A future Tuner run that re-fits either survivor has to clear its band or fail here."""
    lo, hi = ((0.0, _ATTACH_VALUE_SCALE * steps["min"]) if hid == "prefer-active-attach-in-setup"
              else (_ATTACH_VALUE_SCALE * steps["max_preevo"],
                    2 * _ATTACH_VALUE_SCALE * steps["max_preevo"]))
    for agent, weight in _effective(hid):
        assert lo < weight <= hi, f"{agent} ships {hid} at {weight}, outside its band ({band})"


@pytest.mark.req("REQ-ATTACH-BANDS-0005")
def test_the_disruptor_lock_weight_beats_a_bench_recipient_by_design_and_no_more(steps):
    """The item-lock maneuver deliberately spends the Energy on the enabling retreat, so its rung must
    clear the biggest build step a bench recipient could offer instead — and stop there, so it stays a
    structural claim rather than a new positive value term."""
    floor = _ATTACH_VALUE_SCALE * steps["max_preevo"]
    assert floor < _weight("feed-the-line-for-disruptor-lock") <= 2 * floor


@pytest.mark.req("REQ-ATTACH-BANDS-0006")
def test_only_the_three_structure_rungs_survive():
    """The deletion is the ruling (ADR-0069 §7): 19 rungs are GONE, not suppressed, so no dead weight
    coincidence can re-enter tuning. `use-acceleration` is PLAY-side and currency-clean; the other two
    are band-constrained above."""
    assert {h.id for h in HYPOTHESES} == {
        "use-acceleration", "prefer-active-attach-in-setup", "feed-the-line-for-disruptor-lock"}
