"""The D7 combination — one sort key over an opponent-target menu: `value` ordered, `role_priority`
breaking exact ties (Issue #392 D7; the ranker lives in `common/board_choice.py`).

The claim is a property of an ORDERING, not of a board: Issue #395 D1 rules the role sheet an ordinal
priority, never a worth, so no pair whose `value` differs may be reordered by any declared role. That
is why it is asserted over generated menus rather than over the arithmetic that implements it, and
why nothing here builds a board at all.
"""
from __future__ import annotations

import pytest

from common import board_choice as bc
from common.scouting import matchup_plan

RIOLU, MEGA_LUC = 677, 678


def _rows(values, roles=()):
    roles = list(roles) + [0.0] * (len(values) - len(roles))
    return [{"id": i, "value": float(v), "role_priority": float(r)}
            for i, (v, r) in enumerate(zip(values, roles))]


def test_a_role_can_NEVER_reorder_two_rows_whose_value_differs():
    """Asserted as a PROPERTY, not as the arithmetic: not *"the quantum equals 0.5g"* but *"no pair
    differing in value is ever reordered by any declared role"* (Issue #395 D1)."""
    registry = {n: r.priority for n, r in matchup_plan.ROLE_REGISTRY.items()}
    span = bc.role_span()
    hi, lo = max(registry.values()), min(registry.values())
    for gap in (0.001, 0.01, 0.1, 0.5, 0.9, 1.0, 2.9):
        for base in (1.0, 2.0, 3.0):
            rows = _rows([base, base + gap], [hi, lo])          # worst case for the ordering
            key = bc.gust_rank_key(rows)
            assert key(rows[1]) > key(rows[0]), (gap, base, hi, lo, span)
            rows = _rows([base, base + gap], [lo, hi])          # and the aligned case
            assert key(rows[1]) > key(rows[0]), (gap, base, hi, lo, span)


def test_a_perfectly_flat_menu_orders_EXACTLY_by_the_role_ladder():
    """When the menu draws no distinction, `currency.tiebreak_bonus` takes its ``1 / k`` fallback and
    the ordering becomes purely the ladder — the flat-menu population Issue #398 left behind."""
    ladder = ["prize_liability", "avoid", "fragile_preevo", "engine"]
    priorities = [matchup_plan.role_priority(r) for r in ladder]
    rows = _rows([2.0] * len(ladder), priorities)
    ordered = sorted(rows, key=bc.gust_rank_key(rows), reverse=True)
    assert [r["role_priority"] for r in ordered] == sorted(priorities, reverse=True)


def test_an_unrecognised_opponent_contributes_no_matchup_role_at_all():
    """γ=0 is a case this key cannot SEE, by design: an unrecognised opponent arrives with
    `role_priority` 0 and the ordering collapses to `value`. Asserted through the real `MatchupPlan`."""
    plan = matchup_plan.build_matchup_plan(brief_roles={RIOLU: "prize_liability"}, gamma=0.0)
    assert plan.priority(RIOLU) == 0.0
    rows = _rows([2.0, 2.0], [plan.priority(RIOLU), plan.priority(MEGA_LUC)])
    key = bc.gust_rank_key(rows)
    assert key(rows[0]) == key(rows[1]) == 2.0


def test_the_absent_role_field_degrades_to_value_only_ordering():
    """The 0.0 default is not a placeholder — it is exactly what an UNROLED body contributes, so ONE
    key orders a menu carrying `role_priority` and one that does not, identically."""
    rows = [{"value": 3.0}, {"value": 1.0}, {"value": 2.0}]
    assert [r["value"] for r in sorted(rows, key=bc.gust_rank_key(rows), reverse=True)] \
        == [3.0, 2.0, 1.0]


def test_the_role_span_is_DERIVED_from_the_registry_and_not_transcribed():
    """`ROLE_SPAN` normalises the ordinal into `[-1, 1]` and must move when the sheet does: a registry
    gaining a LARGER magnitude must widen it, or the `|role / span| <= 1` D7 bound stops holding."""
    real = {n: r.priority for n, r in matchup_plan.ROLE_REGISTRY.items()}
    assert bc.role_span() == max(abs(p) for p in real.values())
    # The future sheet is passed IN rather than monkey-patched: `ROLE_REGISTRY` is the shipped CLOSED
    # vocabulary. Both directions, because only the widening one carries the D7 proof.
    assert bc.role_span(dict(real, a_future_role=-500)) == 500
    assert bc.role_span(dict(real, a_future_role=1)) == max(abs(p) for p in real.values())


def test_the_key_reads_the_SHIPPED_row_shape_not_only_a_synthetic_one():
    """The CONTRACT, not the arithmetic: a key reading `row["priority"]` would pass every test above
    and order nothing live. A spelling agreement between two modules, so it is a spelling check."""
    import inspect

    from common import pilot as pilot_mod

    src = inspect.getsource(pilot_mod.Pilot._opponent_target_rows)
    assert '"role_priority"' in src, "the shipped row no longer spells the field this key reads"
    assert '"value"' in src
    # …and the ranker reads those two names and no others off a row.
    key_src = inspect.getsource(bc.gust_rank_key)
    assert key_src.count('.get("value"') == 2          # the menu quantum, then the per-row leg
    assert '.get("role_priority", 0.0)' in key_src
