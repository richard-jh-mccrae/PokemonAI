from __future__ import annotations

from collections import Counter
from math import comb

import pytest

from common.bellman import (
    ActionIdentity, Actor, Chance, DecisionState, Deterministic, Ledger, ReferenceSolver, Terminal,
)
from common.bellman.algebra import WeightedEdge
from common.bellman.information import BellmanDeckProfile, CausalNeeds, hypergeometric_classes, opponent_belief
from common.bellman.options import LegalAction
from common.bellman.value import CardFacts, Potential, ValueOracle, ValueRegistry


STARYU, CINDERACE, BOSS, WATER, LILLIE = 1030, 666, 1182, 3, 1227
DECK = (STARYU,) * 4 + (CINDERACE,) * 4 + (BOSS,) + (WATER,) * 9 + (LILLIE,)
PROFILE = BellmanDeckProfile(lines=((STARYU, 1031),), accelerators=(CINDERACE,),
                             reusable_energy=(WATER,))


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


def test_causal_turbo_need_transfers_as_dependency_not_tactic():
    obs = _board(hand=(BOSS, WATER, LILLIE))
    needs = CausalNeeds(profile=PROFILE).derive(obs, deck_counts=Counter({STARYU: 4, WATER: 8}))
    assert [(need.key, need.card_ids) for need in needs] == [
        ("accelerator-recipient", (STARYU,)), ("typed-attack-energy", (WATER,))]
    benched = ({"id": STARYU, "serial": 22, "playerIndex": 0},)
    needs = CausalNeeds(profile=PROFILE).derive(_board(bench=benched),
                                 deck_counts=Counter({STARYU: 3, WATER: 8}))
    assert "accelerator-recipient" not in {need.key for need in needs}


def test_hypergeometric_classes_are_mutually_exclusive_with_explicit_whiff():
    need = CausalNeeds(profile=PROFILE).derive(_board(), deck_counts=Counter({STARYU: 4}))[0]
    pool = [STARYU] * 4 + [999] * 16
    outcomes = hypergeometric_classes(pool, 6, (need,))
    assert sum(outcome.probability for outcome in outcomes) == pytest.approx(1.0)
    whiff = next(outcome for outcome in outcomes if outcome.counts == (0,))
    assert whiff.probability == pytest.approx(comb(16, 6) / comb(20, 6))
    assert all(outcome.remainder + sum(outcome.counts) == 6 for outcome in outcomes)


def test_scouting_adapter_conserves_unknown_mass_and_never_selects():
    belief = opponent_belief(_board(), candidates=(
        {"name": "alakazam", "probability": 0.65},
        {"name": "dragapult", "probability": 0.20},
    ), properties={"opp_tempo": "midrange"})
    assert belief.unknown_mass == pytest.approx(0.15)
    assert belief.properties == (("opp_tempo", "midrange"),)


def test_60hp_fixture_attaches_then_takes_lillie_expectation_and_replans():
    registry = ValueRegistry(
        roles={STARYU: ("win_condition_base",)},
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


@pytest.mark.parametrize("card_id", [LILLIE, 1120, 1122, 1223])
def test_real_engine_information_and_coin_plays_become_chance_nodes(card_id):
    from pathlib import Path
    from common.bellman.engine import CgpyTransitionProvider
    from train.blunder.store import load_corrections

    repo = Path(__file__).resolve().parents[2]
    deck = tuple(int(line) for line in (repo / "src" / "agents" / "mega_starmie" /
                                        "deck.csv").read_text().split())
    from common.cards import CardFunctions
    tags = CardFunctions.load()
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
        provider = CgpyTransitionProvider(state, registry=registry)
        if not provider.available:
            continue
        for action in provider.actions(state):
            played, _serial = provider._played_card_id(provider._engines[state.semantic_key], action)
            if played == card_id:
                node = provider.transition(state, action)
                if isinstance(node, Chance):
                    found = node
                    break
        if found is not None:
            break
    assert found is not None, f"no reconstructable {card_id} chance play"
    assert sum(edge.probability for edge in found.children) == pytest.approx(1.0)
    if card_id == 1120:
        assert {edge.label for edge in found.children} == {"heads", "tails"}
