"""The `_EVOLVES_FROM` target select (ctx 18) — `Pilot._evolve_target_tactical` (Issue #417).

Salvatore (1189) puts an Ability-less evolution from the deck onto one of my bodies. The engine poses
`_EVOLVES_TO` (19 — which deck copy) and then this one: WHICH body becomes the Mega Starmie ex. Every
ctx-18 option carries `_CARD`, never `_EVOLVE`, so `_evolve_decision`'s gate abstained on all of them
and the pick fell out of `_order_key`'s fingerprint.

Validation is BY CONSTRUCTION: zero ruled frames carry ctx 18, so the seven real parity boards serve
as fixtures with their recorded ``choice`` DISCARDED — those traces run a randomised policy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from common.evolve_value import EvolveInputs, evolve_value
from common.strategy.context import (_ACTIVE, _BENCH, _CARD, _DECK, _EVOLVE, _EVOLVES_FROM,
                                     _EVOLVES_TO, _MAIN)
from pilot_helpers import card_opt, parity_frame, parity_selects

REPO = Path(__file__).resolve().parents[2]

SALVATORE = 1189       # Supporter — search the deck for an Ability-less evolution, put it on a body
STARYU = 1030          # Basic, 70 HP, Water Gun {W} 20
M_STARMIE = 1031       # Mega Starmie ex — Stage 1 from Staryu, 330 HP, Nebula Beam ●●● 210

#: ``(trace, frame)`` of every ctx-18 step in the committed parity corpus; widths 1/2/3.
#: `ms_mirror_1001` f15 is the only three-wide menu, so it is the discriminating board.
REAL_BOARDS = [("ms_mirror_1001", 15), ("ms_mirror_1001", 20), ("v2_ms_dx_5401", 42),
               ("v2_ms_mirror_5000", 15), ("v2_ms_mirror_5000", 39), ("v2_ms_mirror_5000", 106),
               ("v2_ms_ml_5301", 17)]
WIDEST = ("ms_mirror_1001", 15)


def _shipped_pilot():
    """mega_starmie's REAL Pilot, every kill-switch at its shipped default, as `main.py` builds it."""
    import sys
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


def _terms(pilot, frame: dict):
    """``[term, …]`` per option of a ctx-18 frame, plus the Pilot's pick."""
    obs = frame["obs"]
    sel = obs["select"]
    board = pilot._board(obs)
    return ([pilot._evolve_target_tactical(obs, sel, board, o, pilot._context(obs, sel, board, o))
             for o in sel["option"]], pilot.explain(obs).chosen)


def test_the_constants_land_where_the_engine_enum_says_they_should():
    from cg.api import SelectContext
    assert _EVOLVES_FROM == int(SelectContext.EVOLVES_FROM) == 18
    assert _EVOLVES_TO == int(SelectContext.EVOLVES_TO) == 19


def test_corpus_ctx18_census_is_what_the_equation_was_built_on():
    """The option TYPE is why the select was unreachable: `_evolve_decision` and
    `_prefer_soonest_arming_evolve` both gate on ``type == _EVOLVE``, and these options are `_CARD`."""
    steps = parity_selects(_EVOLVES_FROM)
    widths, ctx_cards, types, areas = {}, set(), set(), set()
    for _trace, _index, sel in steps:
        widths[len(sel["option"])] = widths.get(len(sel["option"]), 0) + 1
        assert (sel.get("minCount"), sel.get("maxCount")) == (1, 1)
        ctx_cards.add((sel.get("contextCard") or {}).get("id"))
        types.update(o["type"] for o in sel["option"])
        areas.update(o.get("area") for o in sel["option"])
    assert len(steps) == 7
    assert widths == {1: 3, 2: 3, 3: 1}
    assert ctx_cards == {M_STARMIE}
    assert types == {_CARD} and _EVOLVE not in types
    assert areas == {_ACTIVE, _BENCH}


def test_corpus_ctx19_is_moot_because_every_menu_is_copies_of_one_species():
    """Picking among interchangeable copies has no strategic content, so no ctx-19 term was built.
    This is the tripwire: a menu spanning two target species fails it, and ctx 19 stops being moot."""
    steps = parity_selects(_EVOLVES_TO)
    multi_species = []
    for trace, index, sel in steps:
        assert {o.get("area") for o in sel["option"]} == {_DECK}
        deck = sel.get("deck") or []
        ids = {(deck[o["index"]] or {}).get("id") for o in sel["option"]
               if 0 <= o["index"] < len(deck)}
        if len(ids) > 1:
            multi_species.append((trace, index, sorted(ids)))
    assert len(steps) == 20
    assert multi_species == []


