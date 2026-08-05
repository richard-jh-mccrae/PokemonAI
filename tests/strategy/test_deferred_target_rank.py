"""**The D7 combination** — one sort key over an opponent-target menu: `value` ordered, `role_priority`
breaking exact ties (POC-T4/5, Issue #392 D7; the ranker lives in `common/board_choice.py`).

Its own file because the claim under test is a **property of an ordering**, not of a board: no pair of
rows whose `value` differs may ever be reordered by any declared role, for any menu and any role
table. `test_board_choice.py` beside it asserts the choice node's arithmetic against synthesized
boards; nothing here builds a board at all.

Issue #395 D1 rules the opponent role sheet an **ordinal priority, never a worth**, and it is forced
rather than chosen: `tests/strategy/test_needs.py`'s `for role in ROLE_TIER: assert
needs.SUPPLIES.get(role)` lint turns CI red for an opponent role with no honest slot to name. A
formula that let a role flip a real `value` difference would be treating that ordinal as a worth. So
the guarantee below is the semantics D1 demands, not a convenient tie-break — which is why it is
asserted as a property over generated menus rather than as the arithmetic that currently implements
it.

The measured population it targets: Issue #398 closed leaving **139 of 343 equal-prize groups
perfectly flat**, because `incoming` is a per-turn maximum so a non-leading body's removal Δ is a
**Structural Zero** at any resolution. Exact ties are what a tiebreak breaks.
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
    """**The D7 guarantee, asserted as a PROPERTY rather than as the arithmetic.**

    Issue #395 D1 rules the role sheet an *ordinal priority, never a worth*, forced by a shipped test
    (`tests/strategy/test_needs.py`'s `ROLE_TIER` ⊆ `SUPPLIES` lint). A formula that let a role flip a
    real `value` difference would be treating the ordinal as a worth. So the claim under test is not
    *"the quantum equals 0.5g"* — that is one implementation of it — but *"no pair differing in value
    is ever reordered by any declared role"*, over generated menus that put the largest positive role
    against the largest negative one on the tightest real gap."""
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
    """The other half of the same guarantee, and the measured population it targets: Issue #398 closed
    leaving **139 of 343 equal-prize groups perfectly flat**, because `incoming` is a per-turn maximum
    so a non-leading body's removal Δ is a Structural Zero at any resolution.

    When the menu draws no distinction at all, `currency.tiebreak_bonus` takes its ``1 / k`` fallback
    and the ordering becomes purely the ladder — which is exactly the bench case
    `_opponent_target_rows`' own comment says *"still ranks almost nothing."*"""
    ladder = ["prize_liability", "avoid", "fragile_preevo", "engine"]
    priorities = [matchup_plan.role_priority(r) for r in ladder]
    rows = _rows([2.0] * len(ladder), priorities)
    ordered = sorted(rows, key=bc.gust_rank_key(rows), reverse=True)
    assert [r["role_priority"] for r in ordered] == sorted(priorities, reverse=True)


def test_an_unrecognised_opponent_contributes_no_matchup_role_at_all():
    """γ=0 is not a case this key handles — it is a case it cannot see, and that is the design.
    `MatchupPlan.priority` is already γ-scaled for matchup provenance and γ-independent for general
    card facts, so an unrecognised opponent arrives here as a row whose `role_priority` is 0 and the
    ordering collapses to `value` alone. Asserted through the real `MatchupPlan` rather than by
    passing 0.0 by hand, so it is a fact about the shipped scaling."""
    plan = matchup_plan.build_matchup_plan(brief_roles={RIOLU: "prize_liability"}, gamma=0.0)
    assert plan.priority(RIOLU) == 0.0
    rows = _rows([2.0, 2.0], [plan.priority(RIOLU), plan.priority(MEGA_LUC)])
    key = bc.gust_rank_key(rows)
    assert key(rows[0]) == key(rows[1]) == 2.0


def test_the_absent_role_field_degrades_to_value_only_ordering():
    """`role_priority` is `pilot._opponent_target_rows`' own leg, shipped to `main` by Issue #395 D7
    while this ranker was being built. The 0.0 default is kept anyway and is not a placeholder: it is
    exactly what an UNROLED body contributes on a live row, so ONE key orders a menu whose rows carry
    the field and a menu whose rows do not, identically. That equivalence is what let this ranker be
    written and graded before that issue merged, and absorb its arrival with no edit."""
    rows = [{"value": 3.0}, {"value": 1.0}, {"value": 2.0}]
    assert [r["value"] for r in sorted(rows, key=bc.gust_rank_key(rows), reverse=True)] \
        == [3.0, 2.0, 1.0]


def test_the_role_span_is_DERIVED_from_the_registry_and_not_transcribed():
    """`ROLE_SPAN` is what normalises the ordinal into `[-1, 1]`, and it must move when the sheet does
    — Issue #395 D3/D4 did exactly that on `main` mid-build: `attacker` 50, `enabler` 40, a
    prize-gated `avoid`, and the table moved from a private dict to the public closed registry. A
    transcribed 100 would rot silently. The guard below is the one that matters: a registry gaining a
    LARGER magnitude must widen the span, or the `|role / span| <= 1` bound the D7 proof rests on
    stops holding."""
    real = {n: r.priority for n, r in matchup_plan.ROLE_REGISTRY.items()}
    assert bc.role_span() == max(abs(p) for p in real.values())
    # The future sheet is passed IN rather than monkey-patched over `matchup_plan`'s private table:
    # `ROLE_REGISTRY` is the shipped CLOSED vocabulary, so mutating it would be exactly the
    # cross-module private reach this repo forbids — and `role_span` takes the override for that
    # reason. Asserted in both directions, because only the widening one carries the D7 proof.
    assert bc.role_span(dict(real, a_future_role=-500)) == 500
    assert bc.role_span(dict(real, a_future_role=1)) == max(abs(p) for p in real.values())


def test_the_key_reads_the_SHIPPED_row_shape_not_only_a_synthetic_one():
    """**The half that only became assertable when Issue #395 D7 merged.** Every test above builds its
    own rows, which grades the arithmetic and not the CONTRACT — a key that read `row["priority"]`
    would pass all of them and order nothing on a live menu.

    So this asserts the field NAME against the shipped producer: `pilot._opponent_target_rows` writes
    `role_priority` beside `prize_advance` / `survival_shift` / `value`, and the ranker reads exactly
    those two. Read out of the Pilot's source rather than by building a board, because constructing a
    live opponent-target row needs a Read, a Brief and the KO clock — the seam this file deliberately
    does not reach into. The claim under test is a spelling agreement between two modules, and that is
    what a spelling check is for.

    ⚠️ Deliberately NOT asserted here: that a live row's `role_priority` takes any particular value.
    That is `tests/strategy/test_opponent_target_value.py`'s (Issue #395's own seam), and duplicating
    it would be a second opinion about someone else's ruling."""
    import inspect

    from common import pilot as pilot_mod

    src = inspect.getsource(pilot_mod.Pilot._opponent_target_rows)
    assert '"role_priority"' in src, "the shipped row no longer spells the field this key reads"
    assert '"value"' in src
    # …and the ranker reads those two names and no others off a row.
    key_src = inspect.getsource(bc.gust_rank_key)
    assert key_src.count('.get("value"') == 2          # the menu quantum, then the per-row leg
    assert '.get("role_priority", 0.0)' in key_src
