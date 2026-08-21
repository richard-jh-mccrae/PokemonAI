from __future__ import annotations

from collections import Counter

import pytest

from cgpy.cards import CardDB
from cgpy.engine import Engine
from cgpy.options import pose_main
from cgpy.rng import SeededRng
from cgpy.schema import CardType
from cgpy.state import PokemonInPlay

from deprecated.bellman.state import DecisionState
from deprecated.bellman import ReferenceSolver
from common.engine import _own_prize_export
from deprecated.bellman.providers import BellmanCgpyProvider as CgpyTransitionProvider
from deprecated.bellman.value import CardFacts, Potential, ValueOracle, ValueRegistry
from deprecated.bellman.tags import CardFunctions


WATER, IGNITION, CINDERACE, STARYU, MEGA = 3, 17, 666, 1030, 1031
TURBO, JETTING, NEBULA = 965, 1487, 1488


def _deck():
    from pathlib import Path
    repo = Path(__file__).resolve().parents[3]
    return tuple(int(line) for line in (repo / "src" / "agents" / "mega_starmie" /
                                        "deck.csv").read_text().split())


DECK = _deck()


def _serials(gs, seat, card_id):
    return [serial for serial, card in gs.cards.items()
            if card.owner == seat and card.card_id == card_id]


def _body(gs, seat, card_id, *, hp=None, energy=()):
    serial = _serials(gs, seat, card_id).pop(0)
    stat = gs.stat(serial)
    return PokemonInPlay(stack=[serial], energy=list(energy), hp=stat.hp if hp is None else hp,
                         max_hp=stat.hp, entered_turn=1)


def _attack_engine(attack_id, *, turbo_bench=True, opp_active_hp=330,
                   opp_bench=((STARYU, 70),)):
    engine, _seat, _error = Engine.start(list(DECK), list(DECK), rng=SeededRng(3))
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
        serial = next(serial for serial in _serials(gs, seat, card_id) if serial not in used)
        used.add(serial)
        return serial

    if attack_id == TURBO:
        active_serial = take(0, CINDERACE)
        energy = take(0, WATER)
        gs.players[0].active = PokemonInPlay(
            stack=[active_serial], energy=[energy], hp=160, max_hp=160, entered_turn=1)
        if turbo_bench:
            bench_serial = take(0, STARYU)
            gs.players[0].bench = [PokemonInPlay(
                stack=[bench_serial], hp=70, max_hp=70, entered_turn=1)]
    else:
        active_serial = take(0, MEGA)
        energy = take(0, WATER if attack_id == JETTING else IGNITION)
        gs.players[0].active = PokemonInPlay(
            stack=[take(0, STARYU), active_serial], energy=[energy], hp=330, max_hp=330,
            entered_turn=1)
    opp_active = take(1, MEGA)
    gs.players[1].active = PokemonInPlay(
        stack=[take(1, STARYU), opp_active], hp=opp_active_hp, max_hp=330, entered_turn=1)
    for card_id, hp in opp_bench:
        serial = take(1, card_id)
        gs.players[1].bench.append(PokemonInPlay(
            stack=[serial], hp=hp, max_hp=gs.stat(serial).hp, entered_turn=1))

    for seat in (0, 1):
        remaining = [serial for serial, card in gs.cards.items()
                     if card.owner == seat and serial not in used]
        non_water = [serial for serial in remaining if gs.card_id(serial) != WATER]
        prizes = non_water[:6]
        deck = [serial for serial in remaining if serial not in prizes]
        gs.players[seat].prize = prizes
        gs.players[seat].deck = deck
    gs.turn = 3
    gs.first_player = 1
    gs.phase = "TURN"
    gs.phase_data = {"seat": 0}
    gs.supporter_played = gs.energy_attached = gs.retreated = gs.stadium_played = False
    gs.pending = None
    pose_main(gs, 0)
    assert any(option.get("attackId") == attack_id for option in gs.pending.options)
    return engine


def _registry():
    db = CardDB.load()
    functions = CardFunctions.load()
    facts = {card_id: CardFacts(
        known=True,
        ace_spec=bool(db.card(card_id).aceSpec),
        typed_basic_energy=db.card(card_id).cardType == CardType.BASIC_ENERGY,
    ) for card_id in set(DECK)}
    return ValueRegistry(
        roles={MEGA: ("primary_attacker", "primary_attacker"),
               CINDERACE: ("accel_source",)},
        functions={card_id: tuple(functions.tags(card_id)) for card_id in set(DECK)},
        facts=facts, line_bases=(STARYU,),
    )


