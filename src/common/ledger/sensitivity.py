from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from types import MappingProxyType, SimpleNamespace

from common.cards import card_clauses, card_store
from common.cards.card_facts import Clause, EnergyCard, PokemonCard, TrainerCard
from common.cards.functions.fetch import DEADNESS, fetch_target_matches
from common.observation import ObservationStateBuilder
from common.observation.knowledge import (
    KnownAttackLocks, KnownDeckTop, KnownOwnPrizes, LegalKnowledge, OpponentBelief,
    OpponentCandidatePosterior, OpponentDecisionEvidence,
)
from common.observation.nodes import (
    Card, HiddenHand, Looking, Option, SelectPrompt, VisibleHand, card_bag,
)
from common.observation.state import AttackEvent, MoveCardEvent

from .activation import ActivationCompiler, ActivationEnvironment
from .capabilities import body_capability, card_option_value
from .coverage import (
    CLAUSE_VALUATION_CONTRACTS, ClauseValuationMode, DirectEquationOwner,
    clause_parameter_mode, clause_parameter_sensitivity_contract,
)
from .features import FEATURE_CATALOG, ActivationRule
from .worth import Demand, EvaluationModel, _model_identity, content_identity


@dataclass(frozen=True, slots=True)
class SensitivityWitness:
    identity: str
    feature: str
    source: str
    claim: str
    rule: ActivationRule


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    identity: str
    feature: str
    activation: float
    contribution: float
    passed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationSensitivityResult:
    identity: str
    features: tuple[str, ...]
    changed_features: tuple[str, ...]
    contribution_delta: float
    passed: bool


@dataclass(frozen=True, slots=True)
class ObservationSensitivityWitness:
    identity: str
    features: tuple[str, ...]
    expected_nonzero: bool


@dataclass(frozen=True, slots=True)
class ClauseSensitivityResult:
    identity: str
    contribution_delta: float
    passed: bool
    reason: str | None = None
    expected_feature: str | None = None
    feature_delta: float | None = None
    expected_direction: int | None = None


@dataclass(frozen=True, slots=True)
class ParameterSensitivityWitness:
    identity: str
    parameter: str
    value: object
    placement: str
    card_id: int
    kind: str
    locator: tuple[object, ...]
    expected_feature: str | None
    expected_direction: int | None


def _witnesses():
    rows = {}
    for spec in FEATURE_CATALOG.priced_specs:
        rule = spec.rules[0]
        identity = f"feature:{spec.key}"
        rows[identity] = SensitivityWitness(
            identity, spec.key, rule.source, rule.claims[0], rule)
    return MappingProxyType(rows)


SENSITIVITY_WITNESSES = _witnesses()


def _observation_witnesses():
    from .coverage import OBSERVATION_FIELD_EXPECTATIONS, OBSERVATION_FIELD_FEATURES

    return MappingProxyType({
        identity: ObservationSensitivityWitness(
            identity, tuple(OBSERVATION_FIELD_FEATURES.get(identity, ())), expected)
        for identity, expected in OBSERVATION_FIELD_EXPECTATIONS.items()
    })


OBSERVATION_SENSITIVITY_WITNESSES = _observation_witnesses()


def _clause_occurrences(facts):
    if isinstance(facts, (TrainerCard, EnergyCard)):
        placement = "trainer" if isinstance(facts, TrainerCard) else "energy"
        for index, clause in enumerate(facts.clauses):
            yield placement, ("clauses", index), clause
    elif isinstance(facts, PokemonCard):
        for owner_index, ability in enumerate(facts.abilities):
            for clause_index, clause in enumerate(ability.clauses):
                yield "ability", ("abilities", owner_index, clause_index), clause
        for owner_index, attack in enumerate(facts.attacks):
            for clause_index, clause in enumerate(attack.clauses):
                yield "attack", ("attacks", owner_index, clause_index), clause


def _parameter_witnesses():
    rows = {}
    store = card_store()
    for card_id, facts in sorted(store.items()):
        for placement, locator, clause in _clause_occurrences(facts):
            for parameter, value in clause.params.items():
                if clause_parameter_mode(
                        parameter, value, placement,
                        clause.kind) is not ClauseValuationMode.DIRECT_EQUATION:
                    continue
                value_id = json.dumps(value, sort_keys=True, separators=(",", ":"))
                path = ".".join(str(item) for item in locator)
                identity = (
                    f"parameter:{parameter}={value_id}:{placement}:{clause.kind}:"
                    f"{card_id}:{path}")
                expected_feature, expected_direction = \
                    clause_parameter_sensitivity_contract(
                        parameter, value, clause, placement)
                rows[identity] = ParameterSensitivityWitness(
                    identity, parameter, value, placement, card_id, clause.kind, locator,
                    expected_feature, expected_direction)
    return MappingProxyType(rows)


PARAMETER_SENSITIVITY_WITNESSES = _parameter_witnesses()


def run_sensitivity_witness(witness: SensitivityWitness,
                            ctx: EvaluationModel) -> SensitivityResult:
    activations = ActivationCompiler().compile(
        witness.source, (witness.claim,), _environment(witness, ctx))
    activation = next((item.value for item in activations
                       if item.feature == witness.feature), 0.0)
    contribution = activation * ctx.configuration[witness.feature]
    reason = ("zero activation" if activation == 0.0 else
              "zero contribution" if contribution == 0.0 else None)
    return SensitivityResult(
        witness.identity, witness.feature, activation, contribution,
        reason is None, reason)


def card_probe_contribution(card_id: int, ctx: EvaluationModel) -> float:
    from .evaluate import evaluate

    facts = ctx.facts(card_id)
    board = _rich_board()
    if isinstance(facts, PokemonCard):
        body = _body_for_facts(board.me.active, facts, serial=7400)
        after = replace(board, me=replace(
            board.me, bench=(*board.me.bench[:-1], body)))
    else:
        cards = (*tuple(board.me.hand), Card(card_id, 7400, board.seat))
        after = replace(board, me=replace(
            board.me, hand=VisibleHand(card_bag([
                {"id": card.card_id, "serial": card.serial,
                 "playerIndex": card.owner} for card in cards])),
            hand_count=len(cards)))
    return evaluate(after, ctx).total - evaluate(board, ctx).total


def run_observation_sensitivity(identity: str, features, ctx: EvaluationModel,
                                *, expected_nonzero=True):
    from .evaluate import evaluate
    from .worth import OpponentProfile
    from common.opponent import OpponentTrait

    if identity.startswith("Opponent"):
        ctx = replace(ctx, opponent_profiles=MappingProxyType({
            "fast": OpponentProfile({}, (OpponentTrait("tempo", "fast"),), (), {}),
            "slow": OpponentProfile({}, (OpponentTrait("tempo", "slow"),), (), {}),
        }))

    before, after = _perturb_observation(identity, _rich_board(), ctx)
    before_values = {item.feature: item.value for item in evaluate(before, ctx).activations}
    after_values = {item.feature: item.value for item in evaluate(after, ctx).activations}
    changed = tuple(sorted(feature for feature in features
                           if before_values.get(feature, 0.0)
                           != after_values.get(feature, 0.0)))
    contribution_delta = evaluate(after, ctx).total - evaluate(before, ctx).total
    passed = ((bool(changed) and contribution_delta != 0.0) if expected_nonzero
              else not changed and contribution_delta == 0.0)
    return ObservationSensitivityResult(
        identity, tuple(features), changed, contribution_delta,
        passed)


def run_clause_sensitivity(contract, ctx: EvaluationModel) -> ClauseSensitivityResult:
    facts_rows = tuple(facts for facts in ctx.store.values()
                       if any(clause.kind == contract.kind
                              for clause in card_clauses(facts)))
    if not facts_rows:
        return ClauseSensitivityResult(
            contract.witness, 0.0, False, "no real card carries the clause")
    executor = DIRECT_EQUATION_EXECUTORS.get(contract.owner)
    if executor is None:
        return ClauseSensitivityResult(
            contract.witness, 0.0, False,
            f"direct owner {contract.owner.value} has no executable equation")
    contribution = max(
        (executor(contract, facts, ctx) for facts in facts_rows),
        key=abs)
    reason = None if contribution != 0.0 else "direct equation produced zero valuation delta"
    return ClauseSensitivityResult(
        contract.witness, contribution, reason is None, reason)


