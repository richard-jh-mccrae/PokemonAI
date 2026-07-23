"""The closed, extensible Category vocabulary -- the *human* axis of a Correction.

See ``tools/train/CONTEXT.md`` (Category) and ADR-0009. Strategic error kinds, not
mechanical (the engine SelectContext is captured separately on the Decision).
Extended *by process*: when a real blunder doesn't fit, add a term here (like the
closed Role / Plan vocabularies grow).
"""
from __future__ import annotations

CATEGORIES: tuple[str, ...] = (
    # combat & prizes
    "missed_win",            # a winning/closing line was available, not taken
    "missed_ko",             # a valuable KO (threat/engine Pokemon) available, not taken
    "bad_target",            # attacked or effect-targeted wrong Pokemon
    "wrong_attack",          # used wrong attack (a better one served turn's need)
    "prize_mismanagement",   # poor prize-trade math (traded down, wrong prizes)
    # resources
    "misattachment",         # energy/tool placed on wrong Pokemon
    "wasted_resource",       # supporter/item/ability/card spent for little/negative value
    "wrong_supporter",       # played wrong supporter (a better one served turn's need)
    # tempo & board
    "slow_setup",            # too slow developing win-condition
    "missed_evolution",      # a beneficial evolution was available, not made (evolve when able)
    "overextension",         # over-committed board -> prize liability / sweep exposure
    # positioning & reads
    "bad_retreat",           # wrong retreat call (when / whether / where)
    "ignored_threat",        # failed to play around known incoming threat (defensive)
    "missed_disruption",     # failed to proactively deny opponent (hammer energy, Boss the pre-evo)
    # catch-all
    "sequencing_error",      # right actions, wrong order (locked out a better line)
    "other",                 # escape hatch; forces a good rationale, flags a vocab gap
    # machine-only (ADR-0053 WP3 / design s3a §D4): the value labeler's engine-measured
    # disagreement kind — a decision whose value-net P(win) fell ≥ θ below the expert's best
    # option. NEVER authored by a human (they pick a strategic category above); keeping it
    # separate keeps machine records filterable in every report and off the `other` vocab-gap signal.
    "value_delta",
)


def is_valid_category(category: str) -> bool:
    """True iff ``category`` is a member of the closed vocabulary."""
    return category in CATEGORIES
