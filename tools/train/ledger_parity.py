from __future__ import annotations

import hashlib
from collections import Counter

from common.decision import (ContinuationOpportunity, EvaluationStatus,
                             RealizedOutcome)
from common.ledger.evaluate import evaluate
from common.ledger.preview import price_actions


def _opportunity_sources_match(left, right, kind):
    left = tuple(value for value in left if str(value) == kind)
    right = tuple(value for value in right if str(value) == kind)
    if not left:
        return False
    if not right:
        return any(getattr(value, "source", None) is None for value in left)
    left_sources = {getattr(value, "source", None) for value in left}
    right_sources = {getattr(value, "source", None) for value in right}
    if None in left_sources or None in right_sources:
        return True
    return bool(left_sources.intersection(right_sources))


def _attachment_target_value(footprint):
    return sum(
        component.value for component in footprint.policy_contributions
        if component.feature == "action.attachment_target_fit")


def legacy_choose(prices, *, forced, configuration):
    if forced:
        return _legacy_ranked(
            prices, configuration, include_action_opportunity=True)[0]
    def policy_value(price):
        return (price.swing + price.footprint.action_opportunity
                - _attachment_target_value(price.footprint))

    enders = tuple(price for price in prices if price.ends_turn)
    explicit_end = any(
        RealizedOutcome.EXPLICIT_TURN_END in price.footprint.realized_outcomes
        for price in enders)
    only_explicit_end = bool(enders) and all(
        RealizedOutcome.EXPLICIT_TURN_END in price.footprint.realized_outcomes
        for price in enders)
    best_ender_value = max((price.swing for price in enders),
                           default=float("-inf"))
    ready_knockout_enders = tuple(
        price for price in enders
        if {RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,
            RealizedOutcome.OPPONENT_BODY_KNOCKOUT}.intersection(
                price.footprint.realized_outcomes))
    ready_winning_enders = tuple(
        price for price in ready_knockout_enders
        if (RealizedOutcome.GAME_WIN in price.footprint.realized_outcomes
            or any(component.feature in {"result.win", "active.terminal_liability"}
                   and component.value > 0
                   for component in price.footprint.contributions)))
    continuation_threshold = (
        0.0 if explicit_end or ready_knockout_enders
        else min(0.0, best_ender_value))

    def meaningful(price):
        return policy_value(price) > continuation_threshold + configuration.noise_tolerance

    def eligible_attachment(price):
        if price.action.identity.kind != "attach":
            return True
        if any(
                component.provenance[:1] == ("action.realized_portfolio",)
                and component.feature.startswith("function.cost_reduction")
                for component in price.footprint.policy_contributions):
            return False
        immediate = {"attack", "retreat"}.intersection(
            price.footprint.opportunities_created)
        return (price.swing > best_ender_value + configuration.noise_tolerance
                or price.swing > configuration.noise_tolerance
                or bool(immediate))

    def repays_action_cost(price):
        cost = -sum(component.value for component in price.footprint.policy_contributions
                    if component.feature == "action.opportunity_cost")
        return price.footprint.action_opportunity > cost + configuration.noise_tolerance

    def worth_before_knockout(price):
        if not meaningful(price):
            return False
        refresh = ("supporter_played" in price.footprint.allowances_consumed
                   and "hand" in price.footprint.zones_replaced)
        transient_play = (
            price.action.identity.kind == "play"
            and "in_play" not in price.footprint.immediately_usable_outputs)
        if not refresh and not transient_play:
            return True
        knockout_value = max(ready.swing for ready in ready_knockout_enders)
        return policy_value(price) > knockout_value + configuration.noise_tolerance

    continuing = tuple(price for price in prices
                       if not price.ends_turn and meaningful(price)
                       and eligible_attachment(price))
    ability_would_be_consumed = any(
        not price.ends_turn
        and "ability" in price.footprint.opportunities_consumed
        for price in prices)
    recycling_draws = tuple(
        price for price in prices
        if not price.ends_turn
        and price.action.identity.kind == "ability"
        and not price.footprint.allowances_consumed
        and "attach" not in price.footprint.opportunities_consumed
        and {"deck", "hand"}.issubset(price.footprint.zones_replaced)
        and ("in_play" in price.footprint.zones_replaced
             or ability_would_be_consumed)
        and "hand" in price.footprint.immediately_usable_outputs
        and {"end", "play"}.issubset(price.footprint.opportunities_preserved))
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in recycling_draws
                                  if id(price) not in continuing_ids))
    durable_development = tuple(
        price for price in prices
        if not price.ends_turn
        and repays_action_cost(price)
        and "in_play" in price.footprint.immediately_usable_outputs
        and ((price.action.identity.kind == "play")
             or (price.action.identity.kind == "evolve"
                 and "ready_attacker" in price.footprint.immediately_usable_outputs))
        and {"end", "play"}.issubset(price.footprint.opportunities_preserved))
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in durable_development
                                  if id(price) not in continuing_ids))
    lethal_preparation = tuple(
        price for price in prices
        if not price.ends_turn
        and ContinuationOpportunity.LETHAL_ATTACK in
        price.footprint.opportunities_created
        and "attack" in {
            *price.footprint.opportunities_created,
            *price.footprint.opportunities_preserved})
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in lethal_preparation
                                  if id(price) not in continuing_ids))
    attack_preparation = tuple(
        price for price in prices
        if not price.ends_turn
        and "attack" in price.footprint.opportunities_created
        and "retreat" in {
            *price.footprint.opportunities_created,
            *price.footprint.opportunities_preserved})
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in attack_preparation
                                  if id(price) not in continuing_ids))
    realized_attachments = tuple(
        price for price in prices
        if not price.ends_turn
        and price.action.identity.kind == "attach"
        and ({"end", "play"}.issubset(price.footprint.opportunities_preserved)
             or only_explicit_end)
        and any(
            component.value > configuration.noise_tolerance
            and component.feature == "option.energy"
            and component.provenance[:1] == ("action.realized_portfolio",)
            for component in price.footprint.policy_contributions))
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in realized_attachments
                                  if id(price) not in continuing_ids))
    def has_policy_provenance(price, marker, *, negative=False):
        return any(
            (component.value < -configuration.noise_tolerance
             if negative else component.value > configuration.noise_tolerance)
            and marker in component.provenance
            for component in price.footprint.policy_contributions)

    destructive_play_available = any(
        price.action.identity.kind == "play"
        and (has_policy_provenance(
            price, "action.compound_discard_spend", negative=True)
             or has_policy_provenance(
                 price, "action.discard_spend", negative=True))
        for price in prices)
    realized_plays = tuple(
        price for price in prices
        if not price.ends_turn
        and price.action.identity.kind == "play"
        and (policy_value(price) > (
                min(0.0, best_ender_value) + configuration.noise_tolerance)
             or (destructive_play_available
                 and has_policy_provenance(price, "action.recovery")))
        and "in_play" not in price.footprint.immediately_usable_outputs
        and {"end", "play"}.issubset(price.footprint.opportunities_preserved)
        and any(
            component.value > configuration.noise_tolerance
            and component.provenance[:1] == ("action.realized_portfolio",)
            for component in price.footprint.policy_contributions))
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in realized_plays
                                  if id(price) not in continuing_ids))
    retreat_attachments = tuple(
        price for price in prices
        if not price.ends_turn
        and price.action.identity.kind == "attach"
        and "retreat" in price.footprint.opportunities_created
        and {"end", "play"}.issubset(price.footprint.opportunities_preserved))
    retreat_attachments = tuple(
        price for price in retreat_attachments
        if not any(
            component.provenance[:1] == ("action.realized_portfolio",)
            and component.feature.startswith("function.cost_reduction")
            for component in price.footprint.policy_contributions))
    if (len(retreat_attachments) < 2
            or not any(any(
                component.feature == "option.energy"
                and component.value > configuration.noise_tolerance
                and component.provenance[:1] == ("action.realized_portfolio",)
                for component in price.footprint.policy_contributions)
                for price in retreat_attachments)):
        retreat_attachments = ()
    accelerating_attachments = tuple(
        price for price in prices
        if not price.ends_turn
        and price.swing > configuration.noise_tolerance
        and price.action.identity.kind == "attach"
        and {"attack", "retreat"}.intersection(
            price.footprint.opportunities_created))
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in retreat_attachments
                                  if id(price) not in continuing_ids))
    if accelerating_attachments:
        continuing = tuple(
            price for price in continuing
            if price.action.identity.kind != "attach"
            or price in accelerating_attachments)
    winning_preparation = tuple(
        price for price in prices
        if not price.ends_turn
        and ContinuationOpportunity.WINNING_ATTACK in
        price.footprint.opportunities_created
        and "attack" in {
            *price.footprint.opportunities_created,
            *price.footprint.opportunities_preserved})
    positive_refresh = tuple(
        price for price in prices
        if not price.ends_turn
        and policy_value(price) > configuration.noise_tolerance
        and "supporter_played" in price.footprint.allowances_consumed
        and "hand" in price.footprint.zones_replaced
        and "hand" in price.footprint.immediately_usable_outputs)
    continuing_ids = {id(price) for price in continuing}
    continuing = (*continuing, *(price for price in positive_refresh
                                  if id(price) not in continuing_ids))
    refresh_available = any(
        "supporter_played" in price.footprint.allowances_consumed
        and "hand" in price.footprint.zones_replaced
        for price in continuing)
    if refresh_available:
        durable_preparation = tuple(
            price for price in prices
            if not price.ends_turn
            and "in_play" in price.footprint.immediately_usable_outputs
            and (price.footprint.opportunities_created
                 or price.action.identity.kind == "evolve"
                 or meaningful(price))
            and "play" in price.footprint.opportunities_preserved
            and price not in continuing)
        continuing = (*continuing, *durable_preparation)
    if ready_winning_enders:
        continuing = ()
    elif winning_preparation:
        continuing = winning_preparation
    elif ready_knockout_enders:
        continuing = tuple(
            price for price in continuing
            if ((price.action.identity.kind != "attach"
                 or not accelerating_attachments
                 or price in accelerating_attachments)
                and (worth_before_knockout(price)
                     or price in lethal_preparation)))
    elif retreat_attachments:
        continuing = retreat_attachments
    if continuing:
        return _legacy_ranked(_legacy_preservation_frontier(
            continuing, configuration.noise_tolerance), configuration,
            include_action_opportunity=True,
            include_dependency_opportunity=True)[0]
    if ready_winning_enders:
        return _legacy_ranked(ready_winning_enders, configuration)[0]
    if ready_knockout_enders:
        active_knockouts = tuple(
            price for price in ready_knockout_enders
            if RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT in
            price.footprint.realized_outcomes)
        attacks = tuple(
            price for price in enders
            if RealizedOutcome.ACTION_ENDED_TURN in
            price.footprint.realized_outcomes
            and (not active_knockouts
                 or price in active_knockouts
                 or not price.footprint.contributions))
        return _legacy_ranked(attacks, configuration)[0]
    return _legacy_ranked(enders or prices, configuration)[0]