def run_parameter_sensitivity(witness, ctx):
    facts = ctx.facts(witness.card_id)
    contract = CLAUSE_VALUATION_CONTRACTS[witness.kind]
    contribution, feature_delta = _direct_parameter_contributions(
        contract, facts, ctx,
        parameter=witness.parameter,
        locator=witness.locator,
        feature=witness.expected_feature,
        transform=lambda value: _perturb_parameter_at(
            value, witness.locator, witness.parameter, witness.kind))
    reason = None
    if contribution == 0.0:
        reason = "parameter perturbation produced zero valuation delta"
    elif witness.expected_feature is not None and feature_delta == 0.0:
        reason = f"{witness.expected_feature} produced zero valuation delta"
    elif witness.expected_direction is not None \
            and feature_delta * witness.expected_direction <= 0.0:
        actual = "positive" if feature_delta > 0 else "negative"
        expected = "positive" if witness.expected_direction > 0 else "negative"
        reason = (f"{witness.expected_feature} moved {actual}; "
                  f"expected {expected}")
    return ClauseSensitivityResult(
        witness.identity, contribution, reason is None, reason,
        witness.expected_feature, feature_delta, witness.expected_direction)


def _direct_clause_valuations(contract, facts, ctx, *, transform=None,
                              parameter=None, locator=None):
    from .evaluate import evaluate

    ctx = _clause_probe_context(ctx, facts, contract.kind, locator=locator)
    facts = ctx.facts(facts.card_id)
    probe_clauses = ((_located_clause(facts, locator),) if locator is not None else
                     tuple(clause for clause in card_clauses(facts)
                           if clause.kind == contract.kind))
    board = _rich_board()
    board = _clause_probe_board(
        board, facts, contract.kind, ctx, parameter=parameter, locator=locator)
    if contract.kind == "attack_twice":
        stadium = next((candidate for candidate in ctx.store.values()
                        if getattr(candidate, "name", None) == "Festival Grounds"), None)
        if stadium is not None:
            board = replace(board, stadium=(Card(stadium.card_id, 7600, board.seat),))
    if contract.kind == "first_turn_attack_permission":
        board = replace(board, turn=replace(
            board.turn, number=1, first_player=board.seat))
    if contract.kind == "setup_active":
        board = replace(board, turn=replace(board.turn, number=0))
    stripped = (_without_clause(facts, contract.kind) if transform is None
                else transform(facts))
    store = dict(ctx.store)
    store[facts.card_id] = stripped
    stripped_ctx = _derived_probe_context(
        ctx, store, {facts.card_id: stripped})
    if isinstance(facts, PokemonCard):
        body = _body_for_facts(board.me.active, facts)
        if parameter in {"energy_type", "rider_energy_type"}:
            wanted = next(int(getattr(clause, parameter))
                          for clause in probe_clauses
                          if getattr(clause, parameter, None) is not None)
            body = replace(body, energies=(*body.energies, wanted))
        if parameter == "amount_per" and any(
                clause.amount_per == "attached_fighting_energy"
                for clause in probe_clauses):
            body = replace(body, energies=(*body.energies, 6, 6))
        if parameter == "trigger" and any(
                clause.trigger == "on_evolve" for clause in probe_clauses):
            body = replace(body, pre_evolution=(Card(119, 7810, board.seat),))
        body = _clause_probe_body(body, facts, contract.kind)
        if contract.kind == "survive_ko":
            body = replace(body, hp=body.max_hp)
        replacement_facts = next(
            candidate for candidate in ctx.store.values()
            if isinstance(candidate, PokemonCard)
            and candidate.card_id != facts.card_id)
        side = replace(
            board.me, active=body,
            bench=tuple(
                _body_for_facts(candidate, replacement_facts)
                if candidate.card.card_id == facts.card_id
                and parameter not in {"exclude_name", "no_stack"}
                else candidate
                for candidate in board.me.bench))
        opposing = replace(
            board.them,
            active=(_body_for_facts(board.them.active, replacement_facts)
                    if board.them.active.card.card_id == facts.card_id
                    else board.them.active),
            bench=tuple(
                _body_for_facts(candidate, replacement_facts)
                if candidate.card.card_id == facts.card_id else candidate
                for candidate in board.them.bench))
        if any(clause.condition == "active_has_festival_lead"
               for clause in card_clauses(facts) if clause.kind == contract.kind):
            lead = next(candidate for candidate in ctx.store.values()
                        if isinstance(candidate, PokemonCard) and any(
                            ability.name == "Festival Lead" for ability in candidate.abilities))
            side = replace(
                side, active=_body_for_facts(side.active, lead),
                bench=(body, *side.bench[1:]))
        if contract.kind == "grant_prevo_attacks":
            target = replace(
                side.bench[0],
                pre_evolution=(Card(119, 7800, board.seat),))
            side = replace(side, bench=(target, *side.bench[1:]))
        elif contract.kind == "copy_attack":
            source = next((candidate for candidate in ctx.store.values()
                           if isinstance(candidate, PokemonCard)
                           and "n's" in candidate.name.casefold()
                           and any(attack.damage for attack in candidate.attacks)), None)
            if source is not None:
                target = _body_for_facts(side.bench[0], source, serial=7900)
                side = replace(side, bench=(target, *side.bench[1:]))
        if contract.kind == "ignores_wr":
            defender = next((candidate for candidate in ctx.store.values()
                             if isinstance(candidate, PokemonCard)
                             and (candidate.weakness == facts.energy_type
                                  or candidate.resistance == facts.energy_type)), None)
            if defender is not None:
                opposing = replace(
                    opposing, active=_body_for_facts(opposing.active, defender))
        elif contract.kind == "ignores_effects":
            defender = next((candidate for candidate in ctx.store.values()
                             if isinstance(candidate, PokemonCard)
                             and any(clause.kind == "damage_reduction" and clause.amount
                                     for clause in card_clauses(candidate))), None)
            if defender is not None:
                opposing = replace(
                    opposing, active=_body_for_facts(opposing.active, defender))
        probe_board = replace(board, me=side, them=opposing)
    elif isinstance(facts, EnergyCard):
        target = board.me.bench[0]
        attached = replace(
            target,
            energies=(*target.energies, facts.provides),
            energy_cards=(*target.energy_cards,
                          Card(facts.card_id, 7500, board.seat)))
        probe_board = replace(board, me=replace(
            board.me, bench=(attached, *board.me.bench[1:])))
    else:
        cards = (*tuple(board.me.hand), Card(facts.card_id, 7500, board.seat))
        probe_board = replace(board, me=replace(
            board.me, hand=VisibleHand(card_bag([
                {"id": card.card_id, "serial": card.serial,
                 "playerIndex": card.owner} for card in cards])),
            hand_count=max(len(cards), board.me.hand_count)))
    return evaluate(probe_board, ctx), evaluate(probe_board, stripped_ctx)


def _located_clause(facts, locator):
    collection, owner_index, *tail = locator
    if collection == "clauses":
        return facts.clauses[owner_index]
    return getattr(facts, collection)[owner_index].clauses[tail[0]]


def _derived_probe_context(ctx, store, overrides):
    probe = object.__new__(EvaluationModel)
    object.__setattr__(probe, "configuration", ctx.configuration)
    object.__setattr__(probe, "store", MappingProxyType(store))
    object.__setattr__(probe, "prize_plan", ctx.prize_plan)
    object.__setattr__(probe, "opponent_profiles", ctx.opponent_profiles)
    object.__setattr__(probe, "store_identity", content_identity((
        ctx.store_identity, overrides)))
    object.__setattr__(probe, "_identity", _model_identity(
        probe.configuration, probe.store_identity, probe.prize_plan,
        probe.opponent_profiles))
    return probe


