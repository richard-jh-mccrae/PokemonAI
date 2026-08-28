from collections import Counter

from cgpy.schema import OptionType, SelectContext
from common.decision import correction_compute_profile
from common.ledger import evaluate
from common.observation import ObservationStateBuilder

from real_engine_helpers import (
    BodySpec, decide_option, lock_main_allowances, observation, option_card_id, scenario,
)


ACCURACY_COMPUTE = correction_compute_profile()


def _scenario(agent, **kwargs):
    return scenario(agent, compute_configuration=ACCURACY_COMPUTE, **kwargs)


def _chosen_card_ids(engine, decision):
    options = engine.gs.pending.options
    return tuple(option_card_id(engine, options[index]) for index in decision.chosen)


def test_attack_is_priced_against_real_engine_end_after_phase_advance():
    engine, agent = _scenario(
        "mega_starmie", me_active=BodySpec((1030, 1031), energies=(3,)),
        them_active=BodySpec((1030, 1031)))
    lock_main_allowances(engine)

    decision = agent.decide(observation(engine))
    options = engine.gs.pending.options
    chosen = options[decision.chosen[0]]
    candidates = decision.decision_result.roster.candidates
    attack = next(row for row in candidates if row.action.identity.kind == "attack")
    end = next(row for row in candidates if row.action.identity.kind == "end")

    assert chosen["type"] == int(OptionType.ATTACK)
    assert attack.disposition.value == "ends_turn"
    assert attack.delta.total > end.delta.total == 0.0


def test_ultra_ball_prices_play_two_discards_and_fetch_as_one_real_engine_chain():
    engine, agent = _scenario(
        "dragapult_ex", me_active=BodySpec((119,)), me_hand=(1121, 2, 5, 121),
        me_top=(121,), them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.PLAY)
    assert engine.gs.pending.context == int(SelectContext.DISCARD)

    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert len(decision.chosen) == 2
    assert set(_chosen_card_ids(engine, decision)) == {2, 5}
    engine.step(list(decision.chosen))
    assert engine.gs.pending.context == int(SelectContext.TO_HAND)

    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert _chosen_card_ids(engine, decision) == (120,)
    engine.step(list(decision.chosen))
    assert 120 in tuple(engine.gs.card_id(serial) for serial in engine.gs.players[0].hand)


def test_retreat_prices_payment_and_best_promotion_as_one_real_engine_chain():
    engine, agent = _scenario(
        "dragapult_ex", me_active=BodySpec((119,), energies=(2,), hp=20),
        me_bench=(BodySpec((119, 120, 121), energies=(2, 5)), BodySpec((119,))),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.RETREAT)
    assert engine.gs.pending.context == int(SelectContext.DISCARD_ENERGY)
    decision, _option = decide_option(engine, agent)
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert engine.gs.pending.context == int(SelectContext.SWITCH)
    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert _chosen_card_ids(engine, decision) == (121,)
    engine.step(list(decision.chosen))
    assert engine.gs.card_id(engine.gs.players[0].active.top) == 121


def test_poffin_uses_both_real_engine_bench_selections():
    engine, agent = _scenario(
        "dragapult_ex", me_active=BodySpec((119,)), me_hand=(1086,),
        me_top=(119, 119), them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.PLAY)
    assert engine.gs.pending.context == int(SelectContext.TO_BENCH)
    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert len(decision.chosen) == 2
    engine.step(list(decision.chosen))
    assert len(engine.gs.players[0].bench) == 2


def test_pokegear_prices_play_reveal_and_fetch_as_one_real_engine_chain():
    engine, agent = _scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1122,),
        me_top=(1227, 3, 1223, 3, 1030, 3),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.PLAY)
    assert engine.gs.pending.context == int(SelectContext.TO_HAND)
    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert _chosen_card_ids(engine, decision) == (1227,)
    engine.step(list(decision.chosen))
    assert 1227 in tuple(engine.gs.card_id(serial) for serial in engine.gs.players[0].hand)


def test_drakloak_draws_before_evolving_that_body_to_dragapult():
    engine, agent = _scenario(
        "dragapult_ex", me_active=BodySpec((119, 120), energies=(2, 5)),
        me_hand=(121,), me_top=(1227, 7),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.ABILITY)
    assert option_card_id(engine, option) == 120
    decide_option(engine, agent)

    decision = agent.decide(observation(engine))
    option = engine.gs.pending.options[decision.chosen[0]]
    assert option["type"] == int(OptionType.EVOLVE)
    assert option["inPlayArea"] == 4
    assert option["inPlayIndex"] == 0


