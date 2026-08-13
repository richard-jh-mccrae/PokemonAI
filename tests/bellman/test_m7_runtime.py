from __future__ import annotations

from pathlib import Path
import json

import pytest

from bellman_helpers import runtime
from cgpy.engine import Engine
from cgpy.options import pose_main
from cgpy.rng import SeededRng
from cgpy.search import export_token
from cgpy.state import PokemonInPlay

from common.engine import _own_prize_export
from common import (
    BoardPotential, DecisionState, Deterministic, ProductionLimits, ProductionSolver,
    ReferenceSolver, Terminal, ValueOracle, ValueRegistry,
)
from common.engine import CgpyTransitionProvider
from common.telemetry import to_record
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
DECK = [int(line) for line in (REPO / "src" / "agents" / "mega_starmie" /
                               "deck.csv").read_text().split()]
CINDERACE, STARYU, BOSS, WATER, LILLIE = 666, 1030, 1182, 3, 1227
SALVATORE, MEGA_STARMIE = 1189, 1031


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


def test_post_attach_state_replans_to_a_positive_legal_continuation():
    deployed = runtime()
    engine = _fixture(60)
    first = deployed.decide(_obs(engine))
    assert first.chosen == (1,)
    assert first.diagnostics["backend"] == "cgpy-bellman"
    engine.step(first.chosen)
    second = deployed.decide(_obs(engine))
    assert second.chosen
    assert second.action.kind != "end"
    assert second.value > 0.0


def test_50hp_policy_commits_the_boss_ko_line_after_a_commutative_attach():
    deployed = runtime()
    engine = _fixture(50)
    decision = deployed.decide(_obs(engine))
    assert decision.chosen == (1,)
    assert decision.value > 0.0
    engine.step(decision.chosen)
    decision = deployed.decide(_obs(engine))
    assert decision.chosen == (0,)
    engine.step(decision.chosen)
    assert deployed.decide(_obs(engine)).chosen == (0,)


def test_bellman_telemetry_contains_no_legacy_pilot_payload():
    record = to_record(runtime().decide(_obs(_fixture(60))))

    assert record["bellman"] is True
    assert set(record) == {
        "bellman", "chosen", "action", "value", "complete", "diagnostics", "belief",
    }
    assert not ({"plan", "opts", "lethal", "planned", "margin", "composer", "posture"}
                & set(record))


def test_post_attack_potential_keeps_the_root_players_perspective():
    """A passed turn must not value our attacker as the opponent's threat."""
    deployed = runtime()
    observation = _obs(_fixture(60))
    observation["current"]["yourIndex"] = 1
    registry = deployed.registry
    potential = BoardPotential(deployed.stats, registry=registry, root_seat=0)

    assert potential(observation).total == pytest.approx(
        BoardPotential(deployed.stats, registry=registry)(
        {**observation, "current": {**observation["current"], "yourIndex": 0}}).total)


