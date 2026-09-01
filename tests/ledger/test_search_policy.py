from types import SimpleNamespace

from common.decision import OpportunityRef
from common.ledger.search import preservation_frontier


def candidate(kind, value, *, preserved=(), consumed=(), allowances=(), zones=(), created=(),
              outputs=(), opportunity=0.0, policy_features=(), realized=0.0,
              discard_spend=0.0, recovery=False, executed=None):
    return SimpleNamespace(
        action=SimpleNamespace(identity=SimpleNamespace(kind=kind)),
        delta=SimpleNamespace(total=value, components=()),
        continuation=SimpleNamespace(
            opportunities_preserved=tuple(preserved),
            opportunities_consumed=tuple(consumed),
            allowances_consumed=tuple(allowances),
            zones_replaced=tuple(zones),
            immediately_usable_outputs=tuple(outputs),
            opportunities_created=tuple(created),
            executed_opportunity=executed,
            action_opportunity=opportunity,
            policy_components=(
                *(SimpleNamespace(key=feature, value=0.0, provenance=())
                  for feature in policy_features),
                *((SimpleNamespace(
                    key="option.energy", value=realized,
                    provenance=("action.realized_portfolio",
                                *(('action.recovery',) if recovery else ()))),)
                  if realized else ()),
                *((SimpleNamespace(
                    key="option.search", value=-discard_spend,
                    provenance=("action.compound_discard_spend",)),)
                  if discard_spend else ()))))


def test_preservation_cannot_hide_a_more_valuable_resolved_compound_action():
    fetch = candidate("fetch", 1.2, consumed=("draw",))
    draw = candidate("draw", 1.0, preserved=("fetch",))

    assert preservation_frontier((fetch, draw)) == (fetch, draw)


def test_mutually_exclusive_targets_keep_the_best_policy_value():
    bench = candidate("attach", 0.35, consumed=("attach",))
    active = candidate(
        "attach", 0.02, consumed=("attach",), opportunity=0.53,
        policy_features=("action.survival_tool_target",))

    assert preservation_frontier((bench, active)) == (active,)


def test_preservation_defers_a_lower_value_action_when_order_keeps_both():
    fetch = candidate("fetch", 1.0, consumed=("draw",))
    draw = candidate("draw", 1.2, preserved=("fetch",))

    assert preservation_frontier((fetch, draw)) == (draw,)


def test_positive_ability_is_used_before_evolving_away_its_source():
    evolve = candidate("evolve", 1.2, consumed=("ability",))
    ability = candidate("ability", 0.1, preserved=("evolve",))

    assert preservation_frontier((evolve, ability)) == (ability,)


def test_another_body_ability_does_not_hide_the_source_evolution_consumes():
    first = OpportunityRef("ability", "seat:0:bench:0")
    second = OpportunityRef("ability", "seat:0:bench:1")
    evolve = candidate("evolve", 1.2, consumed=(first,), created=(second,))
    other_ability = candidate(
        "ability", 0.1, preserved=("evolve",), consumed=(second,))
    source_ability = candidate(
        "ability", 0.1, preserved=("evolve",), consumed=(first,))

    assert preservation_frontier((evolve, other_ability)) == (
        evolve, other_ability)
    assert preservation_frontier((evolve, source_ability)) == (source_ability,)


def test_generic_replacement_does_not_create_a_preservation_cycle():
    evolve = candidate(
        "evolve", 1.2, consumed=("attach",), created=("attach",),
        preserved=("play",))
    attach = candidate("attach", 0.1, preserved=("evolve",))

    assert preservation_frontier((evolve, attach)) == (evolve, attach)


def test_sourced_attachment_is_not_replaced_by_another_body_source():
    first = OpportunityRef("attach", "seat:0:body:1")
    second = OpportunityRef("attach", "seat:0:body:2")
    evolve = candidate(
        "evolve", 1.2, consumed=(first,), created=(second,),
        preserved=("attach",))
    attach = candidate(
        "attach", 1.3, consumed=(first,), preserved=("evolve",), executed=first)

    assert preservation_frontier((evolve, attach)) == (attach,)


