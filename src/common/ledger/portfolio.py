from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from math import comb

from common.cards import card_clauses
from common.cards.card_facts import EnergyCard, PokemonCard, TrainerCard, STADIUM, SUPPORTER, TOOL
from common.cards.functions.fetch import DEADNESS, WINDOW, fetch_target_matches

from .capabilities import (DAMAGE_UNIT_HP, OptionUnits, _heal_rider_cost,
                           _heal_targets, _healed_hp, card_option_units,
                           clause_cost_units)
from .portfolio_solver import (
    Fetch as _Fetch,
    Opportunity as _Opportunity,
    PortfolioProblem,
    PortfolioSolveStatistics,
    TurnPortfolioMemo,
    add_units as _add,
    solve_portfolio,
    with_unit as _with_unit,
)
from .worth import FUTURE_TURN_DISCOUNT


HAND_POKEMON_REALIZATION_DISCOUNT = 0.25
FETCHED_POKEMON_REALIZATION_DISCOUNT = FUTURE_TURN_DISCOUNT


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    units: OptionUnits
    binding_features: tuple[str, ...]
    selected_indices: tuple[int, ...] = ()
    selected_units: tuple[tuple[int, OptionUnits], ...] = ()
    statistics: PortfolioSolveStatistics = PortfolioSolveStatistics()


def _requirements(facts, side, board, ctx) -> tuple[tuple[str, float], ...] | None:
    if isinstance(facts, EnergyCard):
        if not side.bodies:
            return None
        allowance = "future_energy" if board.turn.energy_attached else "energy"
        return ((allowance, 1.0), (f"hand:{facts.card_id}", 1.0))
    if isinstance(facts, PokemonCard):
        if facts.evolves_from is None:
            allowance = "bench" if len(side.bench) < side.bench_max else "future_bench"
            return ((allowance, 1.0), (f"hand:{facts.card_id}", 1.0))
        mature_predecessor = any(
            not body.appeared_this_turn
            and getattr(ctx.facts(body.card.card_id), "name", None) == facts.evolves_from
            for body in side.bodies)
        if not mature_predecessor:
            return ((f"evolve:future:{facts.evolves_from}", 1.0),
                    (f"hand:{facts.card_id}", 1.0))
        return ((f"evolve:any:{facts.evolves_from}", 1.0),
                (f"evolve:mature:{facts.evolves_from}", 1.0),
                (f"hand:{facts.card_id}", 1.0))
    if not isinstance(facts, TrainerCard):
        return None
    if facts.kind == SUPPORTER:
        allowance = "future_supporter" if board.turn.supporter_played else "supporter"
        return ((allowance, 1.0), (f"hand:{facts.card_id}", 1.0))
    if facts.kind == STADIUM:
        duplicate = any(card.card_id == facts.card_id for card in board.stadium)
        return None if board.turn.stadium_played or duplicate else (
            ("stadium", 1.0), (f"hand:{facts.card_id}", 1.0))
    if facts.kind == TOOL:
        return (("tool", 1.0), (f"hand:{facts.card_id}", 1.0)) \
            if any(not body.tools for body in side.bodies) else None
    return ((f"hand:{facts.card_id}", 1.0),)


def _capacities(side, board, ctx) -> dict[str, float]:
    capacities = {
        "supporter": int(not board.turn.supporter_played),
        "future_supporter": int(board.turn.supporter_played),
        "energy": int(not board.turn.energy_attached),
        "future_energy": int(board.turn.energy_attached),
        "stadium": int(not board.turn.stadium_played),
        "bench": max(0, side.bench_max - len(side.bench)),
        "future_bench": 1,
        "tool": sum(not body.tools for body in side.bodies),
    }
    for body in side.bodies:
        facts = ctx.facts(body.card.card_id)
        name = getattr(facts, "name", None)
        if name:
            any_key = f"evolve:any:{name}"
            capacities[any_key] = capacities.get(any_key, 0) + 1
            if not body.appeared_this_turn:
                mature_key = f"evolve:mature:{name}"
                capacities[mature_key] = capacities.get(mature_key, 0) + 1
    future_bases = Counter()
    for body in side.bodies:
        if body.appeared_this_turn:
            name = getattr(ctx.facts(body.card.card_id), "name", None)
            if name:
                future_bases[name] += 1
    for card in tuple(side.hand):
        name = getattr(ctx.facts(card.card_id), "name", None)
        if name:
            future_bases[name] += 1
    for card_id, count in board.deck_counts or ():
        name = getattr(ctx.facts(card_id), "name", None)
        if name:
            future_bases[name] += count
    for name, count in future_bases.items():
        capacities[f"evolve:future:{name}"] = float(count)
    return capacities