def _legacy_preservation_frontier(candidates, noise_tolerance=0.0):
    compare_attachment_targets = all(
        candidate.action.identity.kind == "attach" for candidate in candidates)

    def value(candidate):
        return (candidate.swing + candidate.footprint.action_opportunity
                - (0.0 if compare_attachment_targets else
                   _attachment_target_value(candidate.footprint)))

    def realized_source_value(candidate):
        return sum(
            max(0.0, component.value)
            for component in candidate.footprint.policy_contributions
            if component.provenance[:1] == ("action.realized_portfolio",))

    def destructive_spend(candidate):
        return any(
            component.value < -noise_tolerance
            and component.provenance[:1] in {
                ("action.compound_discard_spend",), ("action.discard_spend",)}
            for component in candidate.footprint.policy_contributions)

    def realized_recovery(candidate):
        return any(
            component.value > noise_tolerance
            and "action.recovery" in component.provenance
            for component in candidate.footprint.policy_contributions)

    deferred = set()
    for candidate in candidates:
        consumed = set(candidate.footprint.opportunities_consumed)
        for other in candidates:
            if other is candidate:
                continue
            preserved = set(other.footprint.opportunities_preserved)
            allowances_consumed = getattr(
                candidate.footprint, "allowances_consumed", ())
            zones_replaced = getattr(
                candidate.footprint, "zones_replaced", ())
            opportunities_created = getattr(
                other.footprint, "opportunities_created", ())
            immediately_usable_outputs = getattr(
                other.footprint, "immediately_usable_outputs", ())
            other_allowances_consumed = getattr(
                other.footprint, "allowances_consumed", ())
            same_exclusive_spend = (
                consumed
                and consumed == set(other.footprint.opportunities_consumed)
                and candidate.action.identity.kind == other.action.identity.kind
                and any(component.feature == "action.survival_tool_target"
                        for price in (candidate, other)
                        for component in price.footprint.policy_contributions)
                and value(other) > value(candidate) + noise_tolerance)
            if same_exclusive_spend:
                deferred.add(candidate.action.identity)
                break
            spare_scarce_attachment = (
                candidate.action.identity.kind == "attach"
                and other.action.identity.kind == "attach"
                and consumed == set(other.footprint.opportunities_consumed)
                and candidate.footprint.opportunities_created
                == other.footprint.opportunities_created
                and candidate.footprint.opportunities_preserved
                == other.footprint.opportunities_preserved
                and realized_source_value(candidate)
                > realized_source_value(other) + noise_tolerance)
            if spare_scarce_attachment:
                deferred.add(candidate.action.identity)
                break
            recover_before_destructive_search = (
                candidate.action.identity.kind == "play"
                and other.action.identity.kind == "play"
                and destructive_spend(candidate)
                and realized_recovery(other)
                and "play" in preserved)
            if recover_before_destructive_search:
                deferred.add(candidate.action.identity)
                break
            refresh_after_preparation = (
                "supporter_played" in allowances_consumed
                and "hand" in zones_replaced
                and "hand" in candidate.footprint.immediately_usable_outputs
                and (bool(opportunities_created)
                     or "in_play" in immediately_usable_outputs)
                and "play" in preserved
                and "supporter_played" not in other_allowances_consumed)
            if refresh_after_preparation:
                deferred.add(candidate.action.identity)
                break
            deploy_before_transient_play = (
                candidate.action.identity.kind == "play"
                and "in_play" not in candidate.footprint.immediately_usable_outputs
                and "in_play" in immediately_usable_outputs
                and "play" in preserved)
            if deploy_before_transient_play:
                deferred.add(candidate.action.identity)
                break
            create_before_plain_play = (
                candidate.action.identity.kind == "play"
                and other.action.identity.kind == "play"
                and bool(opportunities_created)
                and not candidate.footprint.opportunities_created
                and "in_play" in immediately_usable_outputs
                and "play" in preserved)
            if create_before_plain_play:
                deferred.add(candidate.action.identity)
                break
            dependency_refresh = (
                ContinuationOpportunity.DEPENDENCY_REACH in
                candidate.footprint.opportunities_created
                and value(candidate) > value(other) + noise_tolerance)
            if dependency_refresh:
                continue
            prepare_before_retreat = (
                candidate.action.identity.kind == "retreat"
                and (((value(other) > noise_tolerance
                       or "attack" in opportunities_created)
                      and bool(opportunities_created))
                     or (other.action.identity.kind == "evolve"
                         and "ready_attacker" in immediately_usable_outputs))
                and "retreat" in preserved)
            if prepare_before_retreat:
                deferred.add(candidate.action.identity)
                break
            live_attachment_before_optional_body = (
                candidate.action.identity.kind == "play"
                and "in_play" in candidate.footprint.immediately_usable_outputs
                and other.action.identity.kind == "attach"
                and ("retreat" in opportunities_created
                     or any(component.feature == "option.energy"
                            for component in other.footprint.policy_contributions))
                and "play" in preserved
                and "discard" not in
                    candidate.footprint.immediately_usable_outputs
                and "attach" in candidate.footprint.opportunities_preserved)
            if live_attachment_before_optional_body:
                deferred.add(candidate.action.identity)
                break
            compound_development_before_attachment = (
                candidate.action.identity.kind == "attach"
                and other.action.identity.kind == "play"
                and "discard" in immediately_usable_outputs
                and "in_play" in immediately_usable_outputs
                and "attach" in opportunities_created
                and "attach" in preserved)
            if compound_development_before_attachment:
                deferred.add(candidate.action.identity)
                break
            if not consumed:
                continue
            live_attachment = (
                candidate.action.identity.kind == "attach"
                and ("retreat" in candidate.footprint.opportunities_created
                     or any(component.feature == "option.energy"
                            for component in
                            candidate.footprint.policy_contributions)))
            create_before_consume = (
                candidate.action.identity.kind in opportunities_created
                and candidate.action.identity.kind in preserved
                and _opportunity_sources_match(
                    consumed, opportunities_created,
                    candidate.action.identity.kind)
                and not live_attachment)
            if create_before_consume:
                deferred.add(candidate.action.identity)
                break
            use_expiring_ability = (
                other.action.identity.kind == "ability"
                and candidate.action.identity.kind == "evolve"
                and other.swing > noise_tolerance
                and _opportunity_sources_match(
                    consumed, other.footprint.opportunities_consumed,
                    "ability"))
            if use_expiring_ability:
                deferred.add(candidate.action.identity)
                break
            if other.swing + noise_tolerance < candidate.swing:
                continue
            other_kind = other.action.identity.kind
            consumed_inventory = Counter(
                (str(opportunity), getattr(opportunity, "source", None))
                for opportunity in consumed if str(opportunity) == other_kind)
            executed = other.footprint.executed_opportunity
            executed_key = (
                other_kind,
                (getattr(executed, "source", None)
                 if executed is not None and str(executed) == other_kind else None))
            at_risk = Counter({executed_key: consumed_inventory[executed_key]})
            created_inventory = Counter(
                (str(opportunity), getattr(opportunity, "source", None))
                for opportunity in candidate.footprint.opportunities_created
                if str(opportunity) == other_kind)
            consumed_count = sum(at_risk.values())
            replacement_count = sum((created_inventory & at_risk).values())
            if (other_kind in consumed
                    and replacement_count < consumed_count
                    and candidate.action.identity.kind in preserved):
                deferred.add(candidate.action.identity)
                break
    kept = tuple(candidate for candidate in candidates
                 if candidate.action.identity not in deferred)
    return kept or tuple(candidates)