def _clause_probe_context(ctx, facts, kind, *, locator=None):
    clauses = ((_located_clause(facts, locator),) if locator is not None else
               tuple(clause for clause in card_clauses(facts) if clause.kind == kind))
    store = dict(ctx.store)
    overrides = {}
    for clause in clauses:
        pokemon_target = (clause.kind == "fetch"
                          and clause.target not in {"basic_energy", "energy"})
        if pokemon_target or clause.energy_type is None or any(
                    isinstance(candidate, EnergyCard)
                    and candidate.provides == int(clause.energy_type)
                    for candidate in store.values()):
            continue
        synthetic_id = 9_999_990 + int(clause.energy_type)
        overrides[synthetic_id] = store[synthetic_id] = replace(
            ctx.facts(3), card_id=synthetic_id,
            name=f"Probe Energy {int(clause.energy_type)}",
            provides=int(clause.energy_type))
    if any(clause.restriction == "arvens_pokemon" for clause in clauses) \
            and not any(isinstance(candidate, PokemonCard)
                        and "arven" in candidate.name.casefold()
                        for candidate in store.values()):
        synthetic_id = 9_999_997
        overrides[synthetic_id] = store[synthetic_id] = replace(
            ctx.facts(119), card_id=synthetic_id, name="Arven's Pokémon")
    wanted = next((str(clause.named) for clause in clauses
                   if clause.condition == "bench_has_named" and clause.named), None)
    if wanted is not None and not any(getattr(candidate, "name", None) == wanted
                                      for candidate in store.values()):
        synthetic_id = 9_999_998
        base = facts if isinstance(facts, PokemonCard) else ctx.facts(119)
        overrides[synthetic_id] = store[synthetic_id] = replace(
            base, card_id=synthetic_id, name=wanted, abilities=(), attacks=(),
            default_roles=(), synergy=())
    return _derived_probe_context(ctx, store, overrides) if overrides else ctx


