from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import importlib.util
from pathlib import Path

from cgpy.engine import Engine
from cgpy.options import pose_main
from cgpy.rng import SeededRng
from cgpy.schema import AreaType
from cgpy.search import export_token
from cgpy.state import PokemonInPlay

from common.engine import CgpyTransitionProvider
from common.runtime import build_runtime


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class BodySpec:
    stack: tuple[int, ...]
    energies: tuple[int, ...] = ()
    tools: tuple[int, ...] = ()
    hp: int | None = None


def deck(agent):
    return [int(value) for value in (
        ROOT / "src" / "agents" / agent / "deck.csv"
    ).read_text(encoding="utf-8").split()[:60]]


def runtime(agent, cards):
    path = ROOT / "src" / "agents" / agent / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_{agent}_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return build_runtime(module.STRATEGY, cards, provider_factory=CgpyTransitionProvider)


def scenario(agent, *, me_active, me_bench=(), me_hand=(), me_discard=(),
             me_prizes=6, me_top=(), them_active=None, them_bench=(),
             them_prizes=6, turn=3):
    cards = deck(agent)
    engine, _seat, _error = Engine.start(cards, cards, rng=SeededRng(71237))
    assert engine is not None
    gs = engine.gs
    pools = []
    for seat in (0, 1):
        pool = defaultdict(list)
        for serial, instance in gs.cards.items():
            if instance.owner == seat:
                pool[instance.card_id].append(serial)
        pools.append(pool)

    def take(seat, card_id):
        values = pools[seat][card_id]
        assert values, f"seat {seat} deck has no remaining card {card_id}"
        return values.pop()

    def body(seat, value):
        stack = [take(seat, card_id) for card_id in value.stack]
        energy = [take(seat, card_id) for card_id in value.energies]
        tools = [take(seat, card_id) for card_id in value.tools]
        maximum = int(gs.stat(stack[-1]).hp)
        return PokemonInPlay(
            stack=stack, energy=energy, tools=tools,
            hp=maximum if value.hp is None else value.hp,
            max_hp=maximum, entered_turn=1,
        )

    def populate(seat, active, bench, hand, discard, prizes, top=()):
        board = gs.players[seat]
        board.active = body(seat, active)
        board.active_facedown = False
        board.bench = [body(seat, value) for value in bench]
        board.hand = [take(seat, card_id) for card_id in hand]
        board.discard = [take(seat, card_id) for card_id in discard]
        top_serials = [take(seat, card_id) for card_id in top]
        remaining = [serial for values in pools[seat].values() for serial in values]
        board.prize = remaining[:prizes]
        board.deck = remaining[prizes:]
        for serial in reversed(top_serials):
            board.deck.append(serial)
        board.poisoned = board.burned = board.asleep = False
        board.paralyzed = board.confused = False

    populate(0, me_active, me_bench, me_hand, me_discard, me_prizes, me_top)
    populate(1, them_active or me_active, them_bench, (), (), them_prizes)
    gs.turn = turn
    gs.first_player = 0
    gs.turn_action_count = 0
    gs.supporter_played = False
    gs.stadium_played = False
    gs.energy_attached = False
    gs.retreated = False
    gs.result = -1
    gs.phase = "TURN"
    gs.phase_data = {"seat": 0}
    gs.pending = None
    gs.frames = []
    gs.pending_triggers = []
    gs.outbox = [[], []]
    gs.outbox_god = []
    pose_main(gs, 0)
    return engine, runtime(agent, cards)


def observation(engine, seat=0):
    return engine.observation(seat, sbi_token=export_token(engine.gs))


def decide_option(engine, agent_runtime, seat=0):
    pending = engine.gs.pending
    decision = agent_runtime.decide(observation(engine, seat))
    chosen = list(decision.chosen)
    option = pending.options[chosen[0]] if chosen else None
    engine.step(chosen)
    return decision, option


def option_card_id(engine, option, seat=0):
    board = engine.gs.players[option.get("playerIndex", seat)]
    area = option.get("area")
    index = option.get("index")
    if area == int(AreaType.DECK):
        serial = board.deck[index]
    elif area == int(AreaType.HAND):
        serial = board.hand[index]
    elif area == int(AreaType.DISCARD):
        serial = board.discard[index]
    elif area == int(AreaType.LOOKING):
        serial = engine.gs.looking[index]
    elif area == int(AreaType.ACTIVE):
        serial = board.active.top
    elif area == int(AreaType.BENCH):
        serial = board.bench[index].top
    else:
        return None
    return engine.gs.card_id(serial)


def lock_main_allowances(engine, *, energy=True, supporter=True, stadium=True,
                         retreated=None, seat=0):
    gs = engine.gs
    gs.energy_attached = energy
    gs.supporter_played = supporter
    gs.stadium_played = stadium
    if retreated is not None:
        gs.retreated = retreated
    pose_main(gs, seat)


__all__ = (
    "BodySpec", "decide_option", "deck", "lock_main_allowances", "observation",
    "option_card_id", "runtime", "scenario",
)
