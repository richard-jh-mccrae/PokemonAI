from __future__ import annotations

from types import SimpleNamespace

from common import ActionIdentity, Deterministic, BellmanLedger
from deprecated.bellman.family_ranking import apply_family_ordering, rank_actions
from common.options import LegalAction
from deprecated.bellman.pilot_profile import PilotProfile


def _equation_profile(**values):
    enabled = {
        f"family.{family}_shadow": 1.0
        for family in ("attachment", "deployment", "evolution", "promote_retreat", "snipe")
    }
    enabled.update(values)
    return PilotProfile.resolve(global_values=enabled)


def _action(kind, index):
    return LegalAction(ActionIdentity(kind, (index,)), (index,), ((index,),), ())


class _Provider:
    def __init__(self, successors):
        self.successors = successors

    def transition(self, _state, action):
        return self.successors[action]


class _Oracle:
    @staticmethod
    def transition_ledger(_before, after, _identity):
        return after.ledger


def test_attachment_leader_near_tie_and_singleton_enter_before_distant_candidate():
    water, ignition, bench, wally = (_action("attach", index) for index in range(4))
    wally = _action("play", 4)
    successors = {
        water: Deterministic(SimpleNamespace(ledger=BellmanLedger((('board', 0.15),), ()))),
        ignition: Deterministic(SimpleNamespace(ledger=BellmanLedger((('board', 0.145),), ()))),
        bench: Deterministic(SimpleNamespace(ledger=BellmanLedger((('board', 0.02),), ()))),
    }

    ranking = rank_actions(SimpleNamespace(), (bench, wally, ignition, water),
                           _Provider(successors), _Oracle(), _equation_profile())

    rows = {candidate.action: candidate for candidate in ranking.candidates}
    assert rows[water].status == "leader"
    assert rows[ignition].status == "near_tie"
    assert rows[bench].status == "deferred"
    assert rows[wally].status == "singleton"
    assert set(ranking.ordered_actions) == {water, ignition, bench, wally}
    assert ranking.ordered_actions.index(bench) > ranking.ordered_actions.index(water)


def test_unscorable_attachment_abstains_into_first_wave():
    attachment = _action("attach", 0)
    ranking = rank_actions(SimpleNamespace(), (attachment,), _Provider({}), _Oracle(),
                           _equation_profile())

    assert ranking.candidates[0].status == "abstained"
    assert ranking.first_wave == (attachment,)


def _state(*, bench=(), active=(), opponent_bench=()):
    return SimpleNamespace(obs={"current": {"yourIndex": 0, "players": [
        {"active": list(active), "bench": list(bench), "hand": []},
        {"active": [], "bench": list(opponent_bench), "hand": []},
    ]}})


def test_every_historical_value_equation_emits_shadow_candidates():
    before = _state(active=({"id": 1, "serial": 1, "hp": 60},),
                    opponent_bench=({"id": 9, "serial": 9, "hp": 100},))
    attach, evolve, retreat, deploy, snipe = (
        _action(kind, index) for index, kind in enumerate(
            ("attach", "evolve", "retreat", "play", "card")))
    successors = {
        attach: Deterministic(SimpleNamespace(
            obs=before.obs, ledger=BellmanLedger((("energy_position", 0.2),), ()))),
        evolve: Deterministic(SimpleNamespace(
            obs=before.obs, ledger=BellmanLedger((("development", 0.3),), ()))),
        retreat: Deterministic(SimpleNamespace(
            obs=_state(active=({"id": 2, "serial": 2, "hp": 70},)).obs,
            ledger=BellmanLedger((("readiness", 0.4),), ()))),
        deploy: Deterministic(SimpleNamespace(
            obs=_state(bench=({"id": 3, "serial": 3, "hp": 70},),
                       active=({"id": 1, "serial": 1, "hp": 60},)).obs,
            ledger=BellmanLedger((("board", 0.5),), ()))),
        snipe: Deterministic(SimpleNamespace(
            obs=_state(active=({"id": 1, "serial": 1, "hp": 60},),
                       opponent_bench=({"id": 9, "serial": 9, "hp": 50},)).obs,
            ledger=BellmanLedger((("damage", 0.25), ("opponent_roles", 0.1)), ()))),
    }

    ranking = rank_actions(before, (attach, evolve, retreat, deploy, snipe),
                           _Provider(successors), _Oracle(), _equation_profile())

    rows = {candidate.action: candidate for candidate in ranking.candidates}
    assert {rows[action].family for action in successors} == {
        "attachment", "evolution", "promote_retreat", "deployment", "snipe",
    }
    assert all(rows[action].shadow for action in successors)
    assert all(rows[action].score is not None for action in successors)


def test_each_shadow_gate_and_coefficient_is_independent():
    evolve = _action("evolve", 0)
    before = _state()
    provider = _Provider({evolve: Deterministic(SimpleNamespace(
        obs=before.obs, ledger=BellmanLedger((("development", 0.5),), ())))})

    disabled = rank_actions(
        before, (evolve,), provider, _Oracle(),
        PilotProfile.resolve(global_values={"family.evolution_shadow": 0.0}),
    ).candidates[0]
    tuned = rank_actions(
        before, (evolve,), provider, _Oracle(),
        _equation_profile(**{"evolution.deploy_weight": 2.0}),
    ).candidates[0]

    assert disabled.status == "shadow_disabled"
    assert disabled.score is None
    assert tuned.score == 1.0


def test_shadow_ordering_never_changes_runtime_order_until_its_family_gate_is_on():
    low, play, high = _action("attach", 0), _action("play", 1), _action("attach", 2)
    successors = {
        low: Deterministic(SimpleNamespace(ledger=BellmanLedger((("board", 0.1),), ()))),
        high: Deterministic(SimpleNamespace(ledger=BellmanLedger((("board", 0.9),), ()))),
    }
    actions = (low, play, high)
    base = _equation_profile()
    ranking = rank_actions(SimpleNamespace(), actions, _Provider(successors), _Oracle(), base)

    assert apply_family_ordering(actions, ranking, base) == actions
    enabled = _equation_profile(**{"family.attachment_ordering": 1.0})
    assert apply_family_ordering(actions, ranking, enabled) == (high, play, low)
