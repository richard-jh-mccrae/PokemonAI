"""The suite's ONE hand-built cgpy `GameState` builder.

Every other cgpy assertion in the suite runs off a committed native trace (`tests/parity/
test_replay_fixtures.py`) or a seeded self-play game, which is the right default: a trace is
evidence and a hand-built board is only an argument. But two kinds of claim have no trace to stand
on, and both need a board anyway —

* **text-derived damage gates** (`tests/parity/test_damage_goldens.py`), where the card pool carries
  a printed rule no captured game happens to exercise;
* **cross-engine agreement on a card absent from the corpus**
  (`tests/parity/test_stadium_static_cross_engine.py`), where the whole point is that no trace
  exists — Lively Stadium (1251) appears in 0 of the 377 committed traces, which is exactly why the
  twin was allowed to not implement it for as long as it did.

`make_state` used to live inside `test_damage_goldens.py`, whose docstring claimed it as *"the
suite's only hand-built cgpy `GameState` — so text-derived damage gates live here rather than in a
second builder somewhere else."* That invariant is worth keeping and the second caller does not
change it; what changes is where the one builder lives, so a second module can reach it without a
second copy existing. Issue #435.
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
    """A minimal two-sided board: one Active each, optional benches, tools and Stadium.

    Bodies are minted at PRINTED hp (``hp = max_hp = stat.hp``), which is the engine's own
    convention and the reason `chain.stadium_hp_delta` exists: a Stadium's HP static is a FLOATING
    render-time modifier that is never stored, so a body under Gravity Mountain still carries its
    printed maximum here and renders 30 lower (`cgpy/render.py:pokemon_dict`).

    ``stadium`` puts that card into the shared `GameState.stadium` zone as a real `CardInstance`,
    owned by seat 0 — ownership only decides whose discard a displacement writes, and nothing here
    displaces. The card's own text decides who it reaches: every `stadium_static` in the pool is
    ``symmetric: true`` (`src/common/card_effects.json`), and `chain.stadium_hp_delta` takes a body
    rather than a seat, so both-sides application is structural rather than configured.
    """
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
