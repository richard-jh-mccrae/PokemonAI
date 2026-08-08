"""CombatMath — the KO oracle (ADR-0052): one closed-form home for damage/KO judgment, built from the
Stat Provider (ADR-0056), ``CardFunctions`` and the ``TransientTracker``, and handed per-decision
facts as call arguments. Never reads a Pilot or a Board, so it is testable standalone."""
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
    CardFactsMixin, EnergyMixin, ReachMixin,
    HarvestMixin, ForwardLineMixin, ClockMixin,
):
    """The oracle the Pilot builds once and delegates to. ``stats`` / ``functions`` / ``transients``
    may each be None and fail OPEN; ``effects`` None leaves the Attach Budget EMPTY (ADR-0067)."""

    def __init__(self, stats, functions, transients=None, effects=None):
        self.stats = stats
        self.functions = functions
        self._transients = transients
        self.effects = effects

    # `incoming_active_damage` and `active_doomed` were DELETED by POC-T1 (Issue #260) — one-line
    # spellings of `incoming`. The composed reads live at `StateModel.TheirSide.doomed`.
