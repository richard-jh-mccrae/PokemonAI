from __future__ import annotations

from pathlib import Path

import pytest

from cgpy.engine import Engine
from cgpy.options import pose_main
from cgpy.rng import SeededRng
from cgpy.search import export_token
from cgpy.state import PokemonInPlay

from common.bellman.engine import _own_prize_export
from common.bellman import (
    DecisionState, MegaStarmiePotential, ProductionLimits, ProductionSolver, ReferenceSolver,
    ValueOracle, ValueRegistry,
)
from common.bellman.engine import CgpyTransitionProvider
from train.blunder.store import load_corrections
from train.tune import _build_pilot


REPO = Path(__file__).resolve().parents[2]
DECK = [int(line) for line in (REPO / "src" / "agents" / "mega_starmie" /
                               "deck.csv").read_text().split()]
CINDERACE, STARYU, BOSS, WATER, LILLIE = 666, 1030, 1182, 3, 1227


def _fixture(hp):
    engine, _seat, _error = Engine.start(DECK, DECK, rng=SeededRng(4))
    gs = engine.gs
    for board in gs.players:
        board.deck = []
        board.hand = []
        board.discard = []
        board.prize = []
        board.active = None
        board.bench = []
    used = set()

    def take(seat, card_id):
        serial = next(serial for serial, card in gs.cards.items()
                      if card.owner == seat and card.card_id == card_id and serial not in used)
        used.add(serial)
        return serial

    gs.players[0].active = PokemonInPlay(
        stack=[take(0, CINDERACE)], hp=160, max_hp=160, entered_turn=1)
    gs.players[0].hand = [take(0, BOSS), take(0, WATER), take(0, LILLIE)]
    gs.players[1].active = PokemonInPlay(
        stack=[take(1, CINDERACE)], hp=160, max_hp=160, entered_turn=1)
    gs.players[1].bench = [PokemonInPlay(
        stack=[take(1, STARYU)], hp=hp, max_hp=70, entered_turn=1)]
    for seat in (0, 1):
        remaining = [serial for serial, card in gs.cards.items()
                     if card.owner == seat and serial not in used]
        safe_prizes = [serial for serial in remaining
                       if gs.card_id(serial) not in (STARYU, 1031, WATER)][:6]
        gs.players[seat].prize = safe_prizes
        gs.players[seat].deck = [serial for serial in remaining if serial not in safe_prizes]
    gs.turn = 3
    gs.first_player = 1
    gs.phase = "TURN"
    gs.phase_data = {"seat": 0}
    gs.supporter_played = gs.energy_attached = gs.retreated = gs.stadium_played = False
    gs.pending = None
    pose_main(gs, 0)
    return engine


def _obs(engine):
    observation = engine.observation(viewer=0, sbi_token=export_token(engine.gs))
    observation["own_prizes"] = _own_prize_export(engine, 0)
    return observation


def test_60hp_policy_attaches_then_commits_lillie_and_replans():
    pilot = _build_pilot("mega_starmie")[0]
    engine = _fixture(60)
    first = pilot.explain(_obs(engine))
    assert first.chosen == [1]
    assert first.composer["bellman"] is True
    engine.step(first.chosen)
    second = pilot.explain(_obs(engine))
    selected = engine.gs.pending.options[second.chosen[0]]
    assert engine.gs.card_id(engine.gs.players[0].hand[selected["index"]]) == LILLIE


def test_50hp_policy_commits_the_boss_ko_line_after_a_commutative_attach():
    pilot = _build_pilot("mega_starmie")[0]
    engine = _fixture(50)
    decision = pilot.explain(_obs(engine))
    assert decision.chosen == [1]
    assert decision.composer["value"] > 0.0
    engine.step(decision.chosen)
    decision = pilot.explain(_obs(engine))
    assert pilot.decide(_obs(engine)) == [0]
    engine.step(decision.chosen)
    assert pilot.decide(_obs(engine)) == [0]


def test_atomic_route_never_calls_legacy_strategic_choosers(monkeypatch):
    pilot = _build_pilot("mega_starmie")[0]
    engine = _fixture(60)

    def legacy_called(*_args, **_kwargs):
        raise AssertionError("legacy strategic chooser was called")

    for name in ("_board", "_option_trace", "plan_turn", "_score_order",
                 "_finish_turn_last", "_greedy_grab"):
        monkeypatch.setattr(pilot, name, legacy_called)
    assert pilot.decide(_obs(engine)) == [1]


class _TerminalMenu:
    def __init__(self, delegate):
        self.delegate = delegate

    def actions(self, state):
        return tuple(action for action in self.delegate.actions(state)
                     if action.identity.kind in {"attack", "end"})

    def transition(self, state, action):
        return self.delegate.transition(state, action)

    def actor(self, state):
        return self.delegate.actor(state)


def test_bounded_and_reference_solvers_have_zero_regret_on_terminal_attack_sample():
    pilot = _build_pilot("mega_starmie")[0]
    registry = ValueRegistry.from_strategy(
        strategy=pilot.strategy, stats=pilot.stats, functions=pilot.functions, deck=pilot.deck)
    oracle = ValueOracle(registry, MegaStarmiePotential(pilot.stats))
    rows = [correction for correction in load_corrections(REPO / "data" / "corrections")
            if correction.agent == "mega_starmie" and correction.obs
            and int((correction.obs.get("select") or {}).get("context", -1)) == 0
            and any(option.get("type") == 13
                    for option in correction.obs["select"].get("option") or ())][:12]
    assert len(rows) == 12
    for correction in rows:
        state = DecisionState.from_observation(
            correction.obs, deck=tuple(DECK), deck_name="mega_starmie",
            value_registry_identity=registry.identity)
        reference_provider = _TerminalMenu(CgpyTransitionProvider(state, registry=registry))
        production_provider = _TerminalMenu(CgpyTransitionProvider(state, registry=registry))
        reference = ReferenceSolver(reference_provider, oracle).decide(state)
        production = ProductionSolver(
            production_provider, oracle,
            limits=ProductionLimits(max_depth=4, max_nodes=1_000,
                                    beam_width=1, preview_main_steps=0)).decide(state)
        assert production.action == reference.action
        assert production.value == pytest.approx(reference.value)


def test_terminal_game_value_does_not_bank_resources_spent_before_the_win():
    pilot = _build_pilot("mega_starmie")[0]
    potential = MegaStarmiePotential(pilot.stats, functions=pilot.functions)
    engine = _fixture(50)
    before = _obs(engine)
    won = _obs(engine)
    won["current"]["result"] = 0
    won["current"]["players"][0]["hand"] = []
    won["current"]["players"][0]["active"][0]["energyCards"] = [
        {"id": WATER, "playerIndex": 0} for _ in range(8)]
    won["current"]["players"][0]["active"][0]["energies"] = [3] * 8
    assert potential(won).families == (("game", potential.seeds.game),)
    assert potential(won).total > potential(before).total
