from __future__ import annotations

from collections import Counter
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
    BoardPotential, Chance, DecisionState, Deterministic, ProductionLimits, ProductionSolver,
    ReferenceSolver, Terminal, ValueOracle, ValueRegistry,
)
from common.engine import CgpyTransitionProvider
from common.planner import forced_action_decision
from common.telemetry import to_record
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
DECK = [int(line) for line in (REPO / "src" / "agents" / "mega_starmie" /
                               "deck.csv").read_text().split()]
LUCARIO_DECK = [int(line) for line in (REPO / "src" / "agents" / "mega_lucario" /
                                       "deck.csv").read_text().split()]
CINDERACE, STARYU, BOSS, WATER, LILLIE = 666, 1030, 1182, 3, 1227
SALVATORE, MEGA_STARMIE, MEOWTH = 1189, 1031, 1071


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


def test_only_legal_action_bypasses_all_bellman_work():
    deployed = runtime()
    observation = _obs(_fixture(60))
    observation["select"] = {
        "type": 1, "context": 8, "minCount": 1, "maxCount": 1,
        "remainDamageCounter": 0, "remainEnergyCost": 0,
        "option": [{"type": 3, "area": 2, "index": 1, "playerIndex": 0}],
        "deck": None, "contextCard": None, "effect": None,
    }
    deployed._planner = lambda _observation: pytest.fail("forced action entered Bellman")

    decision = deployed.decide(observation)

    assert decision.chosen == (0,)
    assert decision.complete
    assert decision.diagnostics == {
        "backend": "forced-single-action", "searched": False, "legal_actions": 1,
    }


def test_exact_successor_policy_is_reused_at_the_live_decision_boundary():
    deployed = runtime()
    engine = _fixture(60)

    first = deployed.decide(_obs(engine))
    engine.step(first.chosen)
    second = deployed.decide(_obs(engine))

    assert second.diagnostics == {
        "backend": "cgpy-bellman-transposition", "searched": False,
    }


def test_single_optional_option_is_not_mistaken_for_a_forced_action():
    observation = _obs(_fixture(60))
    observation["select"] = {
        "type": 1, "context": 8, "minCount": 0, "maxCount": 1,
        "option": [{"type": 3, "area": 2, "index": 1, "playerIndex": 0}],
    }

    assert forced_action_decision(observation) is None


def test_forkable_engine_turbo_flare_energy_menu_reconstructs_the_attack_rider():
    records = json.loads((REPO / "tests" / "fixtures" / "continuation_parity" /
                          "seeded_continuations.json").read_text(encoding="utf-8"))["records"]
    observation = next(record["seed_observation"] for record in records
                       if record["context"] == 22)
    state = DecisionState.from_observation(
        observation, deck=tuple(DECK), deck_name="mega_starmie")
    provider = CgpyTransitionProvider(state)

    assert provider.available and not provider._local_nested, provider._local_error
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


def test_forkable_engine_reconstructs_an_in_play_triggered_ability_gate():
    engine, _seat, _error = Engine.start(
        LUCARIO_DECK, LUCARIO_DECK, rng=SeededRng(4))
    gs = engine.gs
    for seat, board in enumerate(gs.players):
        board.hand = []
        board.discard = []
        board.prize = []
        board.deck = []
        board.active = None
        board.bench = []
        owned = [serial for serial, card in gs.cards.items() if card.owner == seat]
        riolu = next(serial for serial in owned if gs.card_id(serial) == 677)
        board.active = PokemonInPlay(stack=[riolu], hp=80, max_hp=80, entered_turn=0)
        remaining = [serial for serial in owned if serial != riolu]
        board.prize = remaining[:6]
        board.deck = remaining[6:]
    board = gs.players[0]
    meowth = next(serial for serial in board.deck if gs.card_id(serial) == MEOWTH)
    board.deck.remove(meowth)
    board.hand.append(meowth)
    gs.turn = 1
    gs.first_player = 1
    gs.phase = "TURN"
    gs.phase_data = {"seat": 0}
    gs.pending = None
    pose_main(gs, 0)
    play = next(index for index, option in enumerate(engine.gs.pending.options)
                if option["type"] == 7
                and engine.gs.card_id(board.hand[option["index"]]) == MEOWTH)
    engine.step([play])
    assert engine.gs.pending.context == 43

    observation = _obs(engine)
    observation["search_begin_input"] = "opaque-native-token"
    state = DecisionState.from_observation(
        observation, deck=tuple(LUCARIO_DECK), deck_name="mega_lucario")
    provider = CgpyTransitionProvider(state)

    assert provider.available and not provider._local_nested, provider._local_error
    outcomes = {action.identity.kind: provider.transition(state, action)
                for action in provider.actions(state)}
    assert set(outcomes) == {"yes", "no"}
    assert isinstance(outcomes["yes"], Deterministic)
    assert outcomes["yes"].state.obs["select"]["context"] == 7
    assert isinstance(outcomes["no"], Deterministic)
    assert outcomes["no"].state.obs["select"]["context"] == 0


