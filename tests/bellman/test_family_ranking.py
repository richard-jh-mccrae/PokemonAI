from __future__ import annotations

from types import SimpleNamespace

from common import ActionIdentity, Deterministic, Ledger
from common.family_ranking import rank_actions
from common.options import LegalAction
from common.pilot_profile import PilotProfile


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
        water: Deterministic(SimpleNamespace(ledger=Ledger((('board', 0.15),), ()))),
        ignition: Deterministic(SimpleNamespace(ledger=Ledger((('board', 0.145),), ()))),
        bench: Deterministic(SimpleNamespace(ledger=Ledger((('board', 0.02),), ()))),
    }

    ranking = rank_actions(SimpleNamespace(), (bench, wally, ignition, water),
                           _Provider(successors), _Oracle(), PilotProfile.resolve())

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
                           PilotProfile.resolve())

    assert ranking.candidates[0].status == "abstained"
    assert ranking.first_wave == (attachment,)
