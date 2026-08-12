"""Dependency-free mirrors of native engine enum values used by Bellman."""

# OptionType
_NUMBER = 0
_YES = 1
_NO = 2
_CARD = 3
_ATTACHED_TOOL = 4
_ENERGY_CARD = 5
_ENERGY = 6
_PLAY = 7
_ATTACH = 8
_EVOLVE = 9
_ABILITY = 10
_DISCARD_IN_PLAY = 11
_RETREAT = 12
_ATTACK = 13
_END = 14
_SKILL = 15
_SPECIAL_CONDITION = 16

# SelectContext
_MAIN = 0
_SETUP_ACTIVE = 1
_SETUP_BENCH = 2
_SWITCH = 3
_TO_ACTIVE = 4
_TO_HAND = 7
_DISCARD = 8
_DAMAGE = 15
_HEAL = 17
_ATTACH_FROM = 21
_DISCARD_ENERGY = 30
_IS_FIRST = 41
_MULLIGAN = 42

# AreaType
_DECK = 1
_HAND = 2
_ACTIVE = 4
_BENCH = 5
_LOOKING = 12

# LogType and card type
_MOVE_CARD = 6
_SUPPORTER = 3

# Scouting role derivation
_ENGINE_TAGS = frozenset({"energy_accel", "draw", "search", "dig"})
_UTILITY_TAGS = frozenset({"draw", "dig", "search", "supporter_tutor", "stall"})

__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
