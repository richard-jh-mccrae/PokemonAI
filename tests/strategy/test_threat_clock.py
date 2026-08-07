"""S1 — the Threat Clock (ADR-0045): closed-form energy-aware turns-until-opponent-KOs-my-body.

The defensive twin of the KO Race. For each opponent attacker FORM (a visible current form, a form
its line forward-evolves INTO, or a Read-predicted attacker) the fewest opponent turns until it can
afford AND land a KO of one of my bodies — modeling the ~1-Energy/turn attach clock (docs/rules.md
§4), evolution hops, promotion, and multi-hit accumulation (the Survival Window generalized). The
pure `threat_turns` is the arithmetic; the Mixin `_threat_clock` enumerates the live board.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    """The agent's real Pilot, built exactly like main.py (the canonical retest builder)."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


def _energies(n):
    return [{"id": 1}] * n


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_fully_powered_ohko_is_one_turn():
    """A form that can afford its attack NOW and one hit KOs my body threatens on the opponent's very
    next turn (1). Form = (cost, damage, energy_now, evo_hops, promo)."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(130, [(2, 200, 2, 0, 0)]) == 1


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_counts_the_energy_attach_clock():
    """A 1-Energy attacker needing a 3-Energy attack accrues Energy 1/turn; the attach on the firing
    turn counts, so it fires on turn 2."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(130, [(3, 200, 1, 0, 0)]) == 2


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_accumulates_multi_hit_like_survival_window():
    """A hit that doesn't KO accumulates over turns: 120 damage vs a 300-HP body = three hits = 3 turns."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(300, [(2, 120, 2, 0, 0)]) == 3


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_adds_evolution_and_promotion_surcharge():
    """A benched pre-evolution that must evolve one hop (concurrent with attaching to afford) then be
    promoted lands its KO one turn later than the same form with a free promotion (a Switch)."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(130, [(2, 270, 0, 1, 1)]) == 3    # max(1, evo 1, afford 2)=2, +promo 1, one hit
    assert threat_turns(130, [(2, 270, 0, 1, 0)]) == 2    # a Switch waives the promotion surcharge


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_takes_the_soonest_form():
    """The clock is the MINIMUM over all forms — the opponent's fastest route to my body's KO."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(130, [(3, 200, 0, 0, 0), (1, 150, 1, 0, 0)]) == 1


@pytest.mark.req("REQ-CLOCK-0001")
def test_threat_turns_ignores_forms_that_cannot_ko_and_empty():
    """A form dealing no damage to my body never enters (no divide-by-zero); no threatening form → None."""
    from common.strategy.objectives import threat_turns
    assert threat_turns(130, [(1, 0, 5, 0, 0)]) is None
    assert threat_turns(130, []) is None


# ---------------------------------------------------- the Mixin enumerator (`_threat_clock`, live board)

@pytest.mark.req("REQ-CLOCK-0002")
def test_threat_clock_reads_a_powered_active_that_ohkos_my_active():
    """A fully-powered opponent Active (Mega Starmie ex, 3 Energy) OHKOs my Cinderace (160 HP) with
    Nebula Beam (210) — the Threat Clock reads 1 (KO on their next turn)."""
    pilot = _shipped_pilot()
    my_active = {"id": 666, "hp": 160, "energies": []}
    opp = {"active": [{"id": 1031, "hp": 330, "energies": _energies(3)}], "bench": []}
    assert pilot._threat_clock(my_active, opp) == 1


@pytest.mark.req("REQ-CLOCK-0003")
def test_threat_clock_is_affordability_aware():
    """Energy affordability is charged: a 210-HP body facing a Mega Starmie ex whose only one-shot is
    the 3-Energy Nebula Beam reads 2 at 1 Energy and 1 at 3. `active_doomed` stays worst-case."""
    pilot = _shipped_pilot()
    my_body = {"id": 1031, "hp": 210, "energies": []}
    at_1 = {"active": [{"id": 1031, "hp": 330, "energies": _energies(1)}], "bench": []}
    at_3 = {"active": [{"id": 1031, "hp": 330, "energies": _energies(3)}], "bench": []}
    assert pilot._threat_clock(my_body, at_1) == 2       # survives next turn — can't pay the nuke yet
    assert pilot._threat_clock(my_body, at_3) == 1       # nuke online → doomed


@pytest.mark.req("REQ-CLOCK-0004")
def test_threat_clock_sees_the_forward_evolving_bench_threat():
    """A benched Staryu whose line forward-evolves into a Mega Starmie ex SHORTENS the clock — the
    Evolving Threat seen defensively, before it comes online."""
    pilot = _shipped_pilot()
    cind = {"id": 666, "hp": 160, "energies": []}
    active_only = {"active": [{"id": 676, "hp": 110, "energies": []}], "bench": []}
    with_staryu = {"active": [{"id": 676, "hp": 110, "energies": []}],
                   "bench": [{"id": 1030, "hp": 70, "energies": _energies(1)}]}
    base = pilot._threat_clock(cind, active_only)
    laid = pilot._threat_clock(cind, with_staryu)
    assert laid is not None and base is not None and laid < base


@pytest.mark.req("REQ-CLOCK-0005")
def test_threat_clock_promotion_surcharge_waived_by_a_switch():
    """A benched forward threat behind the promotion surcharge lands one turn SOONER when the opponent
    holds a Switch (revealed in their discard)."""
    pilot = _shipped_pilot()
    cind = {"id": 666, "hp": 160, "energies": []}
    board = {"active": [{"id": 676, "hp": 110, "energies": []}],
             "bench": [{"id": 1030, "hp": 70, "energies": _energies(1)}], "discard": []}
    with_switch = dict(board, discard=[{"id": 576}])     # 576 carries the `switch` Function Tag
    assert pilot._threat_clock(cind, with_switch) < pilot._threat_clock(cind, board)


@pytest.mark.req("REQ-CLOCK-0002")
def test_threat_clock_is_none_when_the_opponent_has_no_body():
    """No opponent Pokémon in play → no attacker form → the clock is None (nothing threatens)."""
    pilot = _shipped_pilot()
    assert pilot._threat_clock({"id": 666, "hp": 160, "energies": []},
                               {"active": [], "bench": []}) is None
