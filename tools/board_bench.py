"""Time BoardState.advance against full rebuilds over a synthetic in-search reprint sequence.

Each step deep-copies the previous printout and applies one board-sized mutation (damage, a
draw, an attach, a turn flag), which is the change profile of one search edge. Three pipelines
consume the identical sequence: `BoardState.root` per step (rebuild everything), the
`advance` chain (reuse untouched pieces), and `DecisionState.from_observation` + `plan_key`
(the incumbent per-node cost). Run: `python -m tools.board_bench --steps 300`."""
from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common.board import BoardState                      # noqa: E402
from common.state import DecisionState                   # noqa: E402

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
        body["hp"] = max(10, body["hp"] - 30)
    elif kind == 1:
        me["hand"].append({"id": IDS[step % len(IDS)], "serial": 2000 + step, "playerIndex": 0})
        me["handCount"] += 1
        me["deckCount"] -= 1
    elif kind == 2:
        me["active"][0]["energies"].append(1)
    elif kind == 3:
        them["active"][0]["hp"] = max(10, them["active"][0]["hp"] - 30)
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
    BoardState.root(printouts[0], decklist=DECK).key

    start = time.perf_counter()
    roots = [BoardState.root(printout, decklist=DECK) for printout in printouts]
    for board in roots:
        board.key
    root_ms = (time.perf_counter() - start) * 1000 / len(printouts)

    start = time.perf_counter()
    chain = [BoardState.root(printouts[0], decklist=DECK)]
    chain[0].key
    for printout in printouts[1:]:
        chain.append(chain[-1].advance(printout))
        chain[-1].key
    advance_ms = (time.perf_counter() - start) * 1000 / len(printouts)

    start = time.perf_counter()
    for printout in printouts:
        DecisionState.from_observation(printout, deck=DECK, deck_name="bench").plan_key
    decision_ms = (time.perf_counter() - start) * 1000 / len(printouts)

    mismatch = sum(1 for fresh, stepped in zip(roots, chain)
                   if fresh != stepped or fresh.key != stepped.key)
    print(f"steps                    {len(printouts)}")
    print(f"BoardState.root          {root_ms:8.3f} ms/step")
    print(f"BoardState.advance       {advance_ms:8.3f} ms/step   ({root_ms / advance_ms:4.1f}x vs root)")
    print(f"DecisionState + plan_key {decision_ms:8.3f} ms/step   ({decision_ms / advance_ms:4.1f}x vs advance)")
    print(f"advance == root mismatches: {mismatch}")
    return 1 if mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
