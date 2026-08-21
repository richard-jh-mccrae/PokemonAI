from __future__ import annotations

from collections import Counter
from math import comb

import pytest

from common import (
    ActionIdentity,
    Actor,
    Chance,
    Deterministic,
    BellmanLedger,
    Refresh,
    RevealChoice,
    Terminal,
)
from deprecated.bellman.state import DecisionState
from deprecated.bellman import ReferenceSolver
from common.algebra import WeightedEdge
from common.information import OutcomeGroup, draw_outcomes, hypergeometric_classes
from deprecated.bellman.belief import BellmanDeckProfile, opponent_belief
from common.options import LegalAction
from common.native_engine import _own_hidden_zones, _stratified_order
from deprecated.bellman.value import CardFacts, Potential, ValueOracle, ValueRegistry


STARYU, CINDERACE, BOSS, WATER, LILLIE = 1030, 666, 1182, 3, 1227
DECK = (STARYU,) * 4 + (CINDERACE,) * 4 + (BOSS,) + (WATER,) * 9 + (LILLIE,)
PROFILE = BellmanDeckProfile(lines=((STARYU, 1031),))


def _board(*, node="root", hand=(), energy=0, bench=(), value=0.0):
    active = {"id": CINDERACE, "serial": 19, "playerIndex": 0, "hp": 160,
              "maxHp": 160, "energyCards": [
                  {"id": WATER, "serial": 3 + i, "playerIndex": 0} for i in range(energy)],
              "energies": [3] * energy, "preEvolution": [], "tools": []}
    return {"node": node, "current": {"yourIndex": 0, "board": value,
            "supporterPlayed": False, "energyAttached": bool(energy), "retreated": False,
            "stadiumPlayed": False, "players": [
                {"hand": [{"id": cid, "serial": 10_000 + cid, "playerIndex": 0}
                          for cid in hand], "active": [active],
                 "bench": list(bench), "benchMax": 5, "discard": [], "prize": [None] * 6},
                {"hand": None, "handCount": 0, "active": [], "bench": [], "discard": [],
                 "prize": [None] * 6},
            ]}, "select": {"context": 0, "option": []}}


def _state(**kwargs):
    return DecisionState.from_observation(_board(**kwargs), deck=DECK, deck_name="mega_starmie")


def _action(kind, index):
    return LegalAction(ActionIdentity(kind, (kind, index)), (index,), ((index,),), ())


class Graph:
    def __init__(self, actions, transitions):
        self.a, self.t = actions, transitions

    def actions(self, state):
        return self.a[state.obs["node"]]

    def transition(self, state, action):
        return self.t[(state.obs["node"], action.identity.kind)]

    def actor(self, state):
        return Actor.OURS


def test_deck_profile_contains_declarations_without_derived_tactical_needs():
    assert PROFILE.lines == ((STARYU, 1031),)
    assert PROFILE.line_bases == {STARYU}
    assert PROFILE.line_tops == {1031}


def test_hypergeometric_classes_are_mutually_exclusive_with_explicit_whiff():
    group = OutcomeGroup("line-base", (STARYU,))
    pool = [STARYU] * 4 + [999] * 16
    outcomes = hypergeometric_classes(pool, 6, (group,))
    assert sum(outcome.probability for outcome in outcomes) == pytest.approx(1.0)
    whiff = next(outcome for outcome in outcomes if outcome.counts == (0,))
    assert whiff.probability == pytest.approx(comb(16, 6) / comb(20, 6))
    assert all(outcome.remainder + sum(outcome.counts) == 6 for outcome in outcomes)


def test_wide_draw_support_uses_mass_strata_not_seeded_rare_outcomes():
    pool = [card_id for card_id in range(100, 110) for _copy in range(5)] + [999] * 3
    outcomes = draw_outcomes(pool, 8, max_outcomes=16)
    expected_rare_count = 8 * 3 / len(pool)
    represented_rare_count = sum(
        outcome.probability * outcome.card_ids.count(999) for outcome in outcomes)

    assert sum(outcome.probability for outcome in outcomes) == pytest.approx(1.0)
    assert represented_rare_count == pytest.approx(expected_rare_count, abs=1 / 16)
    assert all(not outcome.exact for outcome in outcomes)


def test_native_single_world_hidden_zone_is_not_grouped_by_numeric_identity():
    """One deployed quadrature world must represent mixture, not arbitrary card-id ordering."""
    grouped = (101,) * 12 + (202,) * 8 + (303,) * 4 + (404,)

    ordered = _stratified_order(grouped, world_index=0, world_count=1)

    assert Counter(ordered) == Counter(grouped)
    assert ordered != list(grouped)
    assert len(set(ordered[:7])) > 1
    assert len(set(ordered[-7:])) > 1


def test_native_belief_worlds_use_distinct_equal_strata_without_changing_mass():
    cards = (101,) * 12 + (202,) * 8 + (303,) * 4 + (404,)
    worlds = [_stratified_order(cards, index, 4) for index in range(4)]

    assert len({tuple(world) for world in worlds}) == 4
    assert all(Counter(world) == Counter(cards) for world in worlds)


def test_unknown_prizes_are_partitioned_after_balancing_the_whole_hidden_pool():
    root = type("Root", (), {
        "deck_counts": ((101, 5), (999, 5)),
        "prize_counts": (),
        "deck": (101,) * 5 + (999,) * 5,
    })()

    deck, prizes = _own_hidden_zones(
        root, {"deckCount": 4, "prize": [None] * 6}, world_index=0, world_count=1)

    assert len(deck) == 4
    assert len(prizes) == 6
    assert Counter(deck + prizes) == Counter(root.deck)
    assert set(deck) == {101, 999}