def _clause_probe_board(board, facts, kind, ctx, *, parameter=None, locator=None):
    clauses = ((_located_clause(facts, locator),) if locator is not None else
               tuple(clause for clause in card_clauses(facts) if clause.kind == kind))
    if parameter in {"evolves_into_type", "target_type"}:
        wanted = next(int(getattr(clause, parameter)) for clause in clauses
                      if getattr(clause, parameter, None) is not None)
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard)
                      and candidate.energy_type == wanted)
        board = replace(board, me=replace(
            board.me, bench=(_body_for_facts(board.me.bench[0], target),
                             *board.me.bench[1:])))
    if parameter == "target" and any(
            clause.target == "opp_dragon_pokemon" for clause in clauses):
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard)
                      and candidate.energy_type == 9)
        target_body = _body_for_facts(board.them.active, target)
        board = replace(board, them=replace(
            board.them, active=replace(
                target_body, card=replace(target_body.card, owner=1))))
    if parameter in {"source_class", "target_class"}:
        wanted = next(str(getattr(clause, parameter)) for clause in clauses
                      if getattr(clause, parameter, None) is not None)
        predicates = {
            "basic": lambda candidate: candidate.evolves_from is None,
            "ex": lambda candidate: candidate.is_rule_box,
            "ex_or_v": lambda candidate: candidate.is_rule_box,
            "has_ability": lambda candidate: bool(candidate.abilities),
        }
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard)
                      and predicates[wanted](candidate))
        target_body = _body_for_facts(board.them.active, target)
        board = replace(board, them=replace(
            board.them, active=replace(
                target_body, card=replace(target_body.card, owner=1))))
    if parameter == "applies_to":
        wanted = next(str(clause.applies_to) for clause in clauses
                      if clause.applies_to)
        family = next((str(clause.name_family).casefold() for clause in clauses
                       if clause.name_family), "")
        predicates = {
            "basic": lambda candidate: candidate.evolves_from is None,
            "basic_non_dark": lambda candidate: candidate.evolves_from is None
            and candidate.energy_type != 7,
            "grass": lambda candidate: candidate.energy_type == 1,
            "has_ability": lambda candidate: bool(candidate.abilities),
            "metal": lambda candidate: candidate.energy_type == 8,
            "name_family": lambda candidate: bool(family)
            and family in candidate.name.casefold(),
            "no_rule_box": lambda candidate: not candidate.is_rule_box,
            "own_basic": lambda candidate: candidate.evolves_from is None,
            "own_evolution_r_pokemon": lambda candidate: candidate.stage in {
                "stage1", "stage2"},
            "own_evolved": lambda candidate: candidate.evolves_from is not None,
            "self_ko_abilities": lambda candidate: bool(candidate.abilities),
            "stage2": lambda candidate: candidate.stage == "stage2",
        }
        if wanted in predicates:
            target = next(candidate for candidate in ctx.store.values()
                          if isinstance(candidate, PokemonCard)
                          and predicates[wanted](candidate))
            target_body = _body_for_facts(board.me.bench[0], target)
            board = replace(board, me=replace(
                board.me, bench=(target_body, *board.me.bench[1:])))
        if wanted == "has_energy_attached":
            board = replace(board, me=replace(
                board.me, active=replace(
                    board.me.active, energies=(*board.me.active.energies, 3))))
    if parameter in {"name", "name_family", "named"}:
        wanted = next(str(getattr(clause, parameter)) for clause in clauses
                      if getattr(clause, parameter, None) is not None)
        family = parameter == "name_family"
        target = next(candidate for candidate in ctx.store.values()
                      if (wanted.casefold() in candidate.name.casefold()
                          if family else candidate.name.casefold() == wanted.casefold()))
        deck_counts = dict(board.deck_counts)
        deck_counts[target.card_id] = max(1, deck_counts.get(target.card_id, 0))
        board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
    if parameter == "energy":
        wanted = next(str(clause.energy) for clause in clauses if clause.energy)
        target = next(
            candidate for candidate in ctx.store.values()
            if isinstance(candidate, EnergyCard)
            and (candidate.kind == "basic_energy") == (wanted == "basic"))
        source = next((clause.source or clause.zone for clause in clauses
                       if clause.energy), None)
        if kind == "discard_opp_energy":
            active = board.them.active
            board = replace(board, them=replace(
                board.them, active=replace(
                    active,
                    energies=(*active.energies, target.provides),
                    energy_cards=(*active.energy_cards, Card(
                        target.card_id, 7840, 1 - board.seat)))))
        elif source == "deck":
            deck_counts = dict(board.deck_counts)
            deck_counts[target.card_id] = max(1, deck_counts.get(target.card_id, 0))
            board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
        elif source == "discard":
            board = replace(board, me=replace(
                board.me, discard=card_bag([*({
                    "id": card.card_id, "serial": card.serial,
                    "playerIndex": card.owner} for card in board.me.discard), {
                        "id": target.card_id, "serial": 7841,
                        "playerIndex": board.seat}])))
        elif source == "hand":
            cards = (*tuple(board.me.hand), Card(target.card_id, 7842, board.seat))
            board = replace(board, me=replace(
                board.me, hand=VisibleHand(card_bag([{
                    "id": card.card_id, "serial": card.serial,
                    "playerIndex": card.owner} for card in cards])),
                hand_count=len(cards)))
        else:
            board = replace(board, me=replace(
                board.me, active=replace(
                    board.me.active,
                    energies=(*board.me.active.energies, target.provides),
                    energy_cards=(*board.me.active.energy_cards, Card(
                        target.card_id, 7843, board.seat)))))
    if parameter in {"energy_type", "rider_energy_type"}:
        wanted = next(int(getattr(clause, parameter)) for clause in clauses
                      if getattr(clause, parameter, None) is not None)
        clause = next(clause for clause in clauses
                      if getattr(clause, parameter, None) is not None)
        source = clause.source or clause.zone
        pokemon_target = (kind == "fetch"
                          and clause.target not in {"basic_energy", "energy"})
        if source in {"deck", "discard", "hand"}:
            target = next(
                candidate for candidate in ctx.store.values()
                if ((isinstance(candidate, PokemonCard)
                     and candidate.energy_type == wanted) if pokemon_target else
                    (isinstance(candidate, EnergyCard)
                     and candidate.provides == wanted))
                and (kind != "fetch" or fetch_target_matches(
                    clause, candidate, reading=DEADNESS)))
            if source == "deck":
                deck_counts = dict(board.deck_counts)
                deck_counts[target.card_id] = max(
                    1, deck_counts.get(target.card_id, 0))
                board = replace(
                    board, deck_counts=tuple(sorted(deck_counts.items())))
            else:
                cards = tuple(board.me.discard if source == "discard" else board.me.hand)
                cards = (*cards, Card(target.card_id, 7844, board.seat))
                bag = card_bag([{
                    "id": card.card_id, "serial": card.serial,
                    "playerIndex": card.owner} for card in cards])
                board = (replace(board, me=replace(board.me, discard=bag))
                         if source == "discard" else replace(
                             board, me=replace(
                                 board.me, hand=VisibleHand(bag),
                                 hand_count=len(cards))))
        else:
            board = replace(board, me=replace(
                board.me, active=replace(
                    board.me.active, energies=(*board.me.active.energies, wanted))))
    if parameter == "distinct_types":
        deck_counts = dict(board.deck_counts)
        deck_counts[2] = max(1, deck_counts.get(2, 0))
        deck_counts[3] = max(1, deck_counts.get(3, 0))
        board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
    if parameter == "to_hand":
        clause = next(clause for clause in clauses if clause.to_hand is not None)
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, EnergyCard)
                      and (clause.energy != "basic"
                           or candidate.kind == "basic_energy")
                      and (clause.energy_type is None
                           or candidate.provides == clause.energy_type))
        needed = int(clause.amount or 1) + int(clause.to_hand or 0)
        source = clause.source or clause.zone
        if source == "deck":
            deck_counts = dict(board.deck_counts)
            deck_counts[target.card_id] = max(
                needed, deck_counts.get(target.card_id, 0))
            if clause.distinct_types and needed > 1:
                second = next(candidate for candidate in ctx.store.values()
                              if isinstance(candidate, EnergyCard)
                              and candidate.kind == "basic_energy"
                              and candidate.provides != target.provides)
                deck_counts[second.card_id] = max(
                    1, deck_counts.get(second.card_id, 0))
            board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
        elif source == "discard":
            cards = (*tuple(board.me.discard), *(Card(
                target.card_id, 7850 + index, board.seat)
                for index in range(needed)))
            board = replace(board, me=replace(board.me, discard=card_bag([{
                "id": card.card_id, "serial": card.serial,
                "playerIndex": card.owner} for card in cards])))
    if parameter == "exclude_name":
        wanted = next(str(clause.exclude_name) for clause in clauses
                      if clause.exclude_name)
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard)
                      and candidate.name == wanted)
        board = replace(board, me=replace(
            board.me, bench=(_body_for_facts(board.me.bench[0], target),
                             *board.me.bench[1:])))
    if parameter == "no_stack":
        board = replace(board, me=replace(
            board.me, bench=(_body_for_facts(board.me.bench[0], facts),
                             *board.me.bench[1:])))
    if parameter == "trigger":
        trigger = next(str(clause.trigger) for clause in clauses if clause.trigger)
        if trigger == "on_evolve":
            board = replace(board, me=replace(
                board.me, active=replace(
                    board.me.active,
                    pre_evolution=(Card(119, 7810, board.seat),))))
        elif trigger == "on_attach":
            board = replace(board, me=replace(
                board.me, active=replace(
                    board.me.active, energies=(*board.me.active.energies, 3))))
        elif trigger == "setup":
            board = replace(board, turn=replace(board.turn, number=1))
    if any(clause.rider == "discard_basic_f_energy" for clause in clauses):
        target = next(
            candidate for candidate in ctx.store.values()
            if isinstance(candidate, EnergyCard)
            and candidate.kind == "basic_energy"
            and candidate.provides == 6)
        cards = (*tuple(board.me.hand), Card(target.card_id, 7860, board.seat))
        board = replace(board, me=replace(
            board.me, hand=VisibleHand(card_bag([{
                "id": card.card_id, "serial": card.serial,
                "playerIndex": card.owner} for card in cards])),
            hand_count=len(cards)))
    if any(
            clause.rider in {"bounce_energy_to_hand", "discard_own_energy"}
            for clause in clauses):
        board = replace(board, me=replace(
            board.me, active=replace(
                board.me.active, energies=(*board.me.active.energies, 6))))
    if parameter == "rider" and any(
            clause.rider == "confuse_target" for clause in clauses):
        board = replace(board, them=replace(board.them, confused=False))
    if any(
            clause.restriction == "evolves_from_self" for clause in clauses):
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard)
                      and candidate.evolves_from == facts.name)
        deck_counts = dict(board.deck_counts)
        deck_counts[target.card_id] = max(1, deck_counts.get(target.card_id, 0))
        board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
    if any(clause.restriction for clause in clauses):
        restriction = next(str(clause.restriction)
                           for clause in clauses if clause.restriction)
        predicates = {
            "active_dragon_only": lambda candidate: candidate.energy_type == 9,
            "active_non_arvens_pokemon": lambda candidate: (
                "arven" not in candidate.name.casefold()),
            "arvens_pokemon": lambda candidate: "arven" in candidate.name.casefold(),
            "ex_or_v_only": lambda candidate: candidate.is_rule_box,
            "mega_only": lambda candidate: "mega" in candidate.name.casefold(),
            "psychic_only": lambda candidate: candidate.energy_type == 5,
        }
        if restriction in predicates:
            target = next(candidate for candidate in ctx.store.values()
                          if isinstance(candidate, PokemonCard)
                          and predicates[restriction](candidate))
            target_body = _body_for_facts(board.me.active, target)
            if restriction == "ex_or_v_only":
                board = replace(board, them=replace(
                    board.them, bench=(replace(target_body, card=replace(
                        target_body.card, owner=1)), *board.them.bench[1:])))
            else:
                board = replace(board, me=replace(board.me, active=target_body))
    conditions = {str(clause.condition) for clause in clauses if clause.condition}
    turn = board.turn
    if conditions.intersection({"first_turn", "going_second_first_turn", "went_first"}):
        turn = replace(turn, number=1)
    if "going_second_first_turn" in conditions:
        turn = replace(turn, first_player=1 - board.seat)
    if "went_first" in conditions:
        turn = replace(turn, first_player=board.seat)
    if "not_first_turn" in conditions:
        turn = replace(turn, number=3)
    if "played_supporter_this_turn" in conditions:
        turn = replace(turn, supporter_played=True)
    if "moved_to_active_this_turn" in conditions:
        turn = replace(turn, retreated=True)
    board = replace(board, turn=turn)
    deck_fetches = tuple(
        clause for clause in clauses
        if clause.kind == "fetch" and clause.zone == "deck")
    if deck_fetches:
        names = {candidate.name for candidate in ctx.store.values()
                 if isinstance(candidate, PokemonCard)}
        deck_counts = dict(board.deck_counts)
        targets = tuple(
            target for fetch_clause in deck_fetches
            if (target := next((
                candidate for candidate in ctx.store.values()
                if fetch_target_matches(fetch_clause, candidate, reading=DEADNESS)
                and (not isinstance(candidate, PokemonCard)
                     or not candidate.evolves_from
                     or candidate.evolves_from in names)), None)) is not None)
        for target in targets:
            deck_counts[target.card_id] = max(1, deck_counts.get(target.card_id, 0))
        board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
        evolved = next((target for target in targets
                        if isinstance(target, PokemonCard) and target.evolves_from), None)
        if evolved is not None:
            base = next(
                candidate for candidate in ctx.store.values()
                if isinstance(candidate, PokemonCard)
                and candidate.name == evolved.evolves_from)
            board = replace(board, me=replace(
                board.me, bench=(_body_for_facts(board.me.bench[0], base),
                                 *board.me.bench[1:])))
    for zone in ("discard", "hand"):
        zone_fetches = tuple(clause for clause in clauses
                             if clause.kind == "fetch" and clause.zone == zone)
        targets = tuple(
            target for fetch_clause in zone_fetches
            if (target := next((candidate for candidate in ctx.store.values()
                               if fetch_target_matches(
                                   fetch_clause, candidate, reading=DEADNESS)), None))
            is not None)
        if not targets:
            continue
        cards = tuple(board.me.discard if zone == "discard" else board.me.hand)
        cards = (*cards, *(Card(target.card_id, 7820 + index, board.seat)
                           for index, target in enumerate(targets)))
        bag = card_bag([{
            "id": card.card_id, "serial": card.serial, "playerIndex": card.owner}
            for card in cards])
        if zone == "discard":
            board = replace(board, me=replace(board.me, discard=bag))
        else:
            board = replace(board, me=replace(
                board.me, hand=VisibleHand(bag), hand_count=len(cards)))
    branch_conditions = {
        str(branch.get("condition"))
        for clause in clauses
        for branch in (clause.amount_if, clause.opponent_amount_if)
        if isinstance(branch, dict)
    }
    branch_enabled = parameter in {"amount_if", "opponent_amount_if"}
    if "exactly_6_prizes_remaining" in branch_conditions and branch_enabled:
        board = replace(board, me=replace(board.me, prize_count=6))
    elif "exactly_6_prizes_remaining" in branch_conditions:
        board = replace(board, me=replace(board.me, prize_count=5))
    if "opp_3_or_fewer_prizes" in branch_conditions and branch_enabled:
        board = replace(board, them=replace(board.them, prize_count=3))
    elif "opp_3_or_fewer_prizes" in branch_conditions:
        board = replace(board, them=replace(board.them, prize_count=4))
    if "hand_size_10_plus_after_draw" in branch_conditions and branch_enabled:
        board = replace(board, me=replace(board.me, hand_count=10))
    elif "hand_size_10_plus_after_draw" in branch_conditions:
        board = replace(board, me=replace(board.me, hand_count=0))
    if "all_own_pokemon_team_rocket" in branch_conditions and branch_enabled:
        rocket = next(
            candidate for candidate in ctx.store.values()
            if isinstance(candidate, PokemonCard)
            and candidate.name.casefold().startswith("team rocket"))
        board = replace(board, me=replace(
            board.me,
            active=_body_for_facts(board.me.active, rocket),
            bench=tuple(_body_for_facts(body, rocket) for body in board.me.bench)))
    if any((clause.per or clause.amount_per) == "my_ancient" for clause in clauses):
        ancient = next(
            ctx.facts(card_id) for card_id in (56, 62, 63, 171, 226, 986)
            if card_id != facts.card_id)
        board = replace(board, me=replace(
            board.me, bench=(
                _body_for_facts(board.me.bench[0], ancient),
                _body_for_facts(board.me.bench[1], ancient),
                *board.me.bench[2:])))
    if any((clause.per or clause.amount_per) in {"their_bench", "opp_bench"}
           for clause in clauses):
        board = replace(board, them=replace(
            board.them, bench=(*board.them.bench, replace(
                board.them.bench[0], card=replace(
                    board.them.bench[0].card, serial=7850)))))
    if any((clause.per or clause.amount_per) == "attached_fighting_energy"
           for clause in clauses):
        board = replace(board, me=replace(
            board.me, active=replace(
                board.me.active, energies=(*board.me.active.energies, 6, 6))))
    if any((clause.per or clause.amount_per) in {
            "energy_on_opp_active", "energy_on_both_actives"}
           for clause in clauses):
        board = replace(board, them=replace(
            board.them, active=replace(
                board.them.active,
                energies=(*board.them.active.energies, 3, 3))))
    if any((clause.per or clause.amount_per) in {
            "basic_energy_own_discard", "basic_energy_in_opp_discard"}
           for clause in clauses):
        energy = next(
            candidate for candidate in ctx.store.values()
            if isinstance(candidate, EnergyCard)
            and candidate.kind == "basic_energy")
        cards = card_bag([
            {"id": energy.card_id, "serial": 7851, "playerIndex": board.seat},
            {"id": energy.card_id, "serial": 7852, "playerIndex": board.seat},
        ])
        if any((clause.per or clause.amount_per) == "basic_energy_own_discard"
               for clause in clauses):
            board = replace(board, me=replace(board.me, discard=cards))
        if any((clause.per or clause.amount_per) == "basic_energy_in_opp_discard"
               for clause in clauses):
            board = replace(board, them=replace(board.them, discard=cards))
    if any(clause.per == "basic_energy_discarded_this_way" for clause in clauses):
        deck_counts = dict(board.deck_counts)
        deck_counts[3] = max(6, deck_counts.get(3, 0))
        board = replace(board, deck_counts=tuple(sorted(deck_counts.items())))
    if "festival_grounds_in_play" in conditions:
        stadium = next(candidate for candidate in ctx.store.values()
                       if getattr(candidate, "name", "") == "Festival Grounds")
        board = replace(board, stadium=(Card(stadium.card_id, 7600, board.seat),))
    if "bench_has_named" in conditions:
        wanted = next(str(clause.named) for clause in clauses if clause.named)
        target = next(candidate for candidate in ctx.store.values()
                      if getattr(candidate, "name", None) == wanted)
        board = replace(board, me=replace(
            board.me, bench=(_body_for_facts(board.me.bench[0], target),
                             *board.me.bench[1:])))
    if "solrock_in_play" in conditions:
        target = next(candidate for candidate in ctx.store.values()
                      if getattr(candidate, "name", None) == "Solrock")
        board = replace(board, me=replace(
            board.me, bench=(_body_for_facts(board.me.bench[0], target),
                             *board.me.bench[1:])))
    if "opp_active_ex" in conditions:
        target = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard) and candidate.is_rule_box)
        board = replace(board, them=replace(
            board.them, active=_body_for_facts(board.them.active, target)))
    if "name_in_opp_discard" in conditions:
        family = next(str(clause.name_family) for clause in clauses if clause.name_family)
        target = next(candidate for candidate in ctx.store.values()
                      if family.casefold() in getattr(candidate, "name", "").casefold())
        board = replace(board, them=replace(
            board.them, discard=card_bag([{
                "id": target.card_id, "serial": 7700, "playerIndex": 1 - board.seat}])))
    if any(clause.per == "ethans_adventure_in_own_discard" for clause in clauses):
        target = next(candidate for candidate in ctx.store.values()
                      if "ethan's adventure" in getattr(
                          candidate, "name", "").casefold())
        board = replace(board, me=replace(
            board.me, discard=card_bag([
                {"id": target.card_id, "serial": 7701,
                 "playerIndex": board.seat},
                {"id": target.card_id, "serial": 7705,
                 "playerIndex": board.seat}])))
    if "pokemon_ko_last_turn" in conditions:
        board = replace(board, events=(MoveCardEvent(
            6, (("fromArea", 4), ("toArea", 3)), True),))
    if "other_ancient_attacked_last_turn" in conditions:
        board = replace(board, events=(AttackEvent(
            15, (("cardId", 62), ("playerIndex", board.seat)), True),))
    if "damage_200_plus" in conditions:
        target = max(
            (candidate for candidate in ctx.store.values()
             if isinstance(candidate, PokemonCard) and candidate.attacks),
            key=lambda candidate: max(
                (attack.damage or attack.damage_fix or attack.damage_max or 0)
                for attack in candidate.attacks))
        board = replace(board, them=replace(
            board.them, active=_body_for_facts(board.them.active, target)))
    if "remaining_hp_30_or_less" in conditions:
        board = replace(board, me=replace(
            board.me, active=replace(board.me.active, hp=20)))
    if "energy_3_plus" in conditions:
        board = replace(board, me=replace(
            board.me, active=replace(board.me.active, energies=(0, 0, 0))))
    if kind == "copy_attack" and any(
            clause.source == "milled_pokemon" for clause in clauses):
        source = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard) and candidate.attacks
                      and not candidate.is_rule_box)
        board = replace(board, me=replace(
            board.me, discard=card_bag([{
                "id": source.card_id, "serial": 7702, "playerIndex": board.seat}])))
    return board