def test_cost_before_draw_chance_outcomes_keep_distinct_latent_states():
    correction = next(
        c for c in load_corrections(REPO / "data" / "corrections")
        if c.agent == "mega_lucario" and c.episode_id == 85785067
        and int((c.decision or {}).get("frame", -1)) == 54)
    deployed = runtime("mega_lucario")
    state = DecisionState.from_observation(
        correction.obs, deck=tuple(LUCARIO_DECK), deck_name="mega_lucario",
        value_registry_identity=deployed.registry.identity)
    provider = CgpyTransitionProvider(
        state, registry=deployed.registry, effects=deployed.effects, stats=deployed.stats)
    ability = next(action for action in provider.actions(state)
                   if action.identity.kind == "ability")

    transition = provider.transition(state, ability)

    assert isinstance(transition, Chance)
    keys = [edge.node.state.semantic_key for edge in transition.children]
    assert len(keys) == len(set(keys)) == 16
    assert all(edge.node.state.obs.get("bellmanLatent") for edge in transition.children)


def test_engine_exports_generic_turn_damage_modifiers_to_successor_value():
    correction = next(
        c for c in load_corrections(REPO / "data" / "corrections")
        if c.agent == "mega_lucario" and c.episode_id == 84889539
        and int((c.decision or {}).get("frame", -1)) == 48)
    deployed = runtime("mega_lucario")
    state = DecisionState.from_observation(
        correction.obs, deck=tuple(LUCARIO_DECK), deck_name="mega_lucario",
        value_registry_identity=deployed.registry.identity)
    provider = CgpyTransitionProvider(
        state, registry=deployed.registry, effects=deployed.effects, stats=deployed.stats)
    boost = next(action for action in provider.actions(state)
                 if action.identity.kind == "play")

    transition = provider.transition(state, boost)

    assert isinstance(transition, Deterministic)
    assert transition.state.obs["bellmanTransient"]["damage_boosts"] == (
        {"bonus": 30, "attackerEnergyType": 6},)


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


def test_typed_fetch_graph_reaches_evolution_cards_through_multi_hop_tutors():
    deployed = runtime("mega_lucario")
    potential = BoardPotential(
        deployed.stats, registry=deployed.registry, profile=deployed.profile,
        effects=deployed.effects, root_seat=0,
    )

    def player(hand):
        visible = list(hand) + [673]
        remaining = len(deployed.deck) - len(visible)
        return {
            "hand": [{"id": card_id} for card_id in hand], "discard": [],
            "active": [], "bench": [{"id": 673, "hp": 80, "maxHp": 80,
                                        "energies": [], "tools": [], "preEvolution": []}],
            "benchMax": 5, "deckCount": remaining,
        }

    direct, _ = potential._reachable_card_access(player([1152]))  # Poké Pad
    assert direct[674] == pytest.approx(0.75)       # Hariyama: no Rule Box
    assert 678 not in direct                        # Mega Lucario ex: Rule Box

    chained, _ = potential._reachable_card_access(player([1071]))  # Meowth ex
    assert chained[1219] == pytest.approx(0.75)       # Petrel
    assert chained[1152] == pytest.approx(0.75 ** 2)  # Petrel -> Poké Pad
    assert chained[1142] == pytest.approx(0.75 ** 2)  # Petrel -> Fighting Gong
    assert chained[1141] == pytest.approx(0.75 ** 2)  # Petrel -> Premium Power Pro
    assert chained[1174] == pytest.approx(0.75 ** 2)  # Petrel -> Air Balloon
    assert chained[1211] == pytest.approx(0.75)       # Meowth -> Black Belt directly
    assert chained[674] == pytest.approx(0.75 ** 3)   # Pad -> Hariyama
    assert chained[676] == pytest.approx(0.75 ** 3)   # Gong/Pad -> Solrock
    assert chained[6] == pytest.approx(0.75 ** 3)     # Gong -> Basic Fighting Energy

    with_fodder, _ = potential._reachable_card_access(player([1071, 1252, 1252]))
    assert with_fodder[678] == pytest.approx(0.75 ** 3)  # Petrel -> Ultra Ball -> Mega

    absent, _ = potential._reachable_card_access(player([]))
    assert 674 not in absent