def test_scouting_adapter_conserves_unknown_mass_and_never_selects():
    belief = opponent_belief(_board(), candidates=(
        {"name": "alakazam", "probability": 0.65},
        {"name": "dragapult", "probability": 0.20},
    ), properties={"opp_tempo": "midrange"})
    assert belief.unknown_mass == pytest.approx(0.15)
    assert belief.properties == (("opp_tempo", "midrange"),)


def test_60hp_fixture_attaches_then_takes_lillie_expectation_and_replans():
    registry = ValueRegistry(
        roles={STARYU: ("primary_attacker",)},
        functions={BOSS: ("gust",), LILLIE: ("draw",), WATER: ()},
        facts={cid: CardFacts(typed_basic_energy=cid == WATER)
               for cid in (STARYU, BOSS, WATER, LILLIE)},
    )
    oracle = ValueOracle(registry, lambda obs: Potential(
        float(obs["current"].get("board", 0.0)),
        (("board", float(obs["current"].get("board", 0.0))),)))
    root = _state(node="root", hand=(BOSS, WATER, LILLIE), value=0.0)
    attached = _state(node="attached", hand=(BOSS, LILLIE), energy=1, value=0.08)
    hit = _state(node="hit", hand=(STARYU,), energy=1, value=0.50)
    whiff = _state(node="whiff", hand=(), energy=1, value=0.05)
    direct_hit = _state(node="direct_hit", hand=(STARYU,), value=0.22)
    direct_whiff = _state(node="direct_whiff", hand=(), value=0.0)
    bossed = _state(node="bossed", hand=(WATER, LILLIE), value=0.06)
    attach, boss, lillie, end = (_action("attach", 0), _action("boss", 1),
                                 _action("play", 2), _action("end", 3))
    graph = Graph(
        {"root": (attach, boss, lillie, end), "attached": (lillie, end),
         "hit": (end,), "whiff": (end,), "direct_hit": (end,),
         "direct_whiff": (end,), "bossed": (end,)},
        {("root", "attach"): Deterministic(attached),
         ("root", "boss"): Terminal(bossed, "Turbo Flare KO"),
         ("root", "play"): Chance((WeightedEdge(0.5, "Staryu", Deterministic(direct_hit)),
                                      WeightedEdge(0.5, "whiff", Deterministic(direct_whiff)))),
         ("attached", "play"): Chance((WeightedEdge(0.5, "Staryu", Deterministic(hit)),
                                          WeightedEdge(0.5, "whiff", Deterministic(whiff))))},
    )
    decision = ReferenceSolver(graph, oracle).decide(root)
    assert decision.action.kind == "attach"
    attached_decision = ReferenceSolver(graph, oracle).decide(attached)
    assert attached_decision.action.kind == "play"
    assert attached_decision.diagnostics["root"].alternatives


@pytest.mark.parametrize(("card_id", "node_type"), [
    (LILLIE, Refresh), (1120, Chance), (1122, RevealChoice), (1223, Refresh),
])
def test_real_engine_owns_resolution_and_hidden_information_has_an_explicit_boundary(
        card_id, node_type):
    from pathlib import Path
    from deprecated.bellman.providers import BellmanCgpyProvider as CgpyTransitionProvider
    from train.blunder.store import load_corrections

    repo = Path(__file__).resolve().parents[3]
    deck = tuple(int(line) for line in (repo / "src" / "agents" / "mega_starmie" /
                                        "deck.csv").read_text().split())
    from bellman_helpers import runtime
    from deprecated.bellman.tags import CardFunctions
    from deprecated.bellman.effects import CardEffects
    tags = CardFunctions.load()
    stats = runtime().stats
    registry = ValueRegistry(
        roles={CINDERACE: ("accel_source",)},
        functions={known: tuple(tags.tags(known)) for known in set(deck)},
        facts={CINDERACE: CardFacts(pokemon=True)},
        lines=((STARYU, 1031),),
    )
    found = None
    for correction in load_corrections(repo / "data" / "corrections"):
        if correction.agent != "mega_starmie" or correction.obs is None:
            continue
        if ((correction.obs.get("select") or {}).get("context") != 0):
            continue
        state = DecisionState.from_observation(correction.obs, deck=deck,
                                               deck_name="mega_starmie")
        provider = CgpyTransitionProvider(
            state, registry=registry, effects=CardEffects.load(), stats=stats)
        if not provider.available:
            continue
        for action in provider.actions(state):
            if action.identity.kind != "play":
                continue
            option = correction.obs["select"]["option"][action.selection[0]]
            hand = correction.obs["current"]["players"][state.root_seat].get("hand") or ()
            played = int(hand[int(option["index"])]["id"])
            if played == card_id:
                node = provider.transition(state, action)
                if isinstance(node, node_type):
                    found = node
                    break
        if found is not None:
            break
    assert found is not None, f"no reconstructable {card_id} information play"
    if isinstance(found, Chance):
        assert sum(edge.probability for edge in found.children) == pytest.approx(1.0)
    if card_id == 1122:
        assert any(len(outcome.choices) > 2 for outcome in found.outcomes)
    if card_id == 1120:
        assert {edge.label for edge in found.children} == {"heads", "tails"}
    if isinstance(found, Refresh):
        assert found.draws
        assert not hasattr(found, "state")