def assert_decision_parity(prices, search_result, choice, *, forced, configuration):
    candidates = search_result.roster.candidates
    if len(prices) != len(candidates):
        raise AssertionError("candidate roster size changed")
    for price, candidate in zip(prices, candidates):
        if price.action.identity != candidate.action.identity:
            raise AssertionError("candidate roster order changed")
        if price.status is not candidate.status:
            raise AssertionError(f"candidate status changed: {price.action.identity}")
        if price.status is EvaluationStatus.UNAVAILABLE:
            if candidate.delta is not None:
                raise AssertionError("unavailable candidate acquired a delta")
            continue
        if candidate.delta is None or candidate.delta.total != price.swing:
            raise AssertionError(f"candidate delta changed: {price.action.identity}")
        expected = tuple((item.feature, item.activation, item.coefficient,
                          item.value, item.provenance)
                         for item in price.footprint.contributions)
        actual = tuple((item.key, item.activation, item.coefficient,
                        item.value, item.provenance)
                       for item in candidate.delta.components)
        if actual != expected:
            raise AssertionError(
                f"candidate decomposition changed: {price.action.identity}; "
                f"expected={expected!r}; actual={actual!r}")
        expected_tie_break = _policy_tie_break(price)
        if candidate.policy_tie_break != expected_tie_break:
            raise AssertionError(f"candidate tie break changed: {price.action.identity}")
    comparable = tuple(
        price for price in prices if price.status is not EvaluationStatus.UNAVAILABLE)
    if not comparable:
        return
    legacy = legacy_choose(
        comparable, forced=forced, configuration=configuration)
    if legacy.action.identity != choice.action.identity:
        raise AssertionError(
            f"deployed choice changed: deployed={choice.action.identity}; "
            f"recomputed={legacy.action.identity}")