def test_meowth_tutor_lines_reach_legal_mega_lucario_outs():
    correction = next(
        c for c in load_corrections(REPO / "data" / "corrections")
        if c.agent == "mega_lucario" and c.episode_id == 85709280
        and int((c.decision or {}).get("frame", -1)) == 17
    )
    deployed = runtime("mega_lucario")
    observation = json.loads(json.dumps(correction.obs))
    seat = int(observation["current"]["yourIndex"])
    known_prizes = Counter(
        card["id"] for card in correction.decision["current"]["players"][seat]["prize"])
    observation["own_prizes"] = {str(card_id): count
                                  for card_id, count in known_prizes.items()}
    state = DecisionState.from_observation(
        observation, deck=tuple(LUCARIO_DECK), deck_name="mega_lucario",
        value_registry_identity=deployed.registry.identity,
    )
    provider = CgpyTransitionProvider(
        state, registry=deployed.registry, effects=deployed.effects, stats=deployed.stats)
    potential = BoardPotential(
        deployed.stats, registry=deployed.registry, profile=deployed.profile,
        effects=deployed.effects, root_seat=seat,
    )
    potential.prepare_needs(observation, seat)

    def carries(action, card_id):
        return f'"id":{card_id}' in repr(action.identity.parts)

    def take(current, predicate):
        action = next(action for action in provider.actions(current) if predicate(action))
        transition = provider.transition(current, action)
        assert isinstance(transition, Deterministic)
        return transition.state

    # A real multi-hop route is carried through each engine state. Existing hand copies cannot
    # masquerade as fetched progress; every committed fetch/play step raises its Bellman value.
    chain = state
    progress = [potential._need_route_access(chain.obs, seat)]
    chain = take(chain, lambda action: action.identity.kind == "play"
                 and carries(action, 1071))
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: action.identity.kind == "yes")
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: carries(action, 1219))
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: action.identity.kind == "play"
                 and carries(action, 1219))
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: carries(action, 1121))
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: action.identity.kind == "play"
                 and carries(action, 1121))
    progress.append(potential._need_route_access(chain.obs, seat))
    chain = take(chain, lambda action: action.identity.kind == "card")
    chain = take(chain, lambda action: carries(action, 673))
    fetched_progress = potential._need_route_access(chain.obs, seat)
    chain = take(chain, lambda action: action.identity.kind == "play"
                 and carries(action, 673))

    assert progress == sorted(progress)
    assert progress[-1] > progress[0] > 0.0
    assert fetched_progress > progress[-1]
    assert all(673 not in dict(need.direct)
               for need in potential._need_model.immediate(chain.obs, seat))

    meowth = take(state, lambda action: action.identity.kind == "play"
                  and carries(action, 1071))
    supporter_menu = take(meowth, lambda action: action.identity.kind == "yes")

    # Black Belt is a Supporter, so Meowth must fetch it directly for same-turn damage.
    black_belt = take(supporter_menu, lambda action: carries(action, 1211))
    assert any(action.identity.kind == "play" and carries(action, 1211)
               for action in provider.actions(black_belt))

    petrel = take(supporter_menu, lambda action: carries(action, 1219))
    trainer_menu = take(petrel, lambda action: action.identity.kind == "play"
                        and carries(action, 1219))
    for target in (1152, 1142, 1121, 1141):
        fetched = take(trainer_menu, lambda action, target=target: carries(action, target))
        assert any(action.identity.kind == "play" and carries(action, target)
                   for action in provider.actions(fetched))


