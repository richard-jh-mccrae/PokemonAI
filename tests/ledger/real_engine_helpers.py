from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

from cgpy.schema import AreaType
from sim.scenario import BodySpec, deck, lock_main_allowances, observation, runtime, scenario


@dataclass(frozen=True, slots=True)
class UltraBallChainResult:
    choices: tuple[tuple[int, ...], ...]
    contexts: tuple[int, ...]
    complete: tuple[bool, ...]
    stop_reasons: tuple[str, ...]
    played_card_id: int
    discarded_card_ids: tuple[int, ...]
    fetched_card_id: int
    decision_ns: tuple[int, ...]
    total_ns: int
    observations: tuple[dict, ...]


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


def run_ultra_ball_chain(agent, *, compute_configuration=None, **scenario_kwargs):
    engine, agent_runtime = scenario(
        agent, compute_configuration=compute_configuration, **scenario_kwargs)
    lock_main_allowances(engine)
    observations = []
    decisions = []
    decision_ns = []
    contexts = []
    started = perf_counter_ns()

    current = observation(engine)
    observations.append(current)
    contexts.append(int(current["select"]["context"]))
    pending = engine.gs.pending
    decision_started = perf_counter_ns()
    decision = agent_runtime.decide(current)
    decision_ns.append(perf_counter_ns() - decision_started)
    decisions.append(decision)
    play = pending.options[decision.chosen[0]]
    played_card_id = engine.gs.card_id(engine.gs.players[0].hand[play["index"]])
    engine.step(list(decision.chosen))

    current = observation(engine)
    observations.append(current)
    contexts.append(int(current["select"]["context"]))
    decision_started = perf_counter_ns()
    decision = agent_runtime.decide(current)
    decision_ns.append(perf_counter_ns() - decision_started)
    decisions.append(decision)
    discarded_card_ids = tuple(
        option_card_id(engine, engine.gs.pending.options[index]) for index in decision.chosen)
    engine.step(list(decision.chosen))

    current = observation(engine)
    observations.append(current)
    contexts.append(int(current["select"]["context"]))
    decision_started = perf_counter_ns()
    decision = agent_runtime.decide(current)
    decision_ns.append(perf_counter_ns() - decision_started)
    decisions.append(decision)
    fetched = tuple(
        option_card_id(engine, engine.gs.pending.options[index]) for index in decision.chosen)
    total_ns = perf_counter_ns() - started

    return UltraBallChainResult(
        choices=tuple(tuple(decision.chosen) for decision in decisions),
        contexts=tuple(contexts),
        complete=tuple(bool(decision.complete) for decision in decisions),
        stop_reasons=tuple(
            str(decision.diagnostics["search"]["stop_reason"]) for decision in decisions),
        played_card_id=played_card_id,
        discarded_card_ids=discarded_card_ids,
        fetched_card_id=fetched[0],
        decision_ns=tuple(decision_ns),
        total_ns=total_ns,
        observations=tuple(observations),
    )


__all__ = (
    "BodySpec", "decide_option", "deck", "lock_main_allowances", "observation",
    "option_card_id", "run_ultra_ball_chain", "runtime", "scenario", "UltraBallChainResult",
)