def _clause_probe_body(body, facts, kind):
    clauses = tuple(clause for clause in card_clauses(facts) if clause.kind == kind)
    conditions = {str(clause.condition) for clause in clauses if clause.condition}
    if "full_hp" in conditions:
        body = replace(body, hp=body.max_hp)
    if "moved_to_active_this_turn" in conditions:
        body = replace(body, appeared_this_turn=True)
    if "energy_3_plus" in conditions:
        body = replace(body, energies=(*body.energies, *((0,) * max(
            0, 3 - len(body.energies)))))
    if "dark_energy_attached" in conditions:
        body = replace(body, energies=(*body.energies, 7),
                       energy_cards=(Card(7, 7703, body.card.owner),))
    if "team_rocket_energy_attached" in conditions:
        body = replace(body, energies=(*body.energies, 0),
                       energy_cards=(Card(15, 7704, body.card.owner),))
    return body


def _direct_clause_contribution(contract, facts, ctx, *, transform=None):
    valued, stripped_value = _direct_clause_valuations(
        contract, facts, ctx, transform=transform)
    valued_features = {item.feature: item.value for item in valued.activations}
    stripped_features = {item.feature: item.value for item in stripped_value.activations}
    return sum(
        (valued_features.get(feature, 0.0) - stripped_features.get(feature, 0.0))
        * ctx.configuration[feature]
        for feature in contract.features)


def _direct_parameter_contributions(contract, facts, ctx, *, transform, parameter,
                                    locator, feature):
    valued, perturbed = _direct_clause_valuations(
        contract, facts, ctx, transform=transform,
        parameter=parameter, locator=locator)
    if feature is None:
        return valued.total - perturbed.total, None
    valued_features = {item.feature: item.value for item in valued.activations}
    perturbed_features = {item.feature: item.value for item in perturbed.activations}
    feature_delta = (
        valued_features.get(feature, 0.0) - perturbed_features.get(feature, 0.0)
    ) * ctx.configuration[feature]
    return valued.total - perturbed.total, feature_delta