def test_typed_tutor_option_value_credits_its_best_reachable_outcome():
    deployed = runtime("mega_lucario")
    potential = BoardPotential(
        deployed.stats, registry=deployed.registry, profile=deployed.profile,
        effects=deployed.effects, root_seat=0,
    )

    def hand_value(card_id):
        owner = {
            "active": [{"id": 675}], "bench": [],
            "hand": [{"id": card_id}], "discard": [],
            "benchMax": 5, "deckCount": len(deployed.deck) - 2,
        }
        return potential._hand_resources(owner)

    # Boss has immediate gust Worth. Petrel can instead reach a typed Trainer and that Trainer's
    # best legal target, so its state value carries the option rather than tying on cardboard.
    assert hand_value(1219) > hand_value(1182)


def test_petrel_need_route_targets_air_balloon_when_retreat_is_the_missing_operation():
    deployed = runtime("mega_lucario")
    potential = BoardPotential(
        deployed.stats, registry=deployed.registry, profile=deployed.profile,
        effects=deployed.effects, root_seat=0,
    )
    observation = json.loads((
        REPO / "tests" / "fixtures" / "corrections" /
        "ml_petrel_balloon_retreat_lethal_f15.json").read_text())["obs"]
    observation["current"]["energyAttached"] = True
    seat = int(observation["current"]["yourIndex"])
    me = observation["current"]["players"][seat]
    needs = potential._need_model.immediate(observation, seat)
    available = potential._remaining_deck_pool(me)

    route = potential._need_model.best_route(
        1219, needs, supporter_available=True,
        discard_capacity=len(me["hand"]) - 1,
        bench_capacity=int(me.get("benchMax", 5)) - len(me.get("bench") or ()),
        available_targets=available)

    assert route is not None
    assert needs[route.need_index].key == "retreat_access"
    assert route.path == (1219, 1174)

    potential.prepare_needs(observation, seat)
    prepared = potential._prepared_need_routes[1219]
    assert (1219, 1174) in {candidate.path for candidate in prepared}
    assert (1219, 1123) in {candidate.path for candidate in prepared}  # Switch, same operation.
    state = DecisionState.from_observation(
        observation, deck=tuple(LUCARIO_DECK), deck_name="mega_lucario",
        value_registry_identity=deployed.registry.identity)
    provider = CgpyTransitionProvider(
        state, registry=deployed.registry, effects=deployed.effects, stats=deployed.stats)
    play_petrel = next(action for action in provider.actions(state)
                       if action.selection == (0,))
    pending_transition = provider.transition(state, play_petrel)
    assert isinstance(pending_transition, Deterministic)
    pending = pending_transition.state
    pending_access = potential._need_route_access(pending.obs, seat)
    route_targets = {int(route.path[1]) for route in prepared if len(route.path) > 1}
    unavailable = json.loads(json.dumps(pending.obs))
    deck = tuple(unavailable["select"].get("deck") or ())
    irrelevant_option = next(
        option for option in unavailable["select"]["option"]
        if option.get("area") == 1
        and int(deck[int(option["index"])]["id"]) not in route_targets)
    unavailable["select"]["option"] = [irrelevant_option]
    assert potential._need_route_access(unavailable, seat) == 0.0
    fetch_balloon = next(
        action for action in provider.actions(pending)
        if '"id":1174' in repr(action.identity.parts))
    fetched_transition = provider.transition(pending, fetch_balloon)
    assert isinstance(fetched_transition, Deterministic)
    fetched = fetched_transition.state
    fetched_access = potential._need_route_access(fetched.obs, seat)
    attach_balloon = next(action for action in provider.actions(fetched)
                          if action.identity.kind == "attach")
    attached_transition = provider.transition(fetched, attach_balloon)
    assert isinstance(attached_transition, Deterministic)

    assert pending_access > 0.0
    assert fetched_access > pending_access
    assert potential.search_focus(attached_transition.state.obs) > fetched_access
    assert potential(attached_transition.state.obs).total >= potential(fetched.obs).total