def _scale(units: OptionUnits, multiplier: float) -> OptionUnits:
    return OptionUnits(**{
        name: getattr(units, name) * multiplier
        for name in OptionUnits.__dataclass_fields__
    })


def _fielded_line_count(facts, side, ctx) -> int:
    return sum(
        facts.name in {
            getattr(ctx.facts(body.card.card_id), "name", None),
            *(getattr(ctx.facts(card.card_id), "name", None)
              for card in body.pre_evolution),
        }
        for body in side.bodies)


def _weighted_worth(units: OptionUnits, ctx) -> float:
    return sum(value * ctx.configuration[feature]
               for feature, value in units.activations())


def _expected_capped_hits(population: int, successes: int, draws: int, cap: int) -> float:
    draws = min(population, draws)
    if not population or not successes or not draws or not cap:
        return 0.0
    denominator = comb(population, draws)
    return sum(min(hits, cap) * comb(successes, hits)
               * comb(population - successes, draws - hits) / denominator
               for hits in range(max(0, draws - population + successes),
                                 min(draws, successes) + 1))


def _source_counts(zone, side, board):
    if zone == "deck":
        return dict(board.deck_counts or ())
    cards = side.discard if zone == "discard" else tuple(side.hand)
    return Counter(card.card_id for card in cards)


def _preserved_hand_resources(facts, side, board, ctx):
    reservations = []
    if isinstance(facts, TrainerCard) and facts.kind == SUPPORTER:
        allowance = "future_supporter" if board.turn.supporter_played else "supporter"
        reservations.append((allowance, 1.0))
    required_energy = {
        clause.condition_energy_type for clause in card_clauses(facts)
        if clause.condition_energy_type is not None}
    for energy_type in required_energy:
        card_id = next((
            card.card_id for card in side.hand
            if isinstance((held := ctx.facts(card.card_id)), EnergyCard)
            and held.provides == energy_type), None)
        if card_id is not None:
            reservations.append((f"hand:{card_id}", 1.0))
    evolves_from = getattr(facts, "evolves_from", None)
    predecessor_in_play = any(
        getattr(ctx.facts(body.card.card_id), "name", None) == evolves_from
        for body in side.bodies)
    if evolves_from and not predecessor_in_play:
        card_id = next((
            card.card_id for card in side.hand
            if getattr(ctx.facts(card.card_id), "name", None) == evolves_from), None)
        if card_id is not None:
            reservations.append((f"hand:{card_id}", 1.0))
    return tuple(dict.fromkeys(reservations))