def assert_runtime_parity(*, state, board, provider, evaluation_model, result,
                          search_configuration, policy_configuration):
    baseline = evaluate(board, evaluation_model)
    prices = price_actions(
        state, board, baseline.total, provider, evaluation_model,
        search_configuration)

    class Choice:
        action = result.chosen

    assert_decision_parity(
        prices, result.search, Choice(), forced=result.roster.forced,
        configuration=policy_configuration)


def _legacy_ranked(prices, configuration, *, include_action_opportunity=False,
                   include_dependency_opportunity=False):
    compare_attachment_targets = all(
        price.action.identity.kind == "attach" for price in prices)
    dependency_roster = (
        include_dependency_opportunity
        and any(ContinuationOpportunity.DEPENDENCY_REACH in
                price.footprint.opportunities_created
                for price in prices))

    def value(price):
        include = include_action_opportunity or dependency_roster
        return price.swing + (
            price.footprint.action_opportunity
            - (0.0 if compare_attachment_targets else
               _attachment_target_value(price.footprint))
            if include else 0.0)

    remaining = list(enumerate(prices))
    ranked = []
    while remaining:
        best = max(value(price) for _index, price in remaining)
        tied = tuple((index, price) for index, price in remaining
                     if best - value(price) <= configuration.noise_tolerance)
        exact = all(value(price) == best for _index, price in tied)
        tied = tuple(sorted(tied, key=lambda indexed: (
            (_policy_tie_break(indexed[1]) if exact else ()),
            hashlib.blake2b(
                f"{configuration.tie_seed}:{indexed[1].action.identity}".encode("utf-8"),
                digest_size=8).digest())))
        ranked.extend(price for _index, price in tied)
        tied_indices = {index for index, _price in tied}
        remaining = tuple((index, price) for index, price in remaining
                          if index not in tied_indices)
    return tuple(ranked)


def _policy_tie_break(price):
    commitment = sum(
        component.value for component in price.footprint.policy_contributions
        if component.feature == "action.evolution_target_commitment")
    prize = (() if price.prize_map is None else price.prize_map.plan_rank_key())
    return (-commitment, *prize)


__all__ = ("assert_decision_parity", "assert_runtime_parity", "legacy_choose")
