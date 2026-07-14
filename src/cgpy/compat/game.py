"""``cg.game`` twin: re-exports the cgpy battle singleton (ADR-0059 M3)."""
from ..game import (Battle, StartData, battle_finish, battle_select,  # noqa: F401
                    battle_start, visualize_data)

__all__ = ["Battle", "StartData", "battle_start", "battle_finish", "battle_select",
           "visualize_data"]