def _fetch_variants(facts, units, requirements, side, board, ctx):
    clauses = tuple(clause for clause in card_clauses(facts)
                    if clause.kind == "fetch"
                    and clause.zone in {"deck", "discard", "hand"})
    if not clauses:
        return (_Opportunity(units, requirements, 0),)

    def fetch(clause):
        source_counts = _source_counts(clause.zone, side, board)
        reading = DEADNESS if clause.target == "any" else WINDOW
        field_names = {
            getattr(ctx.facts(body.card.card_id), "name", None)
            for body in side.bodies}
        deployable_names = ({
            candidate.name
            for card in tuple(side.hand)
            if isinstance((candidate := ctx.facts(card.card_id)), PokemonCard)
            and candidate.evolves_from is None}
            if len(side.bench) < side.bench_max else set())

        def evolution_base(candidate):
            if clause.dest != "in_play":
                return None
            names = {
                getattr(ctx.facts(body.card.card_id), "name", None)
                for body in side.bodies
                if not clause.target_condition or not body.appeared_this_turn}
            names.update(deployable_names)
            if candidate.evolves_from in names:
                return candidate.evolves_from
            if clause.rider != "skip_stage1":
                return None
            stage1 = next((card for card in ctx.store.values()
                           if isinstance(card, PokemonCard)
                           and card.name == candidate.evolves_from), None)
            return (stage1.evolves_from if stage1 is not None
                    and stage1.evolves_from in names else None)

        def in_play_compatible(candidate):
            return clause.dest != "in_play" or evolution_base(candidate) is not None

        eligible = tuple(card_id for card_id in source_counts
                         if fetch_target_matches(
                             clause, ctx.facts(card_id), reading=reading)
                         and (not clause.name_family or str(clause.name_family).casefold()
                              in getattr(ctx.facts(card_id), "name", "").casefold())
                         and (clause.restriction != "evolves_from_self"
                              or getattr(ctx.facts(card_id), "evolves_from", None)
                              == getattr(facts, "name", None))
                         and in_play_compatible(ctx.facts(card_id)))
        copies = sum(source_counts[card_id] for card_id in eligible)
        cap = copies if clause.amount == "all" else int(clause.amount or 1)
        distinct = tuple((card_id, getattr(ctx.facts(card_id), "provides", card_id))
                         for card_id in eligible) if clause.distinct_types else ()
        target_resources = tuple(
            (card_id, key)
            for card_id in eligible
            if (base := evolution_base(ctx.facts(card_id))) is not None
            for key in ((f"evolve:future:{base}",)
                        if base not in field_names else
                        (f"evolve:any:{base}",)
                        if not clause.target_condition else (
                f"evolve:any:{base}", f"evolve:mature:{base}")))
        target_reservations = tuple(
            (card_id, key)
            for card_id in eligible
            for key, _amount in _preserved_hand_resources(
                ctx.facts(card_id), side, board, ctx))
        if distinct:
            cap = min(cap, len({group for _card_id, group in distinct}))
        amount = min(cap, copies)
        if clause.dig:
            amount = _expected_capped_hits(
                sum(source_counts.values()), copies, int(clause.dig), int(cap))
        return _Fetch(eligible, float(amount), clause.dest == "bench",
                      str(clause.zone), "search", distinct, clause.dest != "deck_top",
                      target_resources, target_reservations)

    fetches = tuple(fetch(clause) for clause in clauses)
    if (len(fetches) == 1 and fetches[0].amount == 1
            and clauses[0].dest != "in_play"
            and isinstance(facts, TrainerCard)):
        item = fetches[0]
        target_variants = []
        mature_names = {
            getattr(ctx.facts(body.card.card_id), "name", None)
            for body in side.bodies if not body.appeared_this_turn}
        for card_id in item.eligible:
            candidate = ctx.facts(card_id)
            if (not isinstance(candidate, PokemonCard)
                    or candidate.evolves_from not in mature_names):
                continue
            target = _scale(
                card_option_units(candidate, side, board.them, board, ctx),
                FETCHED_POKEMON_REALIZATION_DISCOUNT)
            target = _with_unit(target, "search", 0.0)
            if _weighted_worth(target, ctx) <= 0.0:
                continue
            specific = replace(
                item,
                eligible=(card_id,),
                consumes=False,
                target_resources=tuple(
                    pair for pair in item.target_resources if pair[0] == card_id),
                target_reservations=tuple(
                    pair for pair in item.target_reservations if pair[0] == card_id),
            )
            target_variants.append((
                _weighted_worth(target, ctx),
                _Opportunity(
                    _add(_with_unit(units, "search", min(units.search, 1.0)), target),
                    (*requirements, (f"{item.zone}:{card_id}", 1.0)),
                    0,
                    (specific,),
                ),
            ))
        if target_variants:
            target_variants.sort(key=lambda row: row[0], reverse=True)
            generic = _Opportunity(
                _with_unit(units, "search", min(units.search, 1.0)),
                requirements, 0, fetches)
            return tuple(
                opportunity for _worth, opportunity
                in target_variants) + (generic,)
    if any(clause.choice for clause in clauses):
        declared_amounts = {clause.amount or 1 for clause in clauses}
        if len(declared_amounts) == 1:
            amount = next(iter(declared_amounts))
            source_counts = _source_counts(fetches[0].zone, side, board)
            eligible = {card_id for item in fetches for card_id in item.eligible}
            successes = sum(source_counts[card_id] for card_id in eligible)
            cap = successes if amount == "all" else min(int(amount), successes)
            digs = {int(clause.dig) for clause in clauses if clause.dig}
            available = (_expected_capped_hits(
                sum(source_counts.values()), successes, next(iter(digs)), cap)
                         if len(digs) == 1 else float(cap))
            merged = _Fetch(
                tuple(sorted(eligible)), float(available),
                any(item.to_bench for item in fetches), fetches[0].zone, "search",
                tuple(sorted({pair for item in fetches
                              for pair in item.distinct_groups})),
                all(item.consumes for item in fetches),
                tuple(sorted({pair for item in fetches
                              for pair in item.target_resources})),
                tuple(sorted({pair for item in fetches
                              for pair in item.target_reservations})))
            realized = (float(merged.amount) if isinstance(facts, EnergyCard)
                        else min(units.search, float(merged.amount)))
            return (_Opportunity(
                _with_unit(units, "search", realized),
                requirements, 0, (merged,)),)
        return tuple(_Opportunity(
            _with_unit(units, "search", min(units.search, float(item.amount))),
            requirements, 0, (item,))
                     for item in fetches if item.amount)
    amount = sum(item.amount for item in fetches)
    realized = (float(amount) if isinstance(facts, EnergyCard)
                and any(getattr(ctx.facts(body.card.card_id), "energy_type", None)
                        == next((clause.target_type for clause in clauses
                                 if clause.target_type is not None), None)
                        for body in side.bodies)
                else min(units.search, float(amount)))
    return (_Opportunity(_with_unit(units, "search", realized),
                         requirements, 0, fetches),)


