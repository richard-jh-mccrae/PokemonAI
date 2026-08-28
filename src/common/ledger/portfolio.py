from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import comb

from common.cards import card_clauses
from common.cards.card_facts import EnergyCard, PokemonCard, TrainerCard, STADIUM, SUPPORTER, TOOL
from common.cards.functions.fetch import DEADNESS, WINDOW, fetch_target_matches

from .capabilities import (DAMAGE_UNIT_HP, OptionUnits, _heal_rider_cost,
                           _heal_targets, _healed_hp, clause_cost_units)


HAND_POKEMON_REALIZATION_DISCOUNT = 0.25


@dataclass(frozen=True, slots=True)
class _Fetch:
    eligible: tuple[int, ...]
    amount: float
    to_bench: bool
    zone: str
    field: str = "search"
    distinct_groups: tuple[tuple[int, int], ...] = ()
    consumes: bool = True
    target_resources: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _Opportunity:
    units: OptionUnits
    requirements: tuple[tuple[str, float], ...]
    discard_cost: int
    fetches: tuple[_Fetch, ...] = ()
    discards_hand: bool = False


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    units: OptionUnits
    binding_features: tuple[str, ...]


def _requirements(facts, side, board, ctx) -> tuple[tuple[str, float], ...] | None:
    if isinstance(facts, EnergyCard):
        if board.turn.energy_attached or not side.bodies:
            return None
        return (("energy", 1.0), (f"hand:{facts.card_id}", 1.0))
    if isinstance(facts, PokemonCard):
        if facts.evolves_from is None:
            return (("bench", 1.0), (f"hand:{facts.card_id}", 1.0)) \
                if len(side.bench) < side.bench_max else None
        if not any(
                not body.appeared_this_turn
                and getattr(ctx.facts(body.card.card_id), "name", None) == facts.evolves_from
                for body in side.bodies):
            return None
        return ((f"evolve:any:{facts.evolves_from}", 1.0),
                (f"evolve:mature:{facts.evolves_from}", 1.0),
                (f"hand:{facts.card_id}", 1.0))
    if not isinstance(facts, TrainerCard):
        return None
    if facts.kind == SUPPORTER:
        return None if board.turn.supporter_played else (
            ("supporter", 1.0), (f"hand:{facts.card_id}", 1.0))
    if facts.kind == STADIUM:
        return None if board.turn.stadium_played else (
            ("stadium", 1.0), (f"hand:{facts.card_id}", 1.0))
    if facts.kind == TOOL:
        return (("tool", 1.0), (f"hand:{facts.card_id}", 1.0)) \
            if any(not body.tools for body in side.bodies) else None
    return ((f"hand:{facts.card_id}", 1.0),)


def _capacities(side, board, ctx) -> dict[str, float]:
    capacities = {
        "supporter": int(not board.turn.supporter_played),
        "energy": int(not board.turn.energy_attached),
        "stadium": int(not board.turn.stadium_played),
        "bench": max(0, side.bench_max - len(side.bench)),
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
    return capacities


def _add(left: OptionUnits, right: OptionUnits) -> OptionUnits:
    return OptionUnits(**{
        name: getattr(left, name) + getattr(right, name)
        for name in OptionUnits.__dataclass_fields__
    })


def _scale(units: OptionUnits, multiplier: float) -> OptionUnits:
    return OptionUnits(**{
        name: getattr(units, name) * multiplier
        for name in OptionUnits.__dataclass_fields__
    })


def _with_unit(units: OptionUnits, name: str, value: float) -> OptionUnits:
    return OptionUnits(**{
        field: value if field == name else getattr(units, field)
        for field in OptionUnits.__dataclass_fields__
    })


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


def _fetch_variants(facts, units, requirements, side, board, ctx):
    clauses = tuple(clause for clause in card_clauses(facts)
                    if clause.kind == "fetch"
                    and clause.zone in {"deck", "discard", "hand"})
    if not clauses:
        return (_Opportunity(units, requirements, 0),)

    def fetch(clause):
        source_counts = _source_counts(clause.zone, side, board)
        reading = DEADNESS if clause.target == "any" else WINDOW

        def evolution_base(candidate):
            if clause.dest != "in_play":
                return None
            names = {getattr(ctx.facts(body.card.card_id), "name", None)
                     for body in side.bodies
                     if not clause.target_condition or not body.appeared_this_turn}
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
            for key in ((f"evolve:any:{base}",)
                        if not clause.target_condition else (
                f"evolve:any:{base}", f"evolve:mature:{base}")))
        if distinct:
            cap = min(cap, len({group for _card_id, group in distinct}))
        amount = min(cap, copies)
        if clause.dig:
            amount = _expected_capped_hits(
                sum(source_counts.values()), copies, int(clause.dig), int(cap))
        return _Fetch(eligible, float(amount), clause.dest == "bench",
                      str(clause.zone), "search", distinct, clause.dest != "deck_top",
                      target_resources)

    fetches = tuple(fetch(clause) for clause in clauses)
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
                              for pair in item.target_resources})))
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


