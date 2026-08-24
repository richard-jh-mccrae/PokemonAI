"""Pure shadow value equations over one canonical Bellman transition ledger."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .algebra import BellmanLedger
from .pilot_profile import PilotProfile


@dataclass(frozen=True)
class EquationResult:
    features: tuple[tuple[str, float], ...]
    contributions: tuple[tuple[str, float], ...]
    score: float


def _sum(rows, names) -> float:
    values = dict(rows)
    return sum(float(values.get(name, 0.0)) for name in names)


def _net(ledger: BellmanLedger, names) -> float:
    return _sum(ledger.benefits, names) - _sum(ledger.costs, names)


def _result(features, contributions) -> EquationResult:
    feature_rows = tuple((name, float(value)) for name, value in features)
    contribution_rows = tuple((name, float(value)) for name, value in contributions)
    score = sum(value for _name, value in contribution_rows)
    if not math.isfinite(score):
        raise ValueError("non-finite value-equation score")
    return EquationResult(feature_rows, contribution_rows, score)


def attachment(ledger: BellmanLedger, profile: PilotProfile, *, resource_premium=0.0) -> EquationResult:
    attack = max((_sum(ledger.benefits, (name,)) for name in (
        "board", "development", "energy_position", "multi_target_ko")), default=0.0)
    ability = _sum(ledger.benefits, ("readiness",))
    owned = {"board", "development", "energy_position", "multi_target_ko", "readiness"}
    other = sum(value for name, value in ledger.benefits if name not in owned)
    costs = sum(value for _name, value in ledger.costs)
    scale = profile.get("attachment.value_scale")
    features = (("attack_axis", attack), ("ability_fuel", ability),
                ("other_benefits", other), ("costs", costs),
                ("resource_premium", resource_premium))
    contributions = (
        ("attack_axis", attack * profile.get("attachment.attack_axis_weight") * scale),
        ("ability_fuel", ability * profile.get("attachment.ability_fuel") * scale),
        ("other_benefits", other * profile.get("attachment.other_benefit_weight") * scale),
        ("costs", -costs * profile.get("attachment.cost_weight") * scale),
        ("resource_tiebreak",
         -resource_premium * profile.get("attachment.resource_tiebreak")),
    )
    return _result(features, contributions)


def deployment(ledger: BellmanLedger, profile: PilotProfile) -> EquationResult:
    assignment = _net(ledger, ("board", "development"))
    ability = _net(ledger, ("hand", "hand_demand"))
    acceleration = _net(ledger, ("energy_position", "readiness"))
    owned = {"board", "development", "hand", "hand_demand", "energy_position", "readiness"}
    exposure = sum(value for name, value in ledger.costs if name not in owned)
    scale = profile.get("deployment.value_scale")
    features = (("assignment_relevance", assignment), ("ability_relevance", ability),
                ("accel_unlock", acceleration), ("exposure", exposure))
    contributions = (
        ("assignment_relevance", assignment * profile.get("deployment.assignment_weight") * scale),
        ("ability_relevance", ability * profile.get("deployment.ability_weight") * scale),
        ("accel_unlock", acceleration * profile.get("deployment.acceleration_weight") * scale),
        ("exposure", -exposure * profile.get("deployment.exposure_weight") * scale),
    )
    return _result(features, contributions)


def evolution(ledger: BellmanLedger, profile: PilotProfile) -> EquationResult:
    deploy = _net(ledger, ("board", "development", "readiness", "energy_position"))
    income = _net(ledger, ("hand", "hand_demand"))
    gain, loss = max(0.0, income), max(0.0, -income)
    scale = profile.get("evolution.value_scale")
    features = (("deploy", deploy), ("income_gain", gain), ("income_loss", loss))
    contributions = (
        ("deploy", deploy * profile.get("evolution.deploy_weight") * scale),
        ("income_gain", gain * profile.get("evolution.income_gain_weight") * scale),
        ("income_loss", -loss * profile.get("evolution.income_loss_weight") * scale),
    )
    return _result(features, contributions)


def promote_retreat(ledger: BellmanLedger, profile: PilotProfile) -> EquationResult:
    my_yield = _sum(ledger.benefits, ("damage", "readiness", "multi_target_ko"))
    closure = _sum(ledger.benefits, ("prize_plan",))
    tempo = _sum(ledger.benefits, ("opponent_roles",))
    fatal = _sum(ledger.costs, ("game", "prize_race"))
    resource = sum(value for name, value in ledger.costs if name not in {"game", "prize_race"})
    scale = profile.get("promote_retreat.value_scale")
    features = (("my_yield", my_yield), ("closure", closure), ("tempo_denied", tempo),
                ("fatal", fatal), ("resource_cost", resource))
    contributions = (
        ("my_yield", my_yield * profile.get("promote_retreat.yield_weight") * scale),
        ("closure", closure * profile.get("promote_retreat.closure_weight") * scale),
        ("tempo_denied", tempo * profile.get("promote_retreat.tempo_weight") * scale),
        ("fatal", -fatal * profile.get("promote_retreat.fatal_weight") * scale),
        ("resource_cost", -resource * profile.get("promote_retreat.resource_cost_weight") * scale),
    )
    return _result(features, contributions)


def snipe(ledger: BellmanLedger, profile: PilotProfile) -> EquationResult:
    their_plan = _sum(ledger.benefits, ("opponent_roles", "readiness"))
    my_route = _sum(ledger.benefits, ("damage", "prize_plan", "prize_race"))
    costs = sum(value for _name, value in ledger.costs)
    plan = their_plan * profile.get("snipe.their_plan_weight")
    route = my_route * profile.get("snipe.my_route_weight")
    scale = profile.get("snipe.value_scale")
    features = (("their_plan", their_plan), ("my_route", my_route), ("costs", costs))
    contributions = (("relevance", plan * route * scale),
                     ("costs", -costs * profile.get("snipe.cost_weight") * scale))
    return _result(features, contributions)


SCORERS = {
    "attachment": attachment,
    "deployment": deployment,
    "evolution": evolution,
    "promote_retreat": promote_retreat,
    "snipe": snipe,
}


__all__ = ("EquationResult", "SCORERS", "attachment", "deployment", "evolution",
           "promote_retreat", "snipe")
