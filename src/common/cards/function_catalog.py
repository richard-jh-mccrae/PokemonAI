from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    kind: str
    parameters: frozenset[str]
    parameter_types: MappingProxyType


class FunctionCatalog:
    def __init__(self, schemas):
        self._specs = MappingProxyType({
            kind: FunctionSpec(kind, frozenset(parameters), MappingProxyType({
                name: _PARAMETER_TYPES[name] for name in parameters}))
            for kind, parameters in schemas.items()})

    def __contains__(self, kind) -> bool:
        return str(kind) in self._specs

    def __getitem__(self, kind: str) -> FunctionSpec:
        return self._specs[str(kind)]

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def compile(self, clauses) -> tuple:
        compiled = tuple(clauses or ())
        for clause in compiled:
            if clause.kind not in self:
                raise KeyError(f"unknown card Function {clause.kind!r}")
            unknown = set(clause.params) - self[clause.kind].parameters
            if unknown:
                raise KeyError(
                    f"unknown {clause.kind!r} parameter {sorted(unknown)[0]!r}")
            for name, value in clause.params.items():
                expected = self[clause.kind].parameter_types[name]
                if not isinstance(value, expected):
                    labels = ", ".join(item.__name__ for item in expected)
                    raise TypeError(f"{clause.kind!r} parameter {name!r} requires {labels}")
        return compiled


def card_clauses(record) -> tuple:
    direct = tuple(getattr(record, "clauses", ()) or ())
    abilities = tuple(clause for ability in getattr(record, "abilities", ()) or ()
                      for clause in ability.clauses)
    attacks = tuple(clause for attack in getattr(record, "attacks", ()) or ()
                    for clause in attack.clauses)
    return (*direct, *abilities, *attacks)


_PARAMETER_TYPES = {
    "allowance": (str,), "amount": (int, str), "amount_if": (dict,),
    "amount_on_evolution": (int,), "amount_per": (str,), "applies_to": (str,),
    "attack": (str,), "choice": (bool,), "chooser": (str,), "condition": (str,),
    "condition_energy_type": (int,), "cost": (str,), "cost_required": (bool,),
    "cost_units": (list,), "count": (int, str), "dest": (str,), "dig": (int,),
    "dig_from": (str,), "distinct_types": (bool,), "duration": (str,),
    "each_of": (bool,), "effect": (str,), "energy": (str,), "energy_type": (int,),
    "evolves_into_type": (int,), "exclude_name": (str,), "granted_action": (bool,),
    "hp_max": (int,), "includes_effects": (bool,), "name": (str,),
    "name_family": (str,), "named": (str,), "new_weakness": (int,),
    "no_ability": (bool,), "no_rule_box": (bool,), "no_stack": (bool,), "on": (str,),
    "opponent_amount": (int,), "opponent_amount_if": (dict,), "optional": (bool,),
    "per": (str,), "random": (bool,), "remaining_hp": (int,), "restriction": (str,),
    "rider": (str,), "rider_amount": (int,), "rider_energy_type": (int,),
    "scope": (str,), "source": (str,), "source_class": (str,), "symmetric": (bool,),
    "target": (str,), "target_class": (str,), "target_condition": (str,),
    "target_type": (int,), "timing": (str,), "to_hand": (int,),
    "to_hand_size": (int,), "trigger": (str,), "type": (str,), "window": (int,),
    "zone": (str,),
}


