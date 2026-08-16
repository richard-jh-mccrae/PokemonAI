"""Typed, immutable parameters that shape Pilot search but never Bellman utility ownership."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    group: str
    default: float
    minimum: float
    maximum: float
    units: str
    learnable: bool = True
    family: str = "pilot"


DEFINITIONS = (
    ParameterDefinition("attachment.value_scale", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="attachment"),
    ParameterDefinition("attachment.attack_axis_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="attachment"),
    ParameterDefinition("attachment.ability_fuel", "value_equations", 3.0, 0.0, 30.0,
                        "multiplier", family="attachment"),
    ParameterDefinition("attachment.other_benefit_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="attachment"),
    ParameterDefinition("attachment.cost_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="attachment"),
    ParameterDefinition("attachment.resource_tiebreak", "value_equations", 0.05, 0.0, 1.0,
                        "score/card", family="attachment"),
    ParameterDefinition("deployment.value_scale", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="deployment"),
    ParameterDefinition("deployment.assignment_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="deployment"),
    ParameterDefinition("deployment.ability_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="deployment"),
    ParameterDefinition("deployment.acceleration_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="deployment"),
    ParameterDefinition("deployment.exposure_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="deployment"),
    ParameterDefinition("evolution.value_scale", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="evolution"),
    ParameterDefinition("evolution.deploy_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="evolution"),
    ParameterDefinition("evolution.income_gain_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="evolution"),
    ParameterDefinition("evolution.income_loss_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="evolution"),
    ParameterDefinition("promote_retreat.value_scale", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("promote_retreat.yield_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("promote_retreat.closure_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("promote_retreat.tempo_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("promote_retreat.fatal_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("promote_retreat.resource_cost_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="promote_retreat"),
    ParameterDefinition("snipe.value_scale", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="snipe"),
    ParameterDefinition("snipe.their_plan_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="snipe"),
    ParameterDefinition("snipe.my_route_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="snipe"),
    ParameterDefinition("snipe.cost_weight", "value_equations", 1.0, 0.0, 10.0,
                        "multiplier", family="snipe"),
    ParameterDefinition("family.tie_margin", "family_ranking", 0.01, 0.0, 2.0, "score"),
    ParameterDefinition("family.near_tie_batch_size", "family_ranking", 1.0, 1.0, 64.0,
                        "actions", False),
    *(ParameterDefinition(f"family.{family}_{mode}", "family_ranking",
                          0.0, 0.0, 1.0,
                          "boolean", False, family=family)
      for family in ("attachment", "deployment", "evolution", "promote_retreat", "snipe")
      for mode in ("shadow", "ordering", "widening")),
    ParameterDefinition("search.max_nodes", "search_waves", 4000.0, 1.0, 100000.0,
                        "nodes", False),
    ParameterDefinition("search.runtime_nodes_per_root", "search_waves", 256.0, 1.0, 100000.0,
                        "nodes", False),
    ParameterDefinition("search.chance_max_nodes", "search_waves", 600.0, 1.0, 100000.0,
                        "nodes", False),
    ParameterDefinition("search.reveal_max_nodes", "search_waves", 1300.0, 1.0, 100000.0,
                        "nodes", False),
    ParameterDefinition("search.beam_width", "search_waves", 16.0, 1.0, 256.0,
                        "actions", False),
    ParameterDefinition("search.root_beam_width", "search_waves", 16.0, 1.0, 256.0,
                        "actions", False),
    ParameterDefinition("search.effect_choice_width", "search_waves", 64.0, 1.0, 512.0,
                        "actions", False),
    ParameterDefinition("search.shallow_nodes", "search_waves", 96.0, 1.0, 10000.0,
                        "nodes", False),
    ParameterDefinition("search.refinement_width", "search_waves", 2.0, 0.0, 64.0,
                        "actions", False),
    ParameterDefinition("search.completed_candidate_target", "search_waves", 3.0, 2.0, 32.0,
                        "lines", False),
    ParameterDefinition("search.completed_candidate_time_share", "search_waves", 0.20, 0.0, 1.0,
                        "decision_clock_share", False),
    ParameterDefinition("search.uncertainty_margin", "search_waves", 0.10, 0.0, 10.0,
                        "bellman_value"),
    ParameterDefinition("search.information_dominance_enabled", "search_waves", 1.0, 0.0, 1.0,
                        "boolean", False),
    ParameterDefinition("strategy.focus_enabled", "strategy_beam", 1.0, 0.0, 1.0,
                        "boolean", False),
    ParameterDefinition("strategy.focus_width", "strategy_beam", 8.0, 1.0, 64.0,
                        "actions"),
    ParameterDefinition("terminal.enabled", "terminal_proof", 1.0, 0.0, 1.0,
                        "boolean", False),
    ParameterDefinition("terminal.max_nodes", "terminal_proof", 1024.0, 1.0, 100000.0,
                        "nodes", False),
    ParameterDefinition("terminal.max_seconds", "terminal_proof", 0.25, 0.01, 60.0,
                        "seconds", False),
    ParameterDefinition("terminal.max_decisions", "terminal_proof", 16.0, 1.0, 64.0,
                        "decisions", False),
    ParameterDefinition("clock.remaining_600_seconds", "planning_clock", 30.0, 2.0, 3600.0,
                        "seconds", False),
    ParameterDefinition("clock.remaining_200_seconds", "planning_clock", 15.0, 2.0, 3600.0,
                        "seconds", False),
    ParameterDefinition("clock.remaining_140_seconds", "planning_clock", 10.0, 2.0, 3600.0,
                        "seconds", False),
    ParameterDefinition("clock.emergency_seconds", "planning_clock", 2.0, 0.1, 15.0,
                        "seconds", False),
    ParameterDefinition("clock.adaptive_enabled", "planning_clock", 0.0, 0.0, 1.0,
                        "boolean", False),
    ParameterDefinition("belief.unknown_mass", "belief", 1.0, 0.0, 1.0, "probability"),
    # Arming ADR-0060's opponent strip/gift pricing is a corpus/ladder measurement round —
    # the graded corpus margins predate the term.
    ParameterDefinition("value.opponent_hand_share", "bellman_value", 0.0, 0.0, 1.0,
                        "multiplier", False),
    ParameterDefinition("plan_reuse.enabled", "plan_reuse", 1.0, 0.0, 1.0, "boolean", False),
    ParameterDefinition("scouting.posture_scale", "scouting", 1.0, 0.0, 2.0, "multiplier"),
    ParameterDefinition("telemetry.family_detail", "diagnostics", 0.0, 0.0, 1.0,
                        "boolean", False),
)

_BY_NAME = {definition.name: definition for definition in DEFINITIONS}
if len(_BY_NAME) != len(DEFINITIONS):
    raise RuntimeError("duplicate Pilot parameter name")


@dataclass(frozen=True)
class ResolvedParameter:
    definition: ParameterDefinition
    global_value: float
    deck_learned_adjustment: float
    authored_deck_override: float | None
    effective: float

    def as_dict(self) -> dict:
        definition = self.definition
        return {
            "name": definition.name, "group": definition.group, "family": definition.family,
            "global": self.global_value, "deck_learned_adjustment": self.deck_learned_adjustment,
            "authored_deck_override": self.authored_deck_override,
            "effective": self.effective, "minimum": definition.minimum,
            "maximum": definition.maximum, "units": definition.units,
            "learnable": definition.learnable,
        }


class PilotProfile:
    def __init__(self, rows: tuple[ResolvedParameter, ...], provenance: str = "authored-defaults"):
        self._rows = rows
        self._values = MappingProxyType({row.definition.name: row.effective for row in rows})
        self.provenance = str(provenance)
        payload = {"parameters": [row.as_dict() for row in rows], "provenance": self.provenance}
        self.hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @classmethod
    def resolve(cls, *, global_values: Mapping[str, float] | None = None,
                deck_learned: Mapping[str, float] | None = None,
                authored_deck_overrides: Mapping[str, float] | None = None,
                provenance: str = "authored-defaults") -> "PilotProfile":
        layers = (
            dict(global_values or {}), dict(deck_learned or {}),
            dict(authored_deck_overrides or {}),
        )
        unknown = set().union(*(set(layer) for layer in layers)) - set(_BY_NAME)
        if unknown:
            raise ValueError(f"unknown Pilot parameter(s): {sorted(unknown)}")
        rows = []
        for definition in DEFINITIONS:
            global_value = float(layers[0].get(definition.name, definition.default))
            if not definition.minimum <= global_value <= definition.maximum:
                raise ValueError(f"{definition.name} global value is out of bounds")
            learned = float(layers[1].get(definition.name, 0.0))
            authored = (float(layers[2][definition.name])
                        if definition.name in layers[2] else None)
            if authored is not None and not definition.minimum <= authored <= definition.maximum:
                raise ValueError(f"{definition.name} authored override is out of bounds")
            effective = (authored if authored is not None else min(
                definition.maximum, max(definition.minimum, global_value + learned)))
            rows.append(ResolvedParameter(definition, global_value, learned, authored, effective))
        return cls(tuple(rows), provenance)

    def get(self, name: str) -> float:
        try:
            return self._values[name]
        except KeyError as exc:
            raise KeyError(f"unregistered Pilot parameter: {name}") from exc

    @property
    def rows(self) -> tuple[ResolvedParameter, ...]:
        return self._rows

    def grouped(self) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for row in self._rows:
            groups.setdefault(row.definition.group, []).append(row.as_dict())
        return groups

    def as_dict(self) -> dict:
        return {"hash": self.hash, "provenance": self.provenance,
                "groups": self.grouped()}

    def planning_seconds(self, remaining_overage: float | None) -> float:
        if remaining_overage is None:
            remaining_overage = 200.0
        remaining = max(0.0, float(remaining_overage))
        anchors = (
            (0.0, self.get("clock.emergency_seconds")),
            (140.0, self.get("clock.remaining_140_seconds")),
            (200.0, self.get("clock.remaining_200_seconds")),
            (600.0, self.get("clock.remaining_600_seconds")),
        )
        if remaining >= anchors[-1][0]:
            return anchors[-1][1]
        for (left_x, left_y), (right_x, right_y) in zip(anchors, anchors[1:]):
            if left_x <= remaining <= right_x:
                ratio = (remaining - left_x) / (right_x - left_x)
                return left_y + ratio * (right_y - left_y)
        return anchors[0][1]


DEFAULT_PILOT_PROFILE = PilotProfile.resolve()


__all__ = ("DEFAULT_PILOT_PROFILE", "DEFINITIONS", "ParameterDefinition", "PilotProfile",
           "ResolvedParameter")
