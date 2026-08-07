"""CombatMath — the KO oracle (ADR-0052): one closed-form home for damage/KO judgment.

Constructed from the knowledge seams — the Stat Provider (ADR-0056), ``CardFunctions``, and the
match-scoped ``TransientTracker`` — and handed per-decision facts (the damage context, the
opponent's bench) as explicit call arguments. Composes the pure ``damage.py`` seam; never reads
a Pilot or a Board, so it is testable standalone and injectable wherever combat judgment is
needed (the doctrines' future explicit dependency).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import NamedTuple

from common.board_cards import body_unit_codes   # the ONE read of a body's attached Energy UNITS
from common.board_cards import card_id as body_card_id   # …and the ONE read of a card ENTRY's id
from common.deck_odds import draw_hit_probability
from common.strategy.context import KO_SCORE
from common.strategy.damage import compute_active_damage, wr_adjust

# --- the families (`common/strategy/combat_math/`) ---
from common.strategy.combat_math.budget import (_RECUR_RELOAD_CAP, DISCARD_SUPPLY, _UNIT_COLOURS, WILD_CODE,
                                                unit_colours, units_for_codes, AttachUnit, Budget, _AttachCtx,
                                                _Contribution, _pay_best_p, _can_pay, _matched_slots)  # noqa: F401
from common.strategy.combat_math.cards import CardFactsMixin
from common.strategy.combat_math.clocks import ClockMixin, SurvivalClock  # noqa: F401
from common.strategy.combat_math.energy import EnergyMixin, _ACCEL_TAGS  # noqa: F401
from common.strategy.combat_math.forward import ForwardLineMixin, LinePrize  # noqa: F401
from common.strategy.combat_math.harvest import HarvestMixin, _BENCH_SNIPE, _BENCH_SNIPE_CAP  # noqa: F401
from common.strategy.combat_math.policy import (HARVEST_POSSIBLE, HARVEST_UNAVOIDABLE, UNCHARGED,
                                                CURRENT_FORMS_ONLY)  # noqa: F401
from common.strategy.combat_math.reach import ReachMixin, _EFFICIENCY  # noqa: F401

class CombatMath(
    # the questions, cheapest first: what a card says, what pays for it, what that reaches
    CardFactsMixin, EnergyMixin, ReachMixin,
    # …and the compositions over them
    HarvestMixin, ForwardLineMixin, ClockMixin,
):
    """The oracle instance the Pilot builds once and delegates to.

    Args:
        stats: the Stat Provider (``get``/``attack``/forward queries), or None (stat-blind —
            every read fails open to 0/None exactly like a stat-blind Pilot).
        functions: ``CardFunctions`` (defender-side prevention tags), or None.
        transients: the match-scoped ``TransientTracker`` (live next-turn grants keyed by body
            serial, ADR-0033), or None — no live shields/locks are then modeled.
        effects: ``CardEffects`` (ADR-0032 Effect Clauses), or None — the Attach Budget then reads
            no yields at all and is empty (fail-CLOSED, ADR-0067).
    """

    def __init__(self, stats, functions, transients=None, effects=None):
        self.stats = stats
        self.functions = functions
        self._transients = transients
        self.effects = effects

    # `incoming_active_damage` and `active_doomed` were DELETED by POC-T1 (Issue #260). The fold
    # turned them into one-line spellings of `incoming` at the `UNCHARGED` policy, and the SAME
    # track's census migration moved their only production consumers onto the snapshot — so what the
    # fold left behind was two zero-caller delegates. Keeping them would have contradicted the
    # deletion rule this track applied to every other unconsumed surface, and a second spelling of a
    # question is the drift hazard ADR-0087 charges for whether or not anything calls it today. The
    # composed reads live where their consumers are: `StateModel.TheirSide.doomed` and, for the
    # current-form damage `Board` exposes, `theirs.incoming(..., forward_ids=CURRENT_FORMS_ONLY)`.