_SCHEMAS = {
    'ability_suppression': ('applies_to', 'condition', 'symmetric', 'target'),
    'accel': ('allowance', 'amount', 'condition', 'dig', 'distinct_types', 'each_of', 'energy', 'energy_type', 'rider', 'source', 'target', 'target_type', 'to_hand', 'trigger', 'zone'),
    'attack_cost_reduction': ('amount', 'applies_to', 'attack', 'condition', 'cost_units', 'energy_type', 'name_family'),
    'attack_debuff': ('amount', 'duration', 'target', 'timing'),
    'attack_lock': ('duration',), 'attack_twice': ('condition',),
    'bench_snipe': ('amount', 'cost', 'count', 'optional', 'restriction', 'target'),
    'bench_spread': ('amount', 'target'),
    'checkup_trigger': ('amount', 'applies_to', 'each_of', 'effect', 'exclude_name', 'symmetric'),
    'coin': ('amount', 'count', 'duration', 'effect', 'includes_effects', 'per', 'rider', 'scope', 'target'),
    'confuse': ('target',), 'copy_attack': ('name_family', 'no_rule_box', 'source'),
    'cost_reduction': ('amount', 'condition'),
    'damage_boost': ('amount', 'applies_to', 'condition', 'energy_type', 'name_family', 'named', 'no_rule_box', 'no_stack', 'optional', 'per', 'rider', 'rider_amount', 'target', 'target_class', 'timing'),
    'damage_counters': ('allowance', 'amount', 'per', 'rider', 'target'),
    'damage_protection': ('duration', 'source_class'),
    'damage_reduction': ('amount', 'duration', 'timing'),
    'deck_top': ('amount', 'dest', 'granted_action', 'source', 'symmetric'),
    'discard_opp_energy': ('amount', 'energy'),
    'draw': ('allowance', 'amount', 'amount_if', 'amount_per', 'condition', 'cost', 'cost_required', 'opponent_amount', 'opponent_amount_if', 'rider', 'rider_amount', 'rider_energy_type', 'to_hand_size', 'trigger', 'window'),
    'energy_bounce': ('amount', 'dest', 'target'),
    'energy_double': ('applies_to', 'energy', 'energy_type', 'no_stack'),
    'energy_provide': ('amount', 'amount_on_evolution', 'rider', 'type'),
    'energy_recur': ('amount', 'energy_type', 'target', 'trigger', 'zone'),
    'evolve_early': ('condition',),
    'fetch': ('allowance', 'amount', 'choice', 'condition', 'cost', 'cost_required', 'dest', 'dig', 'dig_from', 'distinct_types', 'energy_type', 'hp_max', 'name_family', 'no_ability', 'no_rule_box', 'restriction', 'rider', 'target', 'target_condition', 'target_type', 'trigger', 'zone'),
    'first_turn_attack_permission': ('condition',), 'grant_prevo_attacks': ('applies_to',),
    'gust': ('amount', 'condition', 'name_family', 'rider', 'target', 'trigger'),
    'heal': ('amount', 'condition', 'each_of', 'restriction', 'rider', 'target'),
    'hp_bonus': ('amount', 'amount_per', 'energy_type', 'name_family'),
    'ignores_effects': (), 'ignores_wr': ('scope',), 'item_lock': ('duration',),
    'ko': ('target',), 'mill': ('amount', 'target'),
    'move_damage': ('allowance', 'amount', 'condition', 'condition_energy_type', 'dest', 'optional', 'zone'),
    'move_energy': ('amount', 'dest', 'source', 'trigger'),
    'no_retreat': ('duration', 'target'), 'no_weakness': ('duration',),
    'opp_hand_to_deck': ('amount', 'random'),
    'prevent_damage': ('applies_to', 'condition', 'includes_effects', 'no_rule_box', 'source', 'source_class'),
    'prevent_effects': ('applies_to', 'name_family', 'source', 'target_type'),
    'push_out': ('chooser',), 'recoil': ('amount',), 'requires_bench': ('name',),
    'requires_bench_count': ('amount',), 'requires_stadium': (),
    'retreat_lock': ('duration', 'target'),
    'retreat_reduction': ('amount', 'applies_to'), 'same_attack_lock': ('duration',),
    'self_discard_energy': ('amount',), 'self_mill': ('amount',),
    'self_return': ('dest',), 'self_shuffle_in': ('allowance', 'condition'),
    'self_switch': ('allowance', 'exclude_name', 'rider', 'target', 'target_type'),
    'setup_active': ('trigger',), 'sleep': ('target',),
    'stadium_static': ('amount', 'applies_to', 'condition', 'effect', 'evolves_into_type', 'name_family', 'rider', 'source', 'source_class', 'symmetric', 'target', 'timing'),
    'stadium_trigger': ('amount', 'applies_to', 'effect', 'on', 'symmetric'),
    'survive_ko': ('condition', 'remaining_hp', 'source'), 'switch_self': (),
    'weakness_override': ('new_weakness', 'target'),
}


FUNCTION_CATALOG = FunctionCatalog(_SCHEMAS)


__all__ = ("FUNCTION_CATALOG", "FunctionCatalog", "FunctionSpec", "card_clauses")