def _energy_targets(clause, facts, side, ctx):
    if clause.target == "future":
        return tuple(body for body in side.bodies
                     if "future" in ctx.facts(body.card.card_id).tags)
    if clause.target in {"bench", "benched", "bench_only"}:
        targets = tuple(side.bench)
    elif clause.target == "self":
        targets = tuple(body for body in side.bodies
                        if ctx.facts(body.card.card_id).name == getattr(facts, "name", None))
        if not targets and isinstance(facts, PokemonCard):
            return (facts,)
    elif clause.target == "stage2":
        targets = tuple(body for body in side.bodies
                        if ctx.facts(body.card.card_id).stage == "stage2")
    elif clause.target == "own_line":
        names = {getattr(facts, "name", None), getattr(facts, "evolves_from", None)}
        targets = tuple(body for body in side.bodies
                        if ctx.facts(body.card.card_id).name in names)
    else:
        targets = tuple(side.bodies)
    wanted_type = clause.target_type
    if clause.target == "own_type":
        wanted_type = getattr(facts, "energy_type", None)
    if wanted_type is not None:
        targets = tuple(target for target in targets
                        if getattr(target, "energy_type", None) == wanted_type
                        or getattr(ctx.facts(target.card.card_id), "energy_type", None)
                        == wanted_type)
    return targets


def _energy_claims(facts, side, board, ctx):
    claims = []
    for clause in card_clauses(facts):
        if clause.kind not in {"accel", "energy_recur"}:
            continue
        zone = clause.source or clause.zone
        if zone not in {"deck", "discard", "hand"}:
            continue
        source_counts = _source_counts(zone, side, board)
        eligible = tuple(card_id for card_id in source_counts
                         if isinstance(ctx.facts(card_id), EnergyCard)
                         and (clause.energy != "basic"
                              or ctx.facts(card_id).kind == "basic_energy")
                         and (clause.energy_type is None
                              or ctx.facts(card_id).provides == clause.energy_type))
        target_count = len(_energy_targets(clause, facts, side, ctx))
        if not target_count:
            continue
        available = sum(source_counts[card_id] for card_id in eligible)
        attachment_count = int(clause.amount or 1) * (
            target_count if clause.each_of else 1)
        amount = min(available, attachment_count + int(clause.to_hand or 0))
        distinct = tuple((card_id, ctx.facts(card_id).provides)
                         for card_id in eligible) if clause.distinct_types else ()
        if distinct:
            amount = min(amount, len({group for _card_id, group in distinct}))
        if clause.dig:
            amount = _expected_capped_hits(
                sum(source_counts.values()), available, int(clause.dig), int(amount))
        claims.append(_Fetch(
            eligible, float(amount), False, str(zone), "acceleration", distinct))
    return tuple(claims)


def _with_energy_ceiling(facts, units, claims):
    energy_clauses = tuple(clause for clause in card_clauses(facts)
                           if clause.kind in {"accel", "energy_recur"})
    if not energy_clauses:
        return units
    available = sum(claim.amount for claim in claims)
    realized = (available if units.acceleration
                and any(clause.each_of for clause in energy_clauses)
                else min(units.acceleration, available))
    return _with_unit(units, "acceleration", realized)