def test_preserved_ability_does_not_delay_a_more_valuable_search_play():
    search = candidate("play", 0.5, preserved=("ability",))
    ability = candidate("ability", 0.2, preserved=("play",))

    assert preservation_frontier((search, ability)) == (search, ability)


def test_live_attachment_precedes_optional_body_that_preserves_attach():
    basic = candidate(
        "play", 0.4, preserved=("attach",), created=("attach",),
        outputs=("in_play",))
    attach = candidate(
        "attach", -0.2, preserved=("play",), consumed=("attach",),
        created=("retreat",))

    assert preservation_frontier((basic, attach)) == (attach,)


def test_equivalent_retreat_attachment_spares_the_scarcer_energy_source():
    generic = candidate(
        "attach", -0.3, preserved=("play",), consumed=("attach",),
        created=("retreat",))
    scarce = candidate(
        "attach", 0.1, preserved=("play",), consumed=("attach",),
        created=("retreat",), realized=0.2)

    assert preservation_frontier((generic, scarce)) == (generic,)


def test_live_recovery_precedes_a_destructive_search_play():
    destructive = candidate(
        "play", 0.2, preserved=("play",), discard_spend=0.1)
    recovery = candidate(
        "play", -0.1, preserved=("play",), realized=0.1, recovery=True)

    assert preservation_frontier((destructive, recovery)) == (recovery,)


def test_plain_realized_play_does_not_preempt_a_better_destructive_search():
    destructive = candidate(
        "play", 0.2, preserved=("play",), discard_spend=0.1)
    transient = candidate(
        "play", 0.1, preserved=("play",), realized=0.1)

    assert preservation_frontier((destructive, transient)) == (
        destructive, transient)


def test_hand_refresh_waits_for_positive_preparation_without_coarse_consumption():
    supporter = candidate(
        "play", 3.0, allowances=("supporter_played",), zones=("hand",),
        outputs=("hand",))
    evolve = candidate(
        "evolve", 0.2, preserved=("play",), created=("ability",))

    assert preservation_frontier((supporter, evolve)) == (evolve,)


def test_hand_refresh_waits_for_a_durable_body_even_when_body_delta_is_negative():
    supporter = candidate(
        "play", 0.2, allowances=("supporter_played",), zones=("hand",))
    basic = candidate(
        "play", -0.15, preserved=("play",), outputs=("in_play",))

    assert preservation_frontier((supporter, basic)) == (basic,)


def test_transient_play_waits_for_a_durable_body_that_preserves_play():
    item = candidate("play", 0.01)
    basic = candidate(
        "play", -0.15, preserved=("play",), outputs=("in_play",))

    assert preservation_frontier((item, basic)) == (basic,)


def test_unlinked_basic_waits_for_a_hand_line_parent_before_refresh():
    unlinked = candidate(
        "play", -0.2, preserved=("play",), outputs=("in_play",))
    parent = candidate(
        "play", -0.4, preserved=("play",), outputs=("in_play",),
        created=("future_evolve",))

    assert preservation_frontier((unlinked, parent)) == (parent,)


def test_retreat_waits_for_positive_preparation_that_preserves_retreat():
    retreat = candidate("retreat", 1.4)
    evolve = candidate(
        "evolve", 0.5, preserved=("retreat",), created=("ability",))

    assert preservation_frontier((retreat, evolve)) == (evolve,)


def test_retreat_waits_for_attack_setup_even_when_static_value_is_negative():
    retreat = candidate("retreat", 1.4)
    attach = candidate(
        "attach", -0.5, preserved=("retreat",), created=("attack",))

    assert preservation_frontier((retreat, attach)) == (attach,)