def test_meowth_need_routes_include_petrel_to_damage_boost_only_when_boost_is_missing():
    deployed = runtime("mega_lucario")
    potential = BoardPotential(
        deployed.stats, registry=deployed.registry, profile=deployed.profile,
        effects=deployed.effects, root_seat=0,
    )
    observation = json.loads((
        REPO / "tests" / "fixtures" / "corrections" /
        "ml_lethal_retreat_boost_to_ko_f24.json").read_text())["obs"]
    seat = int(observation["current"]["yourIndex"])
    me = observation["current"]["players"][seat]
    me["hand"] = [card for card in me["hand"] if int(card["id"]) != 1141]
    me["handCount"] = len(me["hand"])
    needs = potential._need_model.immediate(observation, seat)
    uncovered = potential._need_model.uncovered_by_direct_hand(
        needs, (int(card["id"]) for card in me["hand"]), supporter_available=True)
    available = potential._remaining_deck_pool(me)
    routes = potential._need_model.routes(
        1071, uncovered, supporter_available=True,
        discard_capacity=len(me["hand"]) - 1,
        bench_capacity=int(me.get("benchMax", 5)) - len(me.get("bench") or ()),
        available_targets=available)

    assert any(
        uncovered[route.need_index].key == "damage_threshold"
        and route.path == (1071, 1219, 1141)
        for route in routes)

    held_needs = potential._need_model.uncovered_by_direct_hand(
        needs, (1141,), supporter_available=True)
    assert "damage_threshold" not in {need.key for need in held_needs}


def test_prize_route_credits_tutored_evolution_access_between_held_and_absent():
    deployed = runtime("mega_lucario")

    def route_value(hand):
        potential = BoardPotential(
            deployed.stats, registry=deployed.registry, profile=deployed.profile,
            effects=deployed.effects, root_seat=0,
        )
        me = {
            "active": [{"id": 678, "energies": [6]}],
            "bench": [{"id": 673, "energies": [6, 6, 6]},
                      {"id": 678, "energies": [6]}],
            "hand": [{"id": card_id} for card_id in hand], "discard": [],
            "benchMax": 5, "deckCount": len(deployed.deck) - 3 - len(hand),
            "prize": [None] * 5,
        }
        opponent = {"prize": [None] * 6}
        potential._known_prize_counts = Counter()
        return potential._prize_plan(me, opponent)

    held = route_value([674])
    tutored = route_value([1152])
    absent = route_value([])

    assert held == pytest.approx(2.0)
    assert tutored == pytest.approx(1.5)
    assert absent == pytest.approx(0.0)
    assert absent < tutored < held


def test_tutored_hariyama_access_changes_prize_route_energy_preparation():
    deployed = runtime("mega_lucario")

    def route_value(hand, makuhita_energy, lucario_energy):
        potential = BoardPotential(
            deployed.stats, registry=deployed.registry, profile=deployed.profile,
            effects=deployed.effects, root_seat=0,
        )
        me = {
            "active": [{"id": 678, "energies": [6]}],
            "bench": [
                {"id": 673, "energies": [6] * makuhita_energy},
                {"id": 678, "energies": [6] * lucario_energy},
            ],
            "hand": [{"id": card_id} for card_id in hand], "discard": [],
            "benchMax": 5, "deckCount": len(deployed.deck) - 3 - len(hand),
            "prize": [None] * 5,
        }
        potential._known_prize_counts = Counter()
        return potential._prize_plan(me, {"prize": [None] * 6})

    for hand in ([674], [1152], [674, 6], [1152, 6]):
        # Hariyama or typed access through Poké Pad, with or without another Energy in hand.
        # That hand Energy retains competing uses; it is not assumed attached for free.
        assert route_value(hand, 3, 0) > route_value(hand, 2, 1)
        assert route_value(hand, 3, 0) > route_value(hand, 1, 2)
    assert route_value([], 3, 0) == pytest.approx(route_value([], 1, 2))