def _heal_variants(facts, units, requirements, side, board, ctx):
    clauses = tuple(clause for clause in card_clauses(facts) if clause.kind == "heal")
    if not clauses:
        return (_Opportunity(units, requirements, 0),)
    variants = []
    for clause in clauses:
        targets = _heal_targets(clause, facts, side, board, ctx)
        if clause.each_of:
            target_requirements = []
            healed = 0.0
            for index, target in enumerate(targets):
                amount = _healed_hp(clause, target) / DAMAGE_UNIT_HP
                target_key = target.card.serial if target.card.serial is not None else index
                target_requirements.append((f"heal:{target_key}", amount))
                healed += amount
            variants.append(_Opportunity(
                _with_unit(units, "healing", healed),
                (*requirements, *target_requirements), 0))
            continue
        for index, target in enumerate(targets):
            healed = _healed_hp(clause, target) / DAMAGE_UNIT_HP
            target_key = target.card.serial if target.card.serial is not None else index
            target_requirements = ((f"heal:{target_key}", healed),)
            if clause.rider == "discard_own_energy":
                target_requirements += ((f"attached-energy:{target_key}",
                                         _heal_rider_cost(clause, target)),)
            variants.append(_Opportunity(
                _with_unit(units, "healing", healed),
                (*requirements, *target_requirements), 0))
    return tuple(variants)


