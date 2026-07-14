"""``cg``-shaped package surface backed by cgpy (ADR-0059 M3).

`cgpy.alias.install()` maps this package over ``sys.modules["cg"]`` (and its submodules),
so every consumer of the native wrapper — agents' ``from cg.api import all_attack``, the
harness's ``from cg.game import battle_start`` — runs on the pure-Python twin unchanged.
"""
from . import api, game, sim, utils

__all__ = ["api", "game", "sim", "utils"]