def card_clause_contribution(card_id: int, kind: str, ctx: EvaluationModel) -> float:
    facts = ctx.facts(card_id)
    contract = CLAUSE_VALUATION_CONTRACTS[str(kind)]
    if facts is None or not any(
            clause.kind == kind for clause in card_clauses(facts)):
        raise KeyError(f"card {card_id} has no {kind!r} clause")
    return _direct_clause_contribution(contract, facts, ctx)


DIRECT_EQUATION_EXECUTORS = MappingProxyType({
    DirectEquationOwner.ACCELERATION: _direct_clause_contribution,
    DirectEquationOwner.ATTACK: _direct_clause_contribution,
    DirectEquationOwner.ATTACK_GATE: _direct_clause_contribution,
    DirectEquationOwner.BENCH_REACH: _direct_clause_contribution,
    DirectEquationOwner.DAMAGE_MOVE: _direct_clause_contribution,
    DirectEquationOwner.DENIAL: _direct_clause_contribution,
    DirectEquationOwner.DRAW: _direct_clause_contribution,
    DirectEquationOwner.HEALING: _direct_clause_contribution,
    DirectEquationOwner.KNOCKOUT: _direct_clause_contribution,
    DirectEquationOwner.PROTECTION: _direct_clause_contribution,
    DirectEquationOwner.SEARCH: _direct_clause_contribution,
    DirectEquationOwner.FUNCTION: _direct_clause_contribution,
})


def _without_clause(facts, kind):
    changes = {}
    if hasattr(facts, "clauses"):
        changes["clauses"] = tuple(
            clause for clause in facts.clauses if clause.kind != kind)
    if hasattr(facts, "abilities"):
        changes["abilities"] = tuple(replace(
            ability, clauses=tuple(
                clause for clause in ability.clauses if clause.kind != kind))
            for ability in facts.abilities)
    if hasattr(facts, "attacks"):
        changes["attacks"] = tuple(replace(
            attack, clauses=tuple(
                clause for clause in attack.clauses if clause.kind != kind))
            for attack in facts.attacks)
    return replace(facts, **changes)


def _perturbed_clause(clause, parameter, kind):
    params = dict(clause.params)
    current = params.get(parameter)
    if parameter in {
            "amount", "amount_on_evolution", "opponent_amount",
            "remaining_hp", "to_hand", "to_hand_size", "count"}:
        params[parameter] = 0
    elif parameter in {"amount_per", "per"}:
        if parameter == "per" and current == "heads":
            params[parameter] = "all_bench"
        else:
            params.pop(parameter, None)
    elif parameter == "cost":
        params.pop(parameter, None)
    elif parameter == "condition":
        params[parameter] = ("remaining_hp_30_or_less"
                             if clause.condition == "full_hp" else "full_hp")
    elif parameter == "target":
        params.pop(parameter, None)
    else:
        params.pop(parameter, None)
    return Clause(clause.kind, **params)


def _perturb_parameter_at(facts, locator, parameter, kind):
    collection, owner_index, *tail = locator
    if collection == "clauses":
        clauses = list(facts.clauses)
        clauses[owner_index] = _perturbed_clause(
            clauses[owner_index], parameter, kind)
        return replace(facts, clauses=tuple(clauses))
    owners = list(getattr(facts, collection))
    clauses = list(owners[owner_index].clauses)
    clause_index = tail[0]
    clauses[clause_index] = _perturbed_clause(
        clauses[clause_index], parameter, kind)
    owners[owner_index] = replace(owners[owner_index], clauses=tuple(clauses))
    return replace(facts, **{collection: tuple(owners)})


def _body_for_facts(template, facts, *, serial=None):
    attacks = tuple(getattr(facts, "attacks", ()) or ())
    costs = (() if not attacks else max(attacks, key=lambda attack: len(attack.cost)).cost)
    maximum = int(getattr(facts, "hp", 100) or 100)
    return replace(
        template, card=replace(
            template.card, card_id=facts.card_id,
            serial=template.card.serial if serial is None else serial),
        hp=max(10, maximum - 30), max_hp=maximum,
        energies=costs or template.energies, energy_cards=(), tools=(), pre_evolution=())


def _perturb_observation(identity, board, ctx):
    def side(name, **changes):
        return replace(board, **{name: replace(getattr(board, name), **changes)})

    me, them = board.me, board.them
    active = me.active
    def evidence(archetype="fast", probability="0.5", unknown="0.1"):
        return OpponentDecisionEvidence(
            "probe", (OpponentCandidatePosterior(archetype, probability),),
            (), (), (), unknown)

    def opponent_board(value):
        knowledge = replace(
            board.knowledge,
            opponent=OpponentBelief(decision_evidence=value))
        return replace(board, knowledge=knowledge)

    if identity == "KnownOwnPrizes.cards":
        knowledge = replace(
            board.knowledge, own_prizes=KnownOwnPrizes(((1121, 1),)))
        return board, replace(board, knowledge=knowledge)
    if identity == "KnownDeckTop.cards":
        knowledge = replace(
            board.knowledge, known_top=KnownDeckTop(((9001, 1121),)))
        return board, replace(board, knowledge=knowledge)
    if identity == "OpponentCandidatePosterior.archetype":
        return opponent_board(evidence()), opponent_board(evidence(archetype="slow"))
    if identity == "OpponentCandidatePosterior.probability":
        return (opponent_board(evidence(probability="0.2")),
                opponent_board(evidence(probability="0.8")))
    if identity == "OpponentDecisionEvidence.unknown_mass":
        return (opponent_board(evidence(unknown="0.1")),
                opponent_board(evidence(unknown="0.8")))
    if identity.startswith("ObservationEvent."):
        fez = _body_for_facts(active, ctx.facts(140))
        prepared = replace(board, me=replace(me, bench=(*me.bench[:-1], fez)))
        knockout = MoveCardEvent(
            6, (("fromArea", 4), ("toArea", 3)), True)
        if identity == "ObservationEvent.kind":
            before = replace(knockout, kind=999)
        elif identity == "ObservationEvent.public_fields":
            before = replace(knockout, public_fields=(("fromArea", 2), ("toArea", 3)))
        else:
            before = replace(knockout, recognized=False)
        return (replace(prepared, events=(before,)),
                replace(prepared, events=(knockout,)))
    body_changes = {
        "Body.hp": {"hp": max(1, active.hp - 30)},
        "Body.max_hp": {"max_hp": active.max_hp + 100},
        "Body.appeared_this_turn": {"appeared_this_turn": True},
        "Body.energies": {"energies": (*active.energies, 3)},
        "Body.energy_cards": {
            "energy_cards": (*active.energy_cards, Card(3, 7001, board.seat))},
        "Body.tools": {"tools": (*active.tools, Card(1174, 7002, board.seat))},
        "Body.pre_evolution": {
            "pre_evolution": (*active.pre_evolution, Card(1030, 7003, board.seat))},
        "Card.card_id": {"card": replace(active.card, card_id=119)},
    }
    if identity in body_changes:
        if identity == "Body.appeared_this_turn":
            cards = (Card(1031, 7004, board.seat),)
            prepared = replace(
                board,
                me=replace(me, active=replace(
                    active, card=replace(active.card, card_id=1030), energies=(3,)),
                    hand=VisibleHand(card_bag([
                        {"id": card.card_id, "serial": card.serial,
                         "playerIndex": card.owner} for card in cards])),
                    hand_count=1))
            return prepared, replace(
                prepared, me=replace(prepared.me, active=replace(
                    prepared.me.active, appeared_this_turn=True)))
        if identity == "Body.energy_cards":
            prepared = side("me", active=replace(active, energies=(3,)))
            return prepared, replace(
                prepared, me=replace(prepared.me, active=replace(
                    prepared.me.active,
                    energy_cards=(Card(3, 7001, board.seat),))))
        return board, side("me", active=replace(active, **body_changes[identity]))
    if identity == "ObservationState.stadium" or identity == "Card.owner":
        stadium = next(facts for facts in ctx.store.values()
                       if getattr(facts, "kind", None) == "stadium"
                       and card_option_value(facts, me, them, board, ctx) > 0.0)
        owned = replace(board, stadium=(Card(stadium.card_id, 7100, board.seat),))
        if identity == "ObservationState.stadium":
            return board, owned
        return owned, replace(
            owned, stadium=(replace(owned.stadium[0], owner=1 - board.seat),))
    if identity == "ObservationState.deck_counts":
        return board, replace(board, deck_counts=(*board.deck_counts, (1227, 2)))
    if identity == "Side.active":
        return board, side("me", active=None)
    if identity == "Side.active_hidden":
        return board, side("me", active_hidden=True)
    if identity == "Side.bench":
        return board, side("me", bench=())
    if identity == "Side.bench_max":
        return board, side("me", bench_max=me.bench_max + 1)
    if identity == "Side.deck_count":
        return board, side("them", deck_count=them.deck_count - 1)
    if identity == "Side.hand":
        cards = (*tuple(me.hand), Card(119, 7200, board.seat))
        return board, side("me", hand=VisibleHand(card_bag([
            {"id": card.card_id, "serial": card.serial, "playerIndex": card.owner}
            for card in cards])), hand_count=len(cards))
    if identity == "Side.hand_count":
        return board, side("them", hand_count=them.hand_count + 1)
    if identity == "Side.discard":
        cards = (*tuple(me.discard), Card(3, 7201, board.seat))
        return board, side("me", discard=card_bag([
            {"id": card.card_id, "serial": card.serial, "playerIndex": card.owner}
            for card in cards]))
    if identity == "Side.prize_count":
        return board, side("them", prize_count=5)
    status = identity.removeprefix("Side.")
    if status in {"poisoned", "burned", "asleep", "paralyzed", "confused"}:
        return board, side("me", **{status: False})
    if identity == "Turn.number":
        cards = (Card(1079, 7300, board.seat), Card(121, 7301, board.seat))
        prepared = replace(
            board,
            me=replace(
                me, active=replace(
                    active, card=replace(active.card, card_id=119), energies=(2, 5)),
                hand=VisibleHand(card_bag([
                    {"id": card.card_id, "serial": card.serial,
                     "playerIndex": card.owner} for card in cards])),
                hand_count=2),
            turn=replace(board.turn, number=3))
        return prepared, replace(prepared, turn=replace(prepared.turn, number=1))
    if identity == "Turn.first_player":
        active = _body_for_facts(me.active, ctx.facts(88))
        active = replace(active, energies=(0,))
        prepared = replace(
            board, me=replace(me, active=active),
            turn=replace(board.turn, number=1, first_player=1 - board.seat))
        return prepared, replace(
            prepared, turn=replace(prepared.turn, first_player=board.seat))
    if identity == "Turn.supporter_played":
        cards = (Card(1227, 7302, board.seat),)
        prepared = replace(board, me=replace(
            me, hand=VisibleHand(card_bag([{
                "id": card.card_id, "serial": card.serial, "playerIndex": card.owner}
                for card in cards])), hand_count=1),
            turn=replace(board.turn, supporter_played=False))
        return prepared, replace(
            prepared, turn=replace(prepared.turn, supporter_played=True))
    if identity == "Turn.retreated":
        active = _body_for_facts(me.active, ctx.facts(849))
        active = replace(active, energies=(0,))
        prepared = replace(
            board, me=replace(me, active=active),
            turn=replace(board.turn, retreated=False))
        return prepared, replace(
            prepared, turn=replace(prepared.turn, retreated=True))
    if identity == "Turn.result":
        return board, replace(board, turn=replace(board.turn, result=board.seat))
    return _perturb_zero_observation(identity, board)


