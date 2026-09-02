from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import importlib.util
from pathlib import Path

from cgpy.engine import Engine
from cgpy.options import pose_main
from cgpy.rng import SeededRng
from cgpy.search import export_token
from cgpy.state import PokemonInPlay

from common.engine import CgpyTransitionProvider
from common.runtime import build_runtime


REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class BodySpec:
    stack: tuple[int, ...]
    energies: tuple[int, ...] = ()
    tools: tuple[int, ...] = ()
    hp: int | None = None


def deck(agent: str) -> list[int]:
    return [int(value) for value in (
        REPO / "src" / "agents" / agent / "deck.csv"
    ).read_text(encoding="utf-8").split()[:60]]


def runtime(agent: str, cards, *, compute_configuration=None,
            provider_factory=CgpyTransitionProvider,
            decision_containment_seconds=None):
    path = REPO / "src" / "agents" / agent / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_{agent}_scenario", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return build_runtime(
        module.STRATEGY, cards, provider_factory=provider_factory,
        compute_configuration=compute_configuration,
        decision_containment_seconds=decision_containment_seconds)


def scenario(agent: str, *, me_active: BodySpec, me_bench=(), me_hand=(),
             me_discard=(), me_prizes=6, me_top=(), me_deck_count=None,
             them_active=None, them_bench=(), them_prizes=6,
             them_deck_count=None, turn=3, compute_configuration=None):
    cards = deck(agent)
    engine, _seat, _error = Engine.start(cards, cards, rng=SeededRng(71237))
    if engine is None:
        raise ValueError(f"agent {agent!r} deck failed cgpy validation")
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
        if not values:
            raise ValueError(f"seat {seat} deck has no remaining card {card_id}")
        return values.pop()

    def body(seat, value):
        stack = [take(seat, card_id) for card_id in value.stack]
        energy = [take(seat, card_id) for card_id in value.energies]
        tools = [take(seat, card_id) for card_id in value.tools]
        maximum = int(gs.stat(stack[-1]).hp)
        return PokemonInPlay(
            stack=stack, energy=energy, tools=tools,
            hp=maximum if value.hp is None else value.hp,
            max_hp=maximum, entered_turn=1)

    def populate(seat, active, bench, hand, discard, prizes, top=(), deck_count=None):
        board = gs.players[seat]
        board.active = body(seat, active)
        board.active_facedown = False
        board.bench = [body(seat, value) for value in bench]
        board.hand = [take(seat, card_id) for card_id in hand]
        board.discard = [take(seat, card_id) for card_id in discard]
        top_serials = [take(seat, card_id) for card_id in top]
        remaining = [serial for values in pools[seat].values() for serial in values]
        board.prize = remaining[:prizes]
        remaining = remaining[prizes:]
        if deck_count is not None:
            body_count = int(deck_count) - len(top_serials)
            if body_count < 0 or body_count > len(remaining):
                raise ValueError("scenario deck count cannot contain the declared top")
            board.deck = remaining[:body_count]
            board.discard.extend(remaining[body_count:])
        else:
            board.deck = remaining
        for serial in reversed(top_serials):
            board.deck.append(serial)
        board.poisoned = board.burned = board.asleep = False
        board.paralyzed = board.confused = False

    populate(0, me_active, me_bench, me_hand, me_discard, me_prizes,
             me_top, me_deck_count)
    populate(1, them_active or me_active, them_bench, (), (), them_prizes,
             deck_count=them_deck_count)
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
    return engine, runtime(agent, cards, compute_configuration=compute_configuration)


def observation(engine: Engine, seat: int = 0) -> dict:
    return engine.observation(seat, sbi_token=export_token(engine.gs))


def lock_main_allowances(engine: Engine, *, energy=True, supporter=True,
                         stadium=True, retreated=None, seat=0) -> None:
    gs = engine.gs
    gs.energy_attached = energy
    gs.supporter_played = supporter
    gs.stadium_played = stadium
    if retreated is not None:
        gs.retreated = retreated
    pose_main(gs, seat)


__all__ = ("BodySpec", "deck", "lock_main_allowances", "observation", "runtime", "scenario")