def test_bellman_batch_establishes_the_starmie_line_before_attacking():
    deployed = runtime()
    records = [json.loads(line) for line in (
        REPO / "data" / "corrections" / "mega_starmie_20260811_46817364" /
        "corrections.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = {
        # Bench Staryu directly. The no-op Ability-first permutation has identical utility but
        # one extra decision, so the solver's documented exact-tie objective removes it.
        "eb4fb1f19691": [2],
        "4907d6c25a56": [0],  # Poffin two Staryu, then take the attack.
        "3730b43d89a5": [1],  # Free Cape, then Water to Cinderace and Turbo Flare.
    }
    for record in records:
        if record["id"] in expected:
            assert deployed.decide(record["obs"]).chosen == tuple(expected[record["id"]])


@pytest.mark.parametrize(("fixture", "expected"), [
    ("ms_snipe_attacker_line_over_support_f85.json", (0,)),
    ("ms_snipe_ko_beats_positional_stack_f45.json", (0,)),
])
def test_snipe_prioritizes_the_attack_line_but_never_over_a_ko(fixture, expected):
    record = json.loads((REPO / "tests" / "fixtures" / "corrections" / fixture).read_text())

    assert runtime().decide(record["obs"]).chosen == expected


@pytest.mark.parametrize(("correction_id", "expected"), [
    ("5d3c218d35c2", (1,)),  # Keep attacking the primary when gusting support gains less value.
    ("6d7a2f5332c9", (0,)),  # Gust the developing primary line for the reachable KO.
])
def test_gust_choices_remain_bellman_cost_benefit_decisions(correction_id, expected):
    record = next(correction for correction in load_corrections(REPO / "data" / "corrections")
                  if correction.agent == "mega_starmie" and correction.id == correction_id)

    assert runtime().decide(record.obs).chosen == expected


def test_runtime_exposes_no_legacy_strategic_choosers():
    deployed = runtime()
    assert not any(hasattr(deployed, name) for name in (
        "_board", "_option_trace", "plan_turn", "_score_order",
        "_finish_turn_last", "_greedy_grab"))
    assert deployed.decide(_obs(_fixture(60))).chosen == (1,)


def test_turn_zero_uses_declarative_pregame_policy():
    deployed = runtime()
    observation = _obs(_fixture(60))
    observation["current"]["turn"] = 0
    observation["select"] = {
        "type": 8, "context": 38, "minCount": 1, "maxCount": 1,
        "remainDamageCounter": 0, "remainEnergyCost": 0,
        "option": [{"type": 0, "number": 0}, {"type": 0, "number": 1}],
        "deck": None, "contextCard": None, "effect": None,
    }

    decision = deployed.decide(observation)
    assert decision.chosen in ((0,), (1,))
    assert decision.diagnostics["backend"] == "declarative-pregame"


def test_forkable_engine_turbo_flare_energy_menu_reconstructs_the_attack_rider():
    records = json.loads((REPO / "tests" / "fixtures" / "continuation_parity" /
                          "seeded_continuations.json").read_text(encoding="utf-8"))["records"]
    observation = next(record["seed_observation"] for record in records
                       if record["context"] == 22)
    state = DecisionState.from_observation(
        observation, deck=tuple(DECK), deck_name="mega_starmie")
    provider = CgpyTransitionProvider(state)

    assert provider.available and not provider._local_nested
    action = next(action for action in provider.actions(state) if len(action.selection) == 3)
    resolved = provider.transition(state, action)
    assert isinstance(resolved, Deterministic)
    # This recorded board has no legal Bench recipient, so the selected cards correctly stay in
    # deck and the reconstructed rider completes the attack instead of fabricating placements.
    assert resolved.state.obs["select"]["context"] == 0
    assert resolved.state.obs["current"]["turn"] > observation["current"]["turn"]


def test_historical_mandatory_prize_and_retreat_cost_menus_replan_without_unknown():
    observation = _obs(_fixture(60))
    observation["search_begin_input"] = "opaque-historical-token"
    seat = observation["current"]["yourIndex"]
    before_prizes = len(observation["current"]["players"][seat]["prize"])
    observation["select"] = {
        "type": 1, "context": 7, "minCount": 3, "maxCount": 3,
        "remainDamageCounter": 0, "remainEnergyCost": 0,
        "option": [{"type": 3, "area": 6, "index": index, "playerIndex": seat}
                   for index in range(4)],
        "deck": None, "contextCard": None, "effect": None,
    }
    prize_state = DecisionState.from_observation(
        observation, deck=tuple(DECK), deck_name="mega_starmie")
    prize_provider = CgpyTransitionProvider(prize_state)
    prize_action = next(action for action in prize_provider.actions(prize_state)
                        if action.selection == (1, 2, 3))
    prize_result = prize_provider.transition(prize_state, prize_action)
    assert isinstance(prize_result, Terminal)
    assert len(prize_result.state.obs["current"]["players"][seat]["prize"]) == before_prizes - 3

    observation = _obs(_fixture(60))
    observation["search_begin_input"] = "opaque-historical-token"
    player = observation["current"]["players"][seat]
    energy = next(card for card in player["hand"] if card["id"] == WATER)
    player["hand"].remove(energy)
    player["handCount"] = len(player["hand"])
    player["active"][0]["energyCards"] = [energy]
    player["active"][0]["energies"] = [3]
    observation["select"] = {
        "type": 4, "context": 30, "minCount": 1, "maxCount": 1,
        "remainDamageCounter": 0, "remainEnergyCost": 1,
        "option": [{"type": 6, "area": 4, "index": 0, "playerIndex": seat,
                    "energyIndex": 0, "count": 1}],
        "deck": None, "contextCard": None, "effect": None,
    }
    cost_state = DecisionState.from_observation(
        observation, deck=tuple(DECK), deck_name="mega_starmie")
    cost_provider = CgpyTransitionProvider(cost_state)
    cost_result = cost_provider.transition(cost_state, cost_provider.actions(cost_state)[0])
    assert isinstance(cost_result, Terminal)
    after = cost_result.state.obs["current"]["players"][seat]
    assert after["active"][0]["energyCards"] == []
    assert after["discard"][-1]["id"] == WATER


def test_forkable_engine_reconstructs_both_evolution_and_target_asks():
    engine = _fixture(60)
    gs = engine.gs
    board = gs.players[0]

    def take_from_deck(card_id):
        serial = next(serial for serial in board.deck if gs.card_id(serial) == card_id)
        board.deck.remove(serial)
        return serial

    salvatore = take_from_deck(SALVATORE)
    staryu = take_from_deck(STARYU)
    board.hand.append(salvatore)
    stat = gs.stat(staryu)
    board.bench.append(PokemonInPlay(
        stack=[staryu], hp=stat.hp, max_hp=stat.hp, entered_turn=gs.turn - 1))
    gs.pending = None
    pose_main(gs, 0)
    play_index = next(index for index, option in enumerate(gs.pending.options)
                      if option["type"] == 7
                      and gs.card_id(board.hand[option["index"]]) == SALVATORE)
    engine.step([play_index])
    assert gs.pending.context == 19

    observation = engine.observation(viewer=0, sbi_token="opaque-historical-token")
    observation["own_prizes"] = _own_prize_export(engine, 0)
    evolve_state = DecisionState.from_observation(
        observation, deck=tuple(DECK), deck_name="mega_starmie")
    evolve_provider = CgpyTransitionProvider(evolve_state)
    assert not evolve_provider._local_nested
    evolve_action = next(action for action in evolve_provider.actions(evolve_state)
                         if action.selection)
    target_node = evolve_provider.transition(evolve_state, evolve_action)
    assert isinstance(target_node, Deterministic)
    assert target_node.state.obs["select"]["context"] == 18

    target_observation = target_node.state.obs
    target_observation["search_begin_input"] = "opaque-historical-token"
    target_state = DecisionState.from_observation(
        target_observation, deck=tuple(DECK), deck_name="mega_starmie")
    target_provider = CgpyTransitionProvider(target_state)
    assert not target_provider._local_nested
    target_action = next(action for action in target_provider.actions(target_state)
                         if target_observation["select"]["option"][action.selection[0]]["area"] == 5)
    resolved = target_provider.transition(target_state, target_action)
    assert isinstance(resolved, Deterministic)
    assert resolved.state.obs["current"]["players"][0]["bench"][0]["id"] == MEGA_STARMIE


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
    deployed = runtime()
    registry = deployed.registry
    oracle = ValueOracle(registry, BoardPotential(deployed.stats, registry=registry))
    rows = []
    for correction in load_corrections(REPO / "data" / "corrections"):
        if (correction.agent != "mega_starmie" or not correction.obs
                or int((correction.obs.get("select") or {}).get("context", -1)) != 0):
            continue
        state = DecisionState.from_observation(
            correction.obs, deck=tuple(DECK), deck_name="mega_starmie",
            value_registry_identity=registry.identity)
        provider = CgpyTransitionProvider(state, registry=registry)
        attacks = tuple(action for action in provider.actions(state)
                        if action.identity.kind == "attack")
        if attacks and all(isinstance(provider.transition(state, action), Terminal)
                           for action in attacks):
            rows.append(correction)
        if len(rows) == 12:
            break
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
            limits=ProductionLimits(max_nodes=1_000, beam_width=1)).decide(state)
        assert production.action == reference.action
        assert production.value == pytest.approx(reference.value)


def test_terminal_game_value_does_not_bank_resources_spent_before_the_win():
    deployed = runtime()
    registry = deployed.registry
    potential = BoardPotential(deployed.stats, registry=registry)
    engine = _fixture(50)
    before = _obs(engine)
    won = _obs(engine)
    won["current"]["result"] = 0
    won["current"]["players"][0]["hand"] = []
    won["current"]["players"][0]["active"][0]["energyCards"] = [
        {"id": WATER, "playerIndex": 0} for _ in range(8)]
    won["current"]["players"][0]["active"][0]["energies"] = [3] * 8
    assert potential(won).families == (("game", potential.scale.game),)
    assert potential(won).total > potential(before).total