def _perturb_zero_observation(identity, board):
    me, them = board.me, board.them

    def with_me(**changes):
        return replace(board, me=replace(me, **changes))

    def with_active(**changes):
        return with_me(active=replace(me.active, **changes))

    if identity == "ObservationState.seat":
        return board, replace(board, seat=1 - board.seat)
    if identity == "ObservationState.me":
        card = replace(me.active.card, serial=me.active.card.serial + 10000)
        return board, with_me(active=replace(me.active, card=card))
    if identity == "ObservationState.them":
        card = replace(them.active.card, serial=them.active.card.serial + 10000)
        return board, replace(board, them=replace(
            them, active=replace(them.active, card=card)))
    if identity == "ObservationState.turn":
        return board, replace(board, turn=replace(
            board.turn, first_player=1 - int(board.turn.first_player or 0)))
    if identity == "ObservationState.looking":
        return board, replace(board, looking=Looking(1, None))
    if identity == "ObservationState.select":
        return board, replace(board, select=_probe_prompt())
    if identity == "ObservationState.decklist":
        return board, replace(board, decklist=(1121,))
    if identity == "ObservationState.knowledge":
        return board, replace(board, knowledge=replace(
            board.knowledge, attack_locks=KnownAttackLocks(((1, 2),))))
    if identity == "ObservationState.legal_actions":
        action = SimpleNamespace(identity=SimpleNamespace(kind="probe", parts=()))
        prepared = replace(
            board, stadium=(Card(1248, 7655, board.seat),), legal_actions=())
        return prepared, replace(prepared, legal_actions=(action,))
    if identity == "ObservationState.events":
        return board, replace(board, events=(MoveCardEvent(None, (), False),))
    if identity == "ObservationState._pieces":
        return board, replace(board, _pieces=(("probe",),))
    if identity == "Body.card":
        return board, with_active(card=replace(
            me.active.card, serial=me.active.card.serial + 10000))
    if identity == "Body.digest":
        return board, with_active(digest=b"sensitivity")
    if identity == "Card.serial":
        return board, with_active(card=replace(
            me.active.card, serial=me.active.card.serial + 10000))
    if identity.startswith("Turn."):
        field = identity.removeprefix("Turn.")
        value = getattr(board.turn, field)
        changed = (not value if isinstance(value, bool) else
                   1 - int(value or 0))
        return board, replace(board, turn=replace(board.turn, **{field: changed}))
    if identity.startswith("Looking."):
        looking = Looking(1, (Card(119, 8100, board.seat),))
        changed = (replace(looking, count=2) if identity.endswith(".count")
                   else replace(looking, cards=None))
        return replace(board, looking=looking), replace(board, looking=changed)
    if identity.startswith("SelectPrompt."):
        field = identity.removeprefix("SelectPrompt.")
        prompt = _probe_prompt()
        changes = {
            "type": 1, "context": 1, "min_count": 1, "max_count": 2,
            "remain_damage_counter": 1, "remain_energy_cost": 1,
            "options": (Option(type=1), Option(type=2)),
            "deck": (Card(119, 8101, board.seat),),
            "context_card": Card(119, 8102, board.seat),
            "effect": Card(1121, 8103, board.seat),
        }
        return (replace(board, select=prompt),
                replace(board, select=replace(prompt, **{field: changes[field]})))
    if identity.startswith("CardBag."):
        bag = me.hand.bag
        field = identity.removeprefix("CardBag.")
        changes = {
            "cards": tuple(replace(card, serial=(card.serial or 0) + 10000)
                           for card in bag.cards),
            "counts": tuple(reversed(bag.counts)),
            "digest": b"sensitivity",
        }
        return board, with_me(hand=VisibleHand(replace(bag, **{field: changes[field]})))
    if identity == "VisibleHand.bag":
        return board, with_me(hand=VisibleHand(replace(
            me.hand.bag, digest=b"sensitivity")))
    if identity == "HiddenHand.count":
        return board, replace(board, them=replace(
            them, hand=HiddenHand(them.hand.count + 1)))
    if identity.startswith("Option."):
        field = identity.removeprefix("Option.")
        prompt = _probe_prompt()
        changed = replace(prompt.options[0], **{field: 1})
        return (replace(board, select=prompt), replace(
            board, select=replace(prompt, options=(changed,))))
    if identity == "KnownAttackLocks.locks":
        before = replace(board.knowledge, attack_locks=KnownAttackLocks(()))
        after = replace(board.knowledge, attack_locks=KnownAttackLocks(((1, 2),)))
        return replace(board, knowledge=before), replace(board, knowledge=after)

    evidence = OpponentDecisionEvidence(
        "probe", (OpponentCandidatePosterior("fast", "0.5"),
                  OpponentCandidatePosterior("slow", "0.5")),
        (1,), (2,), (3,), "0.0")
    if identity.startswith("OpponentDecisionEvidence."):
        field = identity.removeprefix("OpponentDecisionEvidence.")
        changes = {
            "snapshot_identity": "changed",
            "candidates": tuple(reversed(evidence.candidates)),
            "revealed_card_ids": (1, 4),
            "in_play_card_ids": (2, 4),
            "public_resources": (3, 4),
            "failures": (("probe", "failure"),),
            "public_events": ((None, (), False),),
        }
        before = replace(board.knowledge, opponent=OpponentBelief(
            decision_evidence=evidence))
        after = replace(board.knowledge, opponent=OpponentBelief(
            decision_evidence=replace(evidence, **{field: changes[field]})))
        return replace(board, knowledge=before), replace(board, knowledge=after)
    if identity.startswith("OpponentBelief."):
        field = identity.removeprefix("OpponentBelief.")
        belief = OpponentBelief(decision_evidence=evidence)
        changes = {
            "evidence": (("probe", 1),),
            "probabilities": ((119, 1),),
            "decision_evidence": replace(evidence, snapshot_identity="changed"),
        }
        return (replace(board, knowledge=replace(board.knowledge, opponent=belief)),
                replace(board, knowledge=replace(
                    board.knowledge, opponent=replace(belief, **{field: changes[field]}))))
    if identity.startswith("LegalKnowledge."):
        field = identity.removeprefix("LegalKnowledge.")
        changes = {
            "own_prizes": KnownOwnPrizes(()),
            "known_top": KnownDeckTop(()),
            "attack_locks": KnownAttackLocks(((1, 2),)),
            "opponent": OpponentBelief(evidence=(("probe", 1),)),
        }
        return board, replace(
            board, knowledge=replace(board.knowledge, **{field: changes[field]}))
    raise KeyError(f"no observation sensitivity perturbation for {identity}")


