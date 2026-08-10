"""Issue #495 weighted next-attach NeedGraph assignment."""
from __future__ import annotations

from common import needs


def test_equal_edges_are_bit_identical_to_legacy_assignment():
    slots = [needs.Slot("fund_attack", 8.0, 0, "a"),
             needs.Slot("line", 5.0, 1, "b")]
    eligibility = [{0, 1}, {0}]
    resupply = [0.25, 0.5]
    edges = [{0: 8.0, 1: 5.0}, {0: 8.0}]
    assert needs.assignment_value(slots, eligibility, resupply) == \
        needs.assignment_value(slots, eligibility, resupply, edge_values=edges)


def test_weighted_edge_selects_best_fit_without_two_demands():
    slot = needs.Slot("fund_attack", 12.0, 0, "fund:active:next_attach")
    graph = needs.NeedGraph(
        (slot,),
        ((needs.CoverageEdge(0, 12.0),), (needs.CoverageEdge(0, 3.0),)))
    resolution = needs.Resolution(graph=graph, resupply=(0.0,), hand_ids=(3, 6))
    assert len(resolution.slots) == 1
    assert resolution.set_keep((0,)) == 9.0
    assert resolution.set_keep((1,)) == 0.0
    assert resolution.set_keep((0, 1)) == 12.0


def test_one_card_cannot_cover_two_body_slots():
    slots = (needs.Slot("fund_attack", 10.0, 0, "fund:active:next_attach"),
             needs.Slot("fund_attack", 9.0, 0, "fund:bench.0:next_attach"))
    graph = needs.NeedGraph(slots, ((needs.CoverageEdge(0, 10.0),
                                    needs.CoverageEdge(1, 9.0)),))
    resolution = needs.Resolution(graph=graph, resupply=(0.0, 0.0), hand_ids=(3,))
    assert resolution.split() == (0.0, 10.0)


def test_unknown_funding_edges_survive_resolution():
    graph = needs.NeedGraph((), ((),), ("fund:active:card:17:provision",))
    resolution = needs.Resolution(graph=graph, resupply=(), hand_ids=(17,))
    assert resolution.unknowns == graph.unknowns
