"""Pair incremental ObservationState construction against full rebuilds on identical frames.

Each step deep-copies the previous printout and applies one board-sized mutation (damage, a
draw, an attach, a turn flag), which is the change profile of one search edge. Three pipelines
consume the identical sequence: `ObservationStateBuilder.root` per step (rebuild everything), the
`advance` chain (reuse untouched pieces). Run: `python tools/observation_bench.py --steps 300`."""
from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.observation import ObservationStateBuilder               # noqa: E402

IDS = (66, 112, 119, 120, 121, 140)
DECK = tuple(IDS) * 10


def _body(card_id, serial, hp=120):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": hp, "maxHp": 120,
            "appearThisTurn": False, "energies": [], "energyCards": [], "tools": [],
            "preEvolution": []}


def _player(seat, own):
    hand = [{"id": IDS[i % len(IDS)], "serial": 800 + i, "playerIndex": seat} for i in range(6)]
    return {"active": [_body(IDS[0], 10 * seat + 1)],
            "bench": [_body(IDS[i], 10 * seat + 2 + i) for i in range(1, 5)],
            "benchMax": 5, "deckCount": 30, "prize": [None] * 6,
            "discard": [{"id": IDS[1], "serial": 900 + seat, "playerIndex": seat}],
            "handCount": len(hand), "hand": hand if own else None,
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


def _printout():
    return {"select": {"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
                       "remainDamageCounter": 0, "remainEnergyCost": 0,
                       "option": [{"type": 7, "index": i} for i in range(4)], "deck": None,
                       "contextCard": None, "effect": None},
            "logs": [],
            "current": {"turn": 5, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
                        "stadiumPlayed": False, "energyAttached": False, "retreated": False,
                        "result": None, "stadium": [], "looking": None,
                        "players": [_player(0, True), _player(1, False)]}}


def _mutate(printout, step):
    """One search-edge-sized change, cycling through the common kinds."""
    me, them = printout["current"]["players"]
    kind = step % 5
    if kind == 0:
        body = me["bench"][step % 4]
        # Cycle rather than floor: a floored value stops mutating and fakes cheap no-op edges.
        body["hp"] = body["hp"] - 30 if body["hp"] > 30 else 120
    elif kind == 1:
        me["hand"].append({"id": IDS[step % len(IDS)], "serial": 2000 + step, "playerIndex": 0})
        me["handCount"] += 1
        me["deckCount"] -= 1
    elif kind == 2:
        me["active"][0]["energies"].append(1)
    elif kind == 3:
        active = them["active"][0]
        active["hp"] = active["hp"] - 30 if active["hp"] > 30 else 120
    else:
        printout["current"]["supporterPlayed"] = not printout["current"]["supporterPlayed"]
    return printout


def _sequence(steps):
    printouts = [_printout()]
    for step in range(steps):
        printouts.append(_mutate(copy.deepcopy(printouts[-1]), step))
    return printouts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=300)
    args = parser.parse_args(argv)
    printouts = _sequence(args.steps)
    # Warm the process-wide card store and import machinery so no pipeline pays it in its timing.
    builder = ObservationStateBuilder(DECK)
    builder.root(printouts[0]).position_key

    start = time.perf_counter()
    roots = [builder.root(printout) for printout in printouts]
    for board in roots:
        board.key
    root_ms = (time.perf_counter() - start) * 1000 / len(printouts)

    start = time.perf_counter()
    chain = [builder.root(printouts[0])]
    deltas = []
    chain[0].key
    for printout in printouts[1:]:
        child, delta = builder.advance(chain[-1], printout)
        chain.append(child)
        deltas.append(delta)
        chain[-1].key
    advance_ms = (time.perf_counter() - start) * 1000 / len(printouts)

    mismatch = sum(1 for fresh, stepped in zip(roots, chain)
                   if fresh != stepped or fresh.key != stepped.key)
    print(f"steps                    {len(printouts)}")
    print(f"ObservationStateBuilder.root    {root_ms:8.3f} ms/step")
    print(f"ObservationStateBuilder.advance {advance_ms:8.3f} ms/step   ({root_ms / advance_ms:4.1f}x vs root)")
    print(f"advance == root mismatches: {mismatch}")
    print(f"mean changed parts:         {sum(len(delta.parts) for delta in deltas) / len(deltas):8.3f}")
    return 1 if mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
