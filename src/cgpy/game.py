"""Module-level battle singleton mirroring ``cg/game.py`` (ADR-0059 M3).

The drop-in engine surface for the existing harness: ``battle_start(deck0, deck1)`` returns
``(obs, StartData)`` with an attribute-compatible StartData; ``battle_select`` raises the
same exception classes as the native shim (ValueError on a malformed list, IndexError — via
``SelectionError`` — on an illegal selection); ``visualize_data()`` returns the god-frame
JSON string ({current, selected, logs} per posed select, ``selected`` riding one frame
behind the choice it answers, log types as CamelCase name-strings — probed from native
traces, docs/pyeng/determinism.md §7).

Each observation's ``search_begin_input`` carries the cgpy state token
(`cgpy.search.export_token`): engine internals a lone observation cannot express, so a
search seeded from this obs is exact — the cgpy analogue of the native blob. Randomness is
cgpy-owned (`SeededRng`): unseeded by default like the native engine; set ``CGPY_SEED`` for
reproducible self-play (a property the native engine never had).
"""
from __future__ import annotations

import json
import os

from . import search
from .engine import Engine
from .rng import SeededRng
from .schema import LogType


class StartData:
    """Attribute-compatible stand-in for ``cg.sim.StartData`` (the ctypes struct)."""

    def __init__(self, battlePtr, errorPlayer: int, errorType: int):
        self.battlePtr = battlePtr
        self.errorPlayer = errorPlayer
        self.errorType = errorType


class Battle:
    """Mirrors ``cg.sim.Battle``: the per-process singleton holder."""
    engine: Engine | None = None
    obs: dict | None = None
    viz: list[dict] = []
    prev_choice: list[int] | None = None


def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


_LOG_NAMES = {int(v): _camel(v.name) for v in LogType}


def _god_logs(gs) -> list[dict]:
    out = []
    for entry in gs.outbox_god:
        e = dict(entry)
        e["type"] = _LOG_NAMES.get(e.get("type"), e.get("type"))
        out.append(e)
    gs.outbox_god = []
    return out


def _observation() -> dict:
    eng = Battle.engine
    seat = eng.select_seat if eng.select_seat is not None else 0
    Battle.viz.append({"current": eng.god_frame(),
                       "selected": Battle.prev_choice,
                       "logs": _god_logs(eng.gs)})
    Battle.obs = eng.observation(viewer=seat, sbi_token=search.export_token(eng.gs))
    return Battle.obs


def battle_start(deck0: list[int], deck1: list[int]) -> tuple[dict | None, StartData]:
    """Start a battle; ``(None, StartData)`` when a deck is illegal (that seat loses)."""
    if len(deck0) != 60 or len(deck1) != 60:
        raise ValueError("The deck must contain 60 cards.")
    seed = os.environ.get("CGPY_SEED")
    rng = SeededRng(int(seed)) if seed else SeededRng()
    engine, err_player, err_type = Engine.start(list(deck0), list(deck1), rng=rng)
    if engine is None:
        Battle.engine = None
        return (None, StartData(None, err_player, err_type))
    Battle.engine = engine
    Battle.viz = []
    Battle.prev_choice = None
    return (_observation(), StartData(1, -1, 0))


def battle_finish() -> None:
    """End the battle and release the singleton."""
    Battle.engine = None
    Battle.obs = None


def battle_select(select_list: list[int]) -> dict:
    """Apply a selection and return the next observation (native exception classes)."""
    if not isinstance(select_list, list) or not all(isinstance(i, int) for i in select_list):
        raise ValueError("select_list is not list[int]")
    if Battle.engine is None:
        raise ValueError("battle_ptr broken.")
    Battle.engine.step(select_list)        # SelectionError is an IndexError, as native
    Battle.prev_choice = [int(i) for i in select_list]
    return _observation()


def visualize_data() -> str:
    """The god-frame stream for the current battle, as a JSON string."""
    return json.dumps(Battle.viz, ensure_ascii=False)