def _state(engine, registry):
    obs = engine.observation(viewer=0, sbi_token="cgpy")
    obs["own_prizes"] = _own_prize_export(engine, 0)
    return DecisionState.from_observation(obs, deck=DECK, deck_name="mega_starmie",
                                          value_registry_identity=registry.identity)


def _potential(obs):
    current = obs["current"]
    me, opp = current["players"]
    prize = (6 - len(me.get("prize") or ())) - (6 - len(opp.get("prize") or ()))
    damage = 0.0
    for body in tuple(opp.get("active") or ()) + tuple(opp.get("bench") or ()):
        if body:
            damage += max(0, body.get("maxHp", body.get("hp", 0)) - body.get("hp", 0)) / 160.0
    development = sum(len(body.get("energyCards") or ()) * (0.20 if body.get("id") == STARYU else 0.05)
                      for body in (me.get("bench") or ()) if body)
    their_active = next((body for body in (opp.get("active") or ()) if body), None)
    threat = -0.40 if their_active and their_active.get("id") == MEGA else 0.0
    result = current.get("result", -1)
    game = 20.0 if result == 0 else -20.0 if result not in (-1, 0) else 0.0
    families = (("game", game), ("prize_race", prize), ("damage", damage),
                ("development", development), ("threat", threat))
    return Potential(sum(value for _key, value in families), families)


class AttackOnly:
    def __init__(self, delegate, attack_id):
        self.delegate, self.attack_id = delegate, attack_id

    def actions(self, state):
        actions = self.delegate.actions(state)
        engine = self.delegate._engines[state.semantic_key]
        if int(engine.gs.pending.context) != 0:
            return actions
        keep = []
        for action in actions:
            if action.identity.kind == "end":
                keep.append(action)
            elif action.identity.kind == "attack":
                option = engine.gs.pending.options[action.selection[0]]
                if option.get("attackId") == self.attack_id:
                    keep.append(action)
        return tuple(keep)

    def transition(self, state, action):
        return self.delegate.transition(state, action)

    def actor(self, state):
        return self.delegate.actor(state)


def _solve(attack_id, **kwargs):
    registry = _registry()
    engine = _attack_engine(attack_id, **kwargs)
    state = _state(engine, registry)
    provider = CgpyTransitionProvider(state, registry=registry, engine=engine)
    decision = ReferenceSolver(AttackOnly(provider, attack_id), ValueOracle(registry, _potential)).decide(state)
    return decision, provider


def test_turbo_flare_resolves_count_recipients_and_persistent_energy_before_terminal():
    decision, provider = _solve(TURBO)
    assert decision.action.kind == "attack"
    assert decision.value > 0.0
    terminal_engines = [engine for key, engine in provider._engines.items()
                        if provider._attack_committed.get(key)
                        and engine.gs.turn > 3]
    assert terminal_engines
    assert max(len(engine.gs.players[0].bench[0].energy) for engine in terminal_engines) == 3


def test_jetting_blow_snipe_target_is_inside_attack_tree_and_takes_bench_ko():
    decision, provider = _solve(JETTING, opp_active_hp=330,
                                opp_bench=((STARYU, 40), (STARYU, 70)))
    assert decision.action.kind == "attack"
    terminal = max((engine for key, engine in provider._engines.items()
                    if provider._attack_committed.get(key) and engine.gs.turn > 3),
                   key=lambda engine: 6 - len(engine.gs.players[0].prize))
    assert len(terminal.gs.players[1].bench) == 1
    assert terminal.gs.players[1].bench[0].hp == 70


def test_nebula_resolves_damage_ko_prize_and_worst_opponent_promotion_before_value():
    decision, provider = _solve(NEBULA, opp_active_hp=200,
                                opp_bench=((STARYU, 70), (MEGA, 330)))
    assert decision.action.kind == "attack"
    promoted = [engine.gs.card_id(engine.gs.players[1].active.top)
                for key, engine in provider._engines.items()
                if provider._attack_committed.get(key) and engine.gs.turn > 3]
    assert MEGA in promoted
    assert max(6 - len(engine.gs.players[0].prize)
               for key, engine in provider._engines.items()
               if provider._attack_committed.get(key) and engine.gs.turn > 3) == 3
    assert decision.diagnostics["ledger"]["continuation"] >= 2.5
