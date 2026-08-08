"""The suite's ONE hand-built cgpy `GameState` builder (Issue #435).

Every other cgpy assertion runs off a committed native trace or a seeded self-play game, which is
the right default: a trace is evidence and a hand-built board is only an argument. Text-derived
damage gates and cross-engine agreement on a card ABSENT from the corpus have no trace to stand on,
so they build a board here rather than in a second builder somewhere else.
"""
from __future__ import annotations

from collections.abc import Sequence

from cgpy.cards import CardDB
from cgpy.state import CardInstance, GameState, PlayerBoard, PokemonInPlay

DB = CardDB.load()


def make_state(attacker_cid: int, defender_cid: int,
               defender_bench: Sequence[int] = (),
               attacker_tools: Sequence[int] = (),
               attacker_bench: Sequence[int] = (),
               stadium: int | None = None) -> GameState:
    """Bodies are minted at PRINTED hp, the engine's own convention: a Stadium's HP static is a
    FLOATING render-time modifier that is never stored (hence `chain.stadium_hp_delta`)."""
    cards: dict[int, CardInstance] = {}
    serial = iter(range(3, 200))

    def mon(cid: int, owner: int) -> PokemonInPlay:
        s = next(serial)
        cards[s] = CardInstance(serial=s, card_id=cid, owner=owner)
        hp = DB.card(cid).hp
        return PokemonInPlay(stack=[s], hp=hp, max_hp=hp)

    gs = GameState(db=DB, cards=cards, players=[], rng=None)
    b0, b1 = PlayerBoard(), PlayerBoard()
    b0.active = mon(attacker_cid, 0)
    b1.active = mon(defender_cid, 1)
    b0.bench = [mon(c, 0) for c in attacker_bench]
    b1.bench = [mon(c, 1) for c in defender_bench]
    for cid in attacker_tools:                 # attached Pokémon Tool (owner = attacker)
        s = next(serial)
        cards[s] = CardInstance(serial=s, card_id=cid, owner=0)
        b0.active.tools.append(s)
    if stadium is not None:
        s = next(serial)
        cards[s] = CardInstance(serial=s, card_id=stadium, owner=0)
        gs.stadium = [s]
    gs.players = [b0, b1]
    gs.turn = 3
    gs.phase = "TURN"
    return gs