def _aura_jab_recipients(opponent_prizes):
    engine, agent = _scenario(
        "mega_lucario", me_active=BodySpec((677, 678), energies=(6,)),
        me_bench=(BodySpec((673, 674)), BodySpec((673, 674)), BodySpec((677,))),
        me_discard=(6, 6, 6), them_active=BodySpec((677, 678), energies=(6, 6)),
        them_prizes=opponent_prizes)
    lock_main_allowances(engine)
    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.ATTACK)
    assert option["attackId"] == 982
    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    selected_count = len(decision.chosen)
    engine.step(list(decision.chosen))
    recipients = []
    for _ in range(selected_count):
        decision = agent.decide(observation(engine))
        assert decision.decision_result.search.stop_reason == "cached_continuation"
        recipients.extend(_chosen_card_ids(engine, decision))
        engine.step(list(decision.chosen))
    return tuple(recipients)


def test_aura_jab_funds_hariyama_while_opponent_has_five_prizes():
    recipients = _aura_jab_recipients(5)
    assert len(recipients) == 3
    assert set(recipients) == {674}


def test_aura_jab_funds_riolu_or_lucario_when_opponent_has_four_prizes():
    recipients = _aura_jab_recipients(4)
    assert recipients
    assert set(recipients) <= {677, 678}


def test_three_prize_ko_is_terminal_liability_when_opponent_has_three_prizes():
    def valuation(opponent_prizes):
        engine, agent = _scenario(
            "mega_lucario", me_active=BodySpec((677, 678), energies=(6,), hp=270),
            me_bench=(BodySpec((677,)),),
            them_active=BodySpec((677, 678), energies=(6, 6)),
            them_prizes=opponent_prizes)
        board = ObservationStateBuilder(agent.deck).root(observation(engine))
        return evaluate(board, agent.ledger.ctx)

    terminal = valuation(3)
    safe_route = valuation(4)
    terminal_value = sum(
        row.value for row in terminal.contributions
        if row.feature == "active.terminal_liability")
    safe_value = sum(
        row.value for row in safe_route.contributions
        if row.feature == "active.terminal_liability")
    assert terminal_value == -100.0
    assert safe_value == 0.0


def _phantom_dive_targets(bench, *, stopped_budget=None):
    engine, agent = _scenario(
        "dragapult_ex", me_active=BodySpec((119, 120, 121), energies=(2, 5)),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)), them_bench=bench)
    lock_main_allowances(engine)
    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.ATTACK)
    assert option["attackId"] == 154
    if stopped_budget is not None:
        stopped_budget()
    initial = {
        target.top: (engine.gs.card_id(target.top), target.hp)
        for target in engine.gs.players[1].bench
    }
    targets = []
    for _ in range(6):
        decision = agent.decide(observation(engine))
        assert decision.decision_result.search.stop_reason == "cached_continuation"
        option = engine.gs.pending.options[decision.chosen[0]]
        target = engine.gs.players[1].bench[option["index"]]
        assert target.hp > 0
        targets.append(initial[target.top])
        engine.step(list(decision.chosen))
    return tuple(targets)


def test_jetting_blow_reuses_its_cached_best_snipe_target():
    engine, agent = _scenario(
        "mega_starmie", me_active=BodySpec((1030, 1031), energies=(3,)),
        them_active=BodySpec((1030, 1031)),
        them_bench=(BodySpec((1030,), hp=40), BodySpec((1030, 1031), hp=200)))
    lock_main_allowances(engine)

    _decision, option = decide_option(engine, agent)
    assert option["type"] == int(OptionType.ATTACK)
    assert option["attackId"] == 1487
    assert engine.gs.pending.context == int(SelectContext.DAMAGE)

    decision = agent.decide(observation(engine))
    assert decision.decision_result.search.stop_reason == "cached_continuation"
    assert _chosen_card_ids(engine, decision) == (1030,)


def test_phantom_dive_never_spends_a_counter_on_an_already_ko_bench_target():
    targets = _phantom_dive_targets((
        BodySpec((119, 120, 121), hp=20), BodySpec((119,), hp=10),
        BodySpec((119,), hp=70)))
    assert Counter(targets) == Counter({(121, 20): 2, (119, 10): 1, (119, 70): 3})


def test_phantom_dive_target_priorities_do_not_depend_on_bench_order():
    original = _phantom_dive_targets((
        BodySpec((119, 120, 121), hp=20), BodySpec((119,), hp=10),
        BodySpec((119,), hp=70)))
    permuted = _phantom_dive_targets((
        BodySpec((119,), hp=70), BodySpec((119, 120, 121), hp=20),
        BodySpec((119,), hp=10)))
    assert Counter(original) == Counter(permuted)


def test_phantom_dive_avoids_ko_targets_after_search_budget_exhaustion(monkeypatch):
    class StoppedBudget:
        stop_reason = "time_budget"
        frontier = []
        nodes = 0

    targets = _phantom_dive_targets(
        (BodySpec((119, 120, 121), hp=20), BodySpec((119,), hp=10),
         BodySpec((119,), hp=70)),
        stopped_budget=lambda: monkeypatch.setattr(
            "common.ledger.search.BudgetController", lambda _configuration: StoppedBudget()))
    assert Counter(targets) == Counter({(121, 20): 2, (119, 10): 1, (119, 70): 3})