def test_no_ruled_frame_carries_ctx_18_or_19():
    """Why validation here is by construction — and red the moment the first ruling lands."""
    import sys
    sys.path.insert(0, str(REPO / "tests"))
    from corpus_helpers import corpus_index
    ruled = {(c.decision or {}).get("select_context") for c in corpus_index().values()}
    assert "EvolvesFrom" not in ruled and "EvolvesTo" not in ruled


@pytest.mark.parametrize("trace,index", REAL_BOARDS, ids=lambda v: str(v))
def test_every_real_board_prices_every_option_through_the_equation(trace, index):
    """The term must be `evolve_value`'s total and nothing else — no prize leg, area bonus or
    card-id special case."""
    pilot = _shipped_pilot()
    frame = parity_frame(trace, index)
    obs = frame["obs"]
    sel = obs["select"]
    board = pilot._board(obs)
    target_cid = sel["contextCard"]["id"]
    for option in sel["option"]:
        raw = pilot._option_pokemon(obs, sel, option)
        body, result, _ = pilot._evolve_substitution(obs, board, raw, target_cid,
                                                     is_active=(option.get("area") == _ACTIVE))
        expected = evolve_value(EvolveInputs(body=body, result=result)).total
        ctx = pilot._context(obs, sel, board, option)
        assert pilot._evolve_target_tactical(obs, sel, board, option, ctx) == expected
        # Salvatore's clause carries `no_ability: true`, so the income legs are structurally zero
        # here and the whole term is the deploy delta.
        assert expected == result.deploy() - body.deploy()


def test_the_widest_real_board_separates_the_bodies_the_string_sort_could_not():
    """A FIXTURE, explicitly NOT a ruling — the developer REJECTED this board (Issue #417 item 3).
    The bench tie is real: `deploy(R) - deploy(B)` cancels on both benched Staryu (ADR-0124)."""
    pilot = _shipped_pilot()
    terms, chosen = _terms(pilot, parity_frame(*WIDEST))
    assert len(terms) == 3
    active, bench_energised, bench_empty = terms
    assert active > 0 and bench_energised == bench_empty == 0.0
    assert chosen == [0]


#: deploy is a damage currency and this menu is Nebula Beam's 210 scaled by two probabilities, so
#: the bar sits well below the rejected asymmetric build's −26.25 and well above float noise.
_LARGE_NEGATIVE = -1.0


def test_the_ignition_bench_is_priced_as_the_ignition_less_bench_beside_it():
    """ADR-0125. D3: evolving re-reads the attached CARDS against the new stage. D4: `turns_to_afford`
    is a FORWARD clock and the Ignition is discarded at end of turn, so it arms neither side."""
    pilot = _shipped_pilot()
    frame = parity_frame(*WIDEST)
    obs = frame["obs"]
    sel = obs["select"]
    board = pilot._board(obs)
    target_cid = sel["contextCard"]["id"]
    rows = []
    for option in sel["option"]:
        raw = pilot._option_pokemon(obs, sel, option)
        body, result, result_raw = pilot._evolve_substitution(
            obs, board, raw, target_cid, is_active=(option.get("area") == _ACTIVE))
        rows.append((raw, body, result, result_raw))

    (_a_raw, active_b, active_r, _a_res), (ign_raw, ign_b, ign_r, ign_res), \
        (_e_raw, empty_b, empty_r, _e_res) = rows

    # the board this is measured on
    assert [c.get("id") for c in (ign_raw.get("energyCards") or [])] == [17]
    assert ign_raw["energies"] == [0] and _e_raw.get("energies") == []

    # D3: the result side re-derives `[0]` -> `[0, 0, 0]`, matching the engine's own apply seam.
    assert ign_res["energies"] == [0, 0, 0]
    assert ign_res["energyCards"] == ign_raw["energyCards"]

    # D4, on BOTH sides: the vanishing card arms neither the Staryu nor the Mega Starmie ex.
    assert ign_b.arm == ign_r.arm == 3
    assert empty_b.arm == empty_r.arm == 3, "the Ignition-less control must be unchanged"
    assert ign_b.deploy() == empty_b.deploy() and ign_r.deploy() == empty_r.deploy()

    assert ign_r.deploy() - ign_b.deploy() == 0.0
    assert empty_r.deploy() - empty_b.deploy() == 0.0
    assert active_r.deploy() - active_b.deploy() > 0.0, (
        "the ACTIVE holds no Energy, so nothing is excluded there and its delta must stand")