def _realize_fetches(opportunity, usage, capacities):
    if not opportunity.fetches:
        return (), opportunity.units
    requirements = []
    claimed = Counter()
    bench_claim = 0
    local_usage = dict(usage)
    used_groups = set()
    bench_available = capacities.get("bench", 0.0) - usage.get("bench", 0.0)
    for fetch in sorted(opportunity.fetches, key=lambda item: len(item.eligible)):
        wanted = min(fetch.amount, int(bench_available) if fetch.to_bench else fetch.amount)
        for card_id in fetch.eligible:
            group = next((value for target, value in fetch.distinct_groups
                          if target == card_id), None)
            if group is not None and group in used_groups:
                continue
            source_key = f"{fetch.zone}:{card_id}"
            available = capacities.get(source_key, 0.0) - local_usage.get(source_key, 0.0)
            target_keys = tuple(key for target, key in fetch.target_resources
                                if target == card_id)
            for target_key in target_keys:
                available = min(
                    available,
                    capacities.get(target_key, 0.0) - local_usage.get(target_key, 0.0))
            take = min(wanted, available)
            if group is not None:
                take = min(take, 1.0)
            if take:
                if fetch.consumes:
                    requirements.append((source_key, float(take)))
                    local_usage[source_key] = local_usage.get(source_key, 0.0) + take
                for target_key in target_keys:
                    requirements.append((target_key, float(take)))
                    local_usage[target_key] = local_usage.get(target_key, 0.0) + take
                wanted -= take
                claimed[fetch.field] += take
                if group is not None:
                    used_groups.add(group)
                if fetch.to_bench:
                    bench_available -= take
                    bench_claim += take
            if not wanted:
                break
    if bench_claim:
        requirements.append(("bench", float(bench_claim)))
    realized = opportunity.units
    for field in {fetch.field for fetch in opportunity.fetches}:
        amount = claimed.get(field, 0.0)
        realized = _with_unit(
            realized, field, min(getattr(realized, field), float(amount)))
    return tuple(requirements), realized


def feasible_option_portfolio_result(entries, side, board, ctx, *, hand_size: int
                                     ) -> PortfolioResult:
    capacities = _capacities(side, board, ctx)
    opportunities = []
    unconstrained_entries = []
    for index, (facts, units) in enumerate(entries):
        requirements = _requirements(facts, side, board, ctx)
        if requirements is None:
            continue
        card_key = f"card:{index}"
        capacities[card_key] = 1.0
        requirements = (*requirements, (card_key, 1.0))
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
            units = _scale(units, HAND_POKEMON_REALIZATION_DISCOUNT)
        variants = _fetch_variants(facts, units, requirements, side, board, ctx)
        if any(clause.kind == "heal" for clause in card_clauses(facts)):
            variants = _heal_variants(facts, units, requirements, side, board, ctx)
        energy_claims = _energy_claims(facts, side, board, ctx)
        realized_opportunities = tuple(_Opportunity(
            _with_energy_ceiling(facts, opportunity.units, energy_claims),
            opportunity.requirements, discard_cost,
            (*opportunity.fetches, *energy_claims), discards_hand)
            for opportunity in variants)
        opportunities.extend(realized_opportunities)
        if realized_opportunities:
            unconstrained_entries.append(max(
                (opportunity.units for opportunity in realized_opportunities),
                key=lambda candidate: _weighted_worth(candidate, ctx)))

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

    keys = tuple(sorted(capacities))
    initial = tuple(0 for _key in keys)
    states = {(initial, 0, 0, False): OptionUnits()}
    opportunities.sort(key=lambda opportunity: (opportunity.discards_hand, sum(
        len(fetch.eligible) for fetch in opportunity.fetches) or side.deck_count + 1))
    for opportunity in opportunities:
        expanded = dict(states)
        for (used, plays, discards, exhausted), units in states.items():
            if exhausted:
                continue
            usage = dict(zip(keys, used))
            feasible = True
            fetch_requirements, realized_units = _realize_fetches(
                opportunity, usage, capacities)
            for requirement, amount in (*opportunity.requirements, *fetch_requirements):
                if usage.get(requirement, 0.0) + amount > capacities.get(
                        requirement, 0.0):
                    feasible = False
                    break
                usage[requirement] = usage.get(requirement, 0.0) + amount
            if not feasible:
                continue
            next_plays = plays + 1
            hand_resources_used = sum(
                amount for name, amount in usage.items() if name.startswith("hand:"))
            next_discards = (max(discards, hand_size - hand_resources_used)
                             if opportunity.discards_hand else
                             discards + opportunity.discard_cost)
            if hand_resources_used + next_discards > hand_size:
                continue
            key = (tuple(usage.get(name, 0) for name in keys), next_plays,
                   next_discards, opportunity.discards_hand)
            candidate = _add(units, realized_units)
            if _weighted_worth(candidate, ctx) > _weighted_worth(
                    expanded.get(key, OptionUnits()), ctx):
                expanded[key] = candidate
        states = expanded
    chosen = max(states.values(), key=lambda units: _weighted_worth(units, ctx))
    unconstrained = OptionUnits()
    for units in unconstrained_entries:
        unconstrained = _add(unconstrained, units)
    binding = tuple(
        f"option.{field}" for field in OptionUnits.__dataclass_fields__
        if getattr(chosen, field) < getattr(unconstrained, field))
    return PortfolioResult(chosen, binding)


__all__ = ("PortfolioResult", "feasible_option_portfolio_result")