def feasible_option_portfolio_result(entries, side, board, ctx, *, hand_size: int,
                                     reuse: TurnPortfolioMemo | None = None,
                                     reuse_identity: tuple = (), execution_guard=None
                                     ) -> PortfolioResult:
    entries = tuple(entries)
    capacities = _capacities(side, board, ctx)
    compiled_entries = []
    unconstrained_entries = []
    for index, entry in enumerate(entries):
        facts, units, *optional_direct_worth = entry
        direct_worth = (float(optional_direct_worth[0])
                        if optional_direct_worth else 0.0)
        requirements = _requirements(facts, side, board, ctx)
        if requirements is None:
            continue
        cost_clauses = (() if not isinstance(facts, TrainerCard) else tuple(
            clause for clause in card_clauses(facts) if clause.cost is not None))
        raw_cost = sum(clause_cost_units(clause, side) for clause in cost_clauses)
        discards_hand = any(clause.cost == "discard_hand" for clause in cost_clauses)
        shared_cost = max((0
                           if clause.cost == "discard_hand"
                           else clause_cost_units(clause, side)
                           for clause in cost_clauses), default=0.0)
        discard_cost = round(shared_cost)
        units = _with_unit(units, "cost", units.cost - raw_cost + shared_cost)
        if isinstance(facts, PokemonCard):
            future_evolution = any(
                requirement.startswith("evolve:future:")
                for requirement, _amount in requirements)
            equivalent_lines = (1 + _fielded_line_count(facts, side, ctx)
                                if facts.evolves_from is None else 1)
            units = _scale(
                units,
                (FUTURE_TURN_DISCOUNT if future_evolution
                 else HAND_POKEMON_REALIZATION_DISCOUNT)
                / equivalent_lines)
        elif isinstance(facts, EnergyCard) and board.turn.energy_attached:
            units = _scale(units, FUTURE_TURN_DISCOUNT)
        elif (isinstance(facts, TrainerCard) and facts.kind == SUPPORTER
              and board.turn.supporter_played):
            units = _scale(units, FUTURE_TURN_DISCOUNT)
        variants = _fetch_variants(facts, units, requirements, side, board, ctx)
        if any(clause.kind == "heal" for clause in card_clauses(facts)):
            variants = _heal_variants(facts, units, requirements, side, board, ctx)
        energy_claims = _energy_claims(facts, side, board, ctx)
        realized_opportunities = tuple(replace(_Opportunity(
            _with_energy_ceiling(facts, opportunity.units, energy_claims),
            opportunity.requirements, discard_cost,
            (*opportunity.fetches, *energy_claims), discards_hand),
            direct_worth=direct_worth,
            reservations=_preserved_hand_resources(facts, side, board, ctx))
            for opportunity in variants)
        if realized_opportunities:
            compiled_entries.append((
                getattr(facts, "card_id", None), realized_opportunities, index))
            unconstrained_entries.append(max(
                (opportunity.units for opportunity in realized_opportunities),
                key=lambda candidate: _weighted_worth(candidate, ctx)))

    class_lookup = {}
    class_variants = []
    class_sources = []
    for card_id, variants, source_index in compiled_entries:
        signature = (card_id, variants)
        group_index = class_lookup.get(signature)
        if group_index is None:
            group_index = len(class_variants)
            class_lookup[signature] = group_index
            class_variants.append(variants)
            class_sources.append([])
        class_sources[group_index].append(source_index)

    opportunities = []
    for group_index, variants in enumerate(class_variants):
        copy_key = f"copy:{group_index}"
        capacities[copy_key] = float(len(class_sources[group_index]))
        for opportunity in variants:
            opportunities.append(replace(
                opportunity,
                requirements=(*opportunity.requirements, (copy_key, 1.0)),
                entry_index=group_index,
            ))

    for body_index, body in enumerate(side.bodies):
        target_key = body.card.serial if body.card.serial is not None else body_index
        capacities[f"heal:{target_key}"] = max(0, body.max_hp - body.hp) / DAMAGE_UNIT_HP
        capacities[f"attached-energy:{target_key}"] = float(len(body.energies))
    for card_id, count in board.deck_counts or ():
        capacities[f"deck:{card_id}"] = float(max(0, count))
    for card_id, count in Counter(card.card_id for card in side.discard).items():
        capacities[f"discard:{card_id}"] = float(count)
    for card_id, count in Counter(card.card_id for card in tuple(side.hand)).items():
        capacities[f"hand:{card_id}"] = float(count)

    opportunities.sort(key=lambda opportunity: (opportunity.discards_hand, sum(
        len(fetch.eligible) for fetch in opportunity.fetches) or side.deck_count + 1))
    opportunities = tuple(
        replace(opportunity, legacy_order=index)
        for index, opportunity in enumerate(opportunities))
    relevant_capacities = set()
    for opportunity in opportunities:
        relevant_capacities.update(name for name, _amount in opportunity.requirements)
        relevant_capacities.update(name for name, _amount in opportunity.reservations)
        for fetch in opportunity.fetches:
            relevant_capacities.update(
                f"{fetch.zone}:{card_id}" for card_id in fetch.eligible)
            relevant_capacities.update(name for _card_id, name in fetch.target_resources)
            relevant_capacities.update(name for _card_id, name in fetch.target_reservations)
            if fetch.to_bench:
                relevant_capacities.add("bench")
    problem = PortfolioProblem(
        tuple(sorted((name, float(amount)) for name, amount in capacities.items()
                     if name in relevant_capacities)),
        opportunities,
        hand_size,
        tuple(ctx.configuration[feature]
              for feature, _value in OptionUnits().activations()),
        len(entries),
        len(class_variants),
    )
    cache_key = ("ledger.portfolio/v1", *reuse_identity, problem)
    plan = None if reuse is None else reuse.lookup(cache_key)
    if plan is None:
        plan, statistics = solve_portfolio(problem, execution_guard=execution_guard)
        statistics = replace(statistics, turn_cache_misses=int(reuse is not None))
        if reuse is not None:
            reuse.store(cache_key, plan)
    else:
        statistics = PortfolioSolveStatistics(
            entry_count=problem.entry_count,
            class_count=problem.class_count,
            opportunity_count=len(problem.opportunities),
            turn_cache_hits=1,
        )
    unconstrained = OptionUnits()
    for units in unconstrained_entries:
        unconstrained = _add(unconstrained, units)
    binding = tuple(
        f"option.{field}" for field in OptionUnits.__dataclass_fields__
        if getattr(plan.units, field) < getattr(unconstrained, field))
    source_offsets = Counter()
    selected = []
    for selection in plan.selections:
        source_offset = source_offsets[selection.entry_index]
        sources = class_sources[selection.entry_index]
        if source_offset >= len(sources):
            raise AssertionError("Portfolio Plan selects beyond source multiplicity")
        selected.append((sources[source_offset], selection.units))
        source_offsets[selection.entry_index] += 1
    selected_units = tuple(sorted(selected, key=lambda item: item[0]))
    return PortfolioResult(
        plan.units, binding, tuple(index for index, _units in selected_units), selected_units,
        statistics)


__all__ = ("PortfolioResult", "feasible_option_portfolio_result")