def test_the_result_only_exclusion_regression_is_structurally_unreachable():
    """Excluding the expiring Energy on the RESULT but not on the BODY reads as a PENALTY for
    evolving. Asserted on SHAPE, not on the number, so it survives a re-tuned payoff."""
    pilot = _shipped_pilot()
    terms, _chosen = _terms(pilot, parity_frame(*WIDEST))
    assert all(t > _LARGE_NEGATIVE for t in terms), (
        f"an evolve priced as actively worse than not evolving: {terms} — the asymmetric "
        f"(result-only) expiry exclusion is the build that produces this")
    _active, bench_energised, bench_empty = terms
    assert bench_energised == bench_empty, (
        "the two benched Staryu differ only in an Energy that will not survive the turn; pricing "
        "them apart means the body and the result are being read on different clocks")


def test_the_pick_survives_reordering_so_it_is_the_term_and_not_the_fingerprint():
    pilot = _shipped_pilot()
    frame = parity_frame(*WIDEST)
    frame["obs"]["select"]["option"] = list(reversed(frame["obs"]["select"]["option"]))
    terms, chosen = _terms(pilot, frame)
    assert chosen == [2]                     # the Active, now last — the body moved, the pick with it
    assert terms[2] > terms[0] == terms[1] == 0.0


def test_a_forced_width_one_board_is_priced_but_cannot_move_anything():
    """The term still prices a width-1 menu; abstaining on width would be a second, silent gate."""
    pilot = _shipped_pilot()
    terms, chosen = _terms(pilot, parity_frame("v2_ms_ml_5301", 17))
    assert len(terms) == 1 and terms[0] > 0.0
    assert chosen == [0]


# Each gate test below changes exactly ONE field of a REAL corpus board: a synthetic fixture reads
# 0.0 for reasons unrelated to the branch under test (no card table -> `turns_to_afford` is None).
GATE_BOARD = ("v2_ms_mirror_5000", 15)      # width 2, one Active one Bench, BOTH options score


def _gateparity_frame():
    return parity_frame(*GATE_BOARD)


def _term(pilot, frame, option):
    obs, sel = frame["obs"], frame["obs"]["select"]
    board = pilot._board(obs)
    return pilot._evolve_target_tactical(obs, sel, board, option,
                                         pilot._context(obs, sel, board, option))


def test_the_gate_board_scores_before_anything_is_changed():
    """The positive control: a 0.0 below is the GATE talking, not the board."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    assert all(_term(pilot, frame, o) != 0.0 for o in frame["obs"]["select"]["option"])


def test_off_ctx_18_the_term_is_silent():
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    frame["obs"]["select"]["context"] = _MAIN
    assert all(_term(pilot, frame, o) == 0.0 for o in frame["obs"]["select"]["option"])


def test_a_non_card_option_is_silent():
    """Pricing an `_EVOLVE` option here would double-count against `_evolve_decision`."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    option = dict(frame["obs"]["select"]["option"][0], type=_EVOLVE)
    assert _term(pilot, frame, option) == 0.0


def test_an_opponent_owned_option_is_silent():
    """The evolution only ever lands on MY own bodies."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    yi = frame["obs"]["current"]["yourIndex"]
    option = dict(frame["obs"]["select"]["option"][0], playerIndex=1 - yi)
    assert _term(pilot, frame, option) == 0.0


def test_no_context_card_fails_closed_rather_than_reading_the_option():
    """The target rides on the SELECT; the option's own (area, index) names the PRE-EVOLUTION, so a
    `_option_card_id` fallback would compare each body against ITSELF and look like it had priced."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    frame["obs"]["select"]["contextCard"] = None
    assert all(_term(pilot, frame, o) == 0.0 for o in frame["obs"]["select"]["option"])


def test_an_unresolvable_option_body_fails_closed():
    pilot = _shipped_pilot()
    assert _term(pilot, _gateparity_frame(), card_opt(_BENCH, 7)) == 0.0


def test_the_target_is_read_off_the_select_and_not_off_the_option():
    """Point ``contextCard`` at the PRE-EVOLUTION and the substitution becomes body-for-itself. If
    the term read the option's own card (as `ctx.card_id` does at MAIN) this could not move."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    real = [_term(pilot, frame, o) for o in frame["obs"]["select"]["option"]]
    frame["obs"]["select"]["contextCard"] = dict(frame["obs"]["select"]["contextCard"], id=STARYU)
    self_sub = [_term(pilot, frame, o) for o in frame["obs"]["select"]["option"]]
    assert any(v != 0.0 for v in real)
    assert self_sub == [0.0, 0.0]