def _probe_prompt():
    return SelectPrompt(None, None, None, None, None, None, (Option(),), None, None, None)


def _environment(witness, ctx):
    board = _rich_board()
    if witness.rule.operation == "opponent_empty_bench":
        board = replace(board, them=replace(board.them, bench=()))
    parameter_clause = None
    if witness.source == "clause_parameter":
        facts, parameter_clause = next(
            (facts, clause)
            for facts in ctx.store.values()
            for clause in card_clauses(facts)
            if witness.claim in clause.params)
        ctx = _clause_probe_context(ctx, facts, parameter_clause.kind)
        facts = ctx.facts(facts.card_id)
        board = _clause_probe_board(
            board, facts, parameter_clause.kind, ctx, parameter=witness.claim)
    else:
        facts = _facts_for_claim(ctx, witness.claim)
    if witness.rule.operation == "fetch_live_target":
        facts = ctx.facts(1121)
    elif witness.rule.operation == "multi_provision_capacity":
        facts = ctx.facts(17)
    elif witness.rule.operation == "piercing_target":
        clause = next(clause for clause in card_clauses(facts)
                      if clause.kind == witness.claim)
        if witness.claim == "ignores_effects":
            target = next(candidate for candidate in ctx.store.values()
                          if isinstance(candidate, PokemonCard) and any(
                              effect.kind in {"damage_reduction", "prevent_damage"}
                              for effect in card_clauses(candidate)))
        else:
            target = next(candidate for candidate in ctx.store.values()
                          if isinstance(candidate, PokemonCard)
                          and (candidate.weakness == facts.energy_type
                               or candidate.resistance == facts.energy_type))
        board = replace(board, them=replace(
            board.them, active=_body_for_facts(board.them.active, target)))
    elif witness.rule.operation == "copy_attack_source":
        clause = next(clause for clause in card_clauses(facts)
                      if clause.kind == "copy_attack")
        family = str(clause.name_family or "").casefold()
        source = next(candidate for candidate in ctx.store.values()
                      if isinstance(candidate, PokemonCard) and candidate.attacks
                      and (not family or family in candidate.name.casefold())
                      and not (clause.no_rule_box and candidate.is_rule_box))
        if clause.source == "milled_pokemon":
            board = replace(board, me=replace(
                board.me, discard=card_bag([{
                    "id": source.card_id, "serial": 7650,
                    "playerIndex": board.seat}])))
        else:
            board = replace(board, me=replace(
                board.me, bench=(_body_for_facts(
                    board.me.bench[0], source), *board.me.bench[1:])))
    side, opponent = board.me, board.them
    clause = parameter_clause or next((
        clause for clause in card_clauses(facts)
        if clause.kind == witness.claim), None)
    claim_value = (clause.params[witness.claim]
                   if parameter_clause is not None else witness.rule.argument)
    return ActivationEnvironment(
        scale=1.0,
        board=board,
        evaluation_model=ctx,
        side=side,
        opponent=opponent,
        demand=Demand.read(side, ctx, board.turn),
        facts=facts,
        deck_counts=board.deck_counts,
        candidate=SimpleNamespace(roles={}),
        claim_value=claim_value,
        clause=clause,
    )


def _facts_for_claim(ctx, claim):
    return _card_with_clause(ctx, claim) or ctx.facts(1121)


def _card_with_clause(ctx, claim):
    for facts in ctx.store.values():
        if any(clause.kind == claim for clause in card_clauses(facts)):
            return facts
    return None


@lru_cache(maxsize=1)
def _rich_board():
    store = card_store()
    effect_body = next(
        card.card_id for card in store.values()
        if isinstance(card, PokemonCard) and {
            "attack_debuff", "attack_lock", "burn", "confuse", "damage_counters",
            "discard_opp_energy", "no_retreat", "poison", "push_out",
            "retreat_lock", "sleep",
        }.intersection(clause.kind for clause in card_clauses(card)))
    me = _player(
        active=_body(1031, 1, tools=(1174,)),
        bench=(_body(121, 2), _body(120, 3), _body(effect_body, 4)),
        hand=(1121, 17), prizes=4, status=True)
    them = _player(
        active=_body(120, 11, owner=1, energies=(7,), energy_cards=(9,),
                     tools=(1174,)),
        bench=(_body(119, 12, owner=1),), hand_count=5, prizes=2,
        own=False, status=True)
    raw = {
        "select": None,
        "logs": [],
        "current": {
            "turn": 3, "yourIndex": 0, "firstPlayer": 0,
            "supporterPlayed": False, "stadiumPlayed": False,
            "energyAttached": False, "retreated": False, "result": None,
            "stadium": [], "looking": None, "players": [me, them],
        },
    }
    board = ObservationStateBuilder().root(raw)
    return replace(board, deck_counts=((17, 2), (119, 2), (120, 1), (121, 1),
                                       (1030, 1), (1121, 1)))


def _body(card_id, serial, *, owner=0, energies=(), energy_cards=(), tools=()):
    facts = card_store()[card_id]
    maximum = int(getattr(facts, "hp", 100) or 100)
    return {
        "id": card_id, "serial": serial, "playerIndex": owner,
        "hp": max(10, maximum - 20), "maxHp": maximum, "appearThisTurn": False,
        "energies": list(energies),
        "energyCards": [
            {"id": value, "serial": serial * 100 + index, "playerIndex": owner}
            for index, value in enumerate(energy_cards)
        ],
        "tools": [
            {"id": value, "serial": serial * 1000 + index, "playerIndex": owner}
            for index, value in enumerate(tools)
        ],
        "preEvolution": [],
    }


def _player(*, active, bench=(), hand=(), hand_count=None, prizes=6,
            own=True, status=False):
    visible_hand = [
        {"id": value, "serial": 8000 + index, "playerIndex": 0}
        for index, value in enumerate(hand)
    ]
    return {
        "active": [active], "bench": list(bench), "benchMax": 5,
        "deckCount": 20, "prize": [None] * prizes,
        "discard": [{"id": 7, "serial": 9000, "playerIndex": 0 if own else 1}],
        "handCount": len(hand) if hand_count is None else hand_count,
        "hand": visible_hand if own else None,
        "poisoned": status, "burned": status, "asleep": status,
        "paralyzed": status, "confused": status,
    }


__all__ = (
    "OBSERVATION_SENSITIVITY_WITNESSES", "PARAMETER_SENSITIVITY_WITNESSES",
    "SENSITIVITY_WITNESSES",
    "ClauseSensitivityResult", "ObservationSensitivityResult", "SensitivityResult",
    "ParameterSensitivityWitness", "SensitivityWitness",
    "card_clause_contribution", "card_probe_contribution",
    "run_clause_sensitivity",
    "run_observation_sensitivity", "run_parameter_sensitivity",
    "run_sensitivity_witness",
)
