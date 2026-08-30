from __future__ import annotations

import hashlib

from common.decision import EvaluationStatus
from common.ledger.evaluate import evaluate
from common.ledger.preview import price_actions


def legacy_choose(prices, *, forced, configuration):
    if forced:
        return _legacy_ranked(
            prices, configuration, include_action_opportunity=True)[0]
    def policy_value(price):
        return price.swing + price.footprint.action_opportunity

    enders = tuple(price for price in prices if price.ends_turn)
    explicit_end = tuple(
        price for price in enders if price.action.identity.kind == "end")
    end_value = max((policy_value(price) for price in explicit_end), default=0.0)
    continuation_threshold = min(0.0, end_value)
    knockouts = tuple(price for price in prices
                      if price.ends_turn
                      and any(item.feature in {"prize.race", "result.win"}
                              and item.activation > 0
                              for item in price.footprint.contributions))
    meaningful_continuation = any(
        not price.ends_turn
        and policy_value(price) > continuation_threshold + configuration.noise_tolerance
        for price in prices)
    if knockouts and not meaningful_continuation:
        return _legacy_ranked(knockouts, configuration)[0]
    continuing = tuple(price for price in prices
                       if not price.ends_turn
                       and policy_value(price) > (
                           continuation_threshold + configuration.noise_tolerance))
    refresh_available = any(
        "supporter_played" in price.footprint.allowances_consumed
        and "hand" in price.footprint.zones_replaced
        for price in continuing)
    if refresh_available:
        durable_preparation = tuple(
            price for price in prices
            if not price.ends_turn
            and "in_play" in price.footprint.immediately_usable_outputs
            and price.footprint.opportunities_created
            and "play" in price.footprint.opportunities_preserved
            and price not in continuing)
        continuing = (*continuing, *durable_preparation)
    if continuing:
        return _legacy_ranked(_legacy_preservation_frontier(
            continuing, configuration.noise_tolerance), configuration)[0]
    return _legacy_ranked(enders or prices, configuration)[0]


def _legacy_preservation_frontier(candidates, noise_tolerance=0.0):
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
            refresh_after_preparation = (
                "supporter_played" in allowances_consumed
                and "hand" in zones_replaced
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
            prepare_before_retreat = (
                candidate.action.identity.kind == "retreat"
                and other.swing > noise_tolerance
                and bool(opportunities_created)
                and "retreat" in preserved)
            if prepare_before_retreat:
                deferred.add(candidate.action.identity)
                break
            use_free_ability = (
                other.action.identity.kind == "ability"
                and other.swing > noise_tolerance
                and candidate.action.identity.kind == "play"
                and candidate.action.identity.kind in preserved)
            if use_free_ability:
                deferred.add(candidate.action.identity)
                break
            if not consumed:
                continue
            use_expiring_ability = (
                other.action.identity.kind == "ability"
                and candidate.action.identity.kind == "evolve"
                and other.swing > noise_tolerance)
            if (not use_expiring_ability
                    and other.swing + noise_tolerance < candidate.swing):
                continue
            if (other.action.identity.kind in consumed
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
        expected_tie_break = (() if price.prize_map is None
                              else price.prize_map.plan_rank_key())
        if candidate.policy_tie_break != expected_tie_break:
            raise AssertionError(f"candidate tie break changed: {price.action.identity}")
    legacy = legacy_choose(prices, forced=forced, configuration=configuration)
    if legacy.action.identity != choice.action.identity:
        raise AssertionError("deployed choice changed")


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


def _legacy_ranked(prices, configuration, *, include_action_opportunity=False):
    def value(price):
        return price.swing + (
            price.footprint.action_opportunity if include_action_opportunity else 0.0)

    remaining = list(enumerate(prices))
    ranked = []
    while remaining:
        best = max(value(price) for _index, price in remaining)
        tied = tuple((index, price) for index, price in remaining
                     if best - value(price) <= configuration.noise_tolerance)
        exact = all(value(price) == best for _index, price in tied)
        tied = tuple(sorted(tied, key=lambda indexed: (
            (indexed[1].prize_map.plan_rank_key()
             if exact and indexed[1].prize_map is not None else ()),
            hashlib.blake2b(
                f"{configuration.tie_seed}:{indexed[0]}".encode("utf-8"),
                digest_size=8).digest())))
        ranked.extend(price for _index, price in tied)
        tied_indices = {index for index, _price in tied}
        remaining = tuple((index, price) for index, price in remaining
                          if index not in tied_indices)
    return tuple(ranked)


__all__ = ("assert_decision_parity", "assert_runtime_parity", "legacy_choose")
