"""The `_EVOLVES_FROM` target select (ctx 18) — `Pilot._evolve_target_tactical` (Issue #417).

Salvatore evolves a body straight out of the deck, bypassing hand: *"Search your deck for a card
that has no Abilities and evolves from 1 of your Pokémon, and put it onto that Pokémon to evolve
it"* (`data/EN_Card_Data.csv` 1189, read at source). The engine poses `_EVOLVES_TO` (19 — which
physical deck copy) and then this one, which is the real decision: with three Staryu in play, WHICH
one becomes the Mega Starmie ex.

Nothing scored it. `_evolve_decision`'s guard is ``ctx.option_type != _EVOLVE``, and `_EVOLVE` (9)
is a MAIN-menu ACTION type while every ctx-18 option carries `_CARD` (3) — asserted below, off the
real corpus — so the decider abstained on every Salvatore target-select unconditionally, and
`_prefer_soonest_arming_evolve` (identical gate) could not reach it either. Every option therefore
came back 0.0 and the pick fell out of `_order_key`'s canonical fingerprint: the same string-sort
artefact `test_heal_target.py` records for ctx 17.

**Validation is BY CONSTRUCTION, and that is forced rather than chosen.** Measured below over every
committed correction file: **zero** ruled frames carry ctx 18, so *"no ruled frame moves"* is
vacuous here and cannot be the bar — exactly the situation Issue #409 faced at ctx 17. What stands
in for it is that issue's own substitute, unchanged:

* the **seven real ctx-18 boards** in the committed parity corpus, used as constructed fixtures.
  Their board states are genuine engine output; their recorded ``choice`` is DISCARDED, because
  those traces are driven by `tools/parity/capture_match.py`'s randomised policy and reading a
  coin flip as a ruling would anchor this file to noise.
* unit assertions on the term's own legs, its gate, and its fail-closed floor.

The corpus census is itself asserted, so a future capture that adds ctx-18 frames — or a ctx-19
menu spanning more than one target SPECIES, which is the one case the mootness ruling excludes —
makes this file say so rather than silently drifting.
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

#: ``(trace, frame)`` of every ctx-18 step in the committed parity corpus. Three are width-1 (forced,
#: no decision), three are width-2 and one — `ms_mirror_1001` f15 — is the only three-wide menu the
#: corpus contains, so it is the discriminating board this term exists for.
REAL_BOARDS = [("ms_mirror_1001", 15), ("ms_mirror_1001", 20), ("v2_ms_dx_5401", 42),
               ("v2_ms_mirror_5000", 15), ("v2_ms_mirror_5000", 39), ("v2_ms_mirror_5000", 106),
               ("v2_ms_ml_5301", 17)]
WIDEST = ("ms_mirror_1001", 15)


def _shipped_pilot():
    """mega_starmie's REAL Pilot — every kill-switch at its shipped default, exactly as `main.py`
    builds it. Every ctx-18 board in the corpus is a Mega Starmie game, so this is the agent that
    actually faced them."""
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


# ───────────────────────────────────────────────────────────────── the ground truth, re-measured
def test_the_constants_land_where_the_engine_enum_says_they_should():
    """`strategy/context.py` jumped straight from `_HEAL` (17) to `_ABILITY` (10)/`_ATTACH_FROM`
    (21), so the next reader looking for 18 or 19 found nothing at all."""
    from cg.api import SelectContext
    assert _EVOLVES_FROM == int(SelectContext.EVOLVES_FROM) == 18
    assert _EVOLVES_TO == int(SelectContext.EVOLVES_TO) == 19


def test_corpus_ctx18_census_is_what_the_equation_was_built_on():
    """The ground truth Issue #417 measured, re-measured here so a later capture cannot quietly
    change it: 7 ctx-18 steps over the 377 committed traces, widths 1/2/3, every one a MANDATORY
    single pick (`minCount`/`maxCount` 1/1), every option `OptionType.CARD` — **never** `_EVOLVE` —
    over my ACTIVE and BENCH, and every ``contextCard`` the Mega Starmie ex being put down.

    The option TYPE is the whole reason the select was unreachable: `_evolve_decision` and
    `_prefer_soonest_arming_evolve` both gate on ``type == _EVOLVE``, so a menu of `_CARD` options
    abstains through both of them no matter what the board says."""
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
    """The `_EVOLVES_TO` mootness ruling, MEASURED rather than assumed (Issue #417).

    All 20 ctx-19 steps offer `area=DECK` options only, and on every multi-option menu the revealed
    candidates are physically distinct copies of ONE species — picking among interchangeable copies
    has no strategic content, so no term was built. This assertion is the tripwire: a future deck
    running such a search over a line with more than one legal target species makes it fail, which
    is the moment ctx 19 stops being moot."""
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
    """Why validation here is by construction: the committed corpus rules **zero** ctx-18 and
    ctx-19 frames, so there is no human ranking to hold this term against. Asserted rather than
    stated so the first ruling that lands turns this file red and gets a real regression test."""
    import sys
    sys.path.insert(0, str(REPO / "tests"))
    from corpus_helpers import corpus_index
    ruled = {(c.decision or {}).get("select_context") for c in corpus_index().values()}
    assert "EvolvesFrom" not in ruled and "EvolvesTo" not in ruled


# ─────────────────────────────────────────────────────── the seven real boards, as fixtures
@pytest.mark.parametrize("trace,index", REAL_BOARDS, ids=lambda v: str(v))
def test_every_real_board_prices_every_option_through_the_equation(trace, index):
    """On all seven the term IS `evolve_value`'s total for the body-substituted delta — recomputed
    here from `_evolve_substitution`'s own two readings, so the test would catch the term reaching
    for anything the equation does not sanction (a prize leg, an area bonus, a card-id special
    case). The recorded ``choice`` is deliberately not asserted: those traces run a randomised
    policy."""
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
        # The income legs are structurally zero at this select (Salvatore's clause carries
        # `no_ability: true`, and no body this deck offers has an Ability), so the whole term is the
        # deploy delta — the claim the call site's comment makes, asserted rather than trusted.
        assert expected == result.deploy() - body.deploy()


def test_the_widest_real_board_separates_the_bodies_the_string_sort_could_not():
    """`ms_mirror_1001` f15 — the corpus's only three-wide ctx-18 menu: three Staryu (Active 70/70
    unenergised, Bench 70/70 carrying an Ignition Energy, Bench 70/70 unenergised).

    ⚠️ **A FIXTURE, and explicitly NOT a ruling — the developer REJECTED this board on 2026-08-06**
    (Issue #417 acceptance item 3). It carries an Ignition Energy on a BENCHED Staryu while the
    ACTIVE Staryu has none, which is not a play any agent would make; it is what
    `tools/parity/capture_match.py`'s randomised policy produced. So its recorded ``choice`` is
    noise AND the position itself poses no question worth answering. What it is still good for is
    the only thing asserted below: the term separates bodies on a genuine engine board state, where
    before it returned 0.0 on every option and the pick fell out of a JSON string sort.

    The Active wins on the SURVIVAL leg: its `turns_to_ko_me` is 1 against the bench's 4, so
    evolving it into a 330-HP body is the only substitution that moves `p_survive` (0.125 -> 0.250).
    Both benched Staryu read exactly 0.0, and that tie is a real property of the equation rather
    than a failure to look: on the bench `p_survive` is already 1.0 for the pre-evolution, and
    `turns_to_afford` is unchanged by the hop, so `deploy(R) - deploy(B)` cancels on both. It is the
    DELTA that ranks, which is right as an argmax: board value after picking *i* is
    ``Σ_j deploy(B_j) + [deploy(R_i) - deploy(B_i)]``, and the sum is constant across the menu.

    Of the two model limits ADR-0124 recorded on this board and deliberately did not fix, the first
    — `_evolve_substitution` copying `energies` verbatim, so the Ignition on bench 0 read 1 unit
    where the engine's own re-derivation gives 3 — was fixed by **Issue #418 / ADR-0125**, together
    with the expiry the fix makes mandatory (see `test_the_ignition_bench_is_priced_as_the_ignition
    _less_bench_beside_it` below). The second stands: `payoff_damage` pre-credits a pre-evolution
    with its whole line's payoff, which is what makes both bench deltas cancel.

    The bench tie asserted here is therefore now a STRONGER statement than it was: it survives the
    provision fix rather than predating it."""
    pilot = _shipped_pilot()
    terms, chosen = _terms(pilot, parity_frame(*WIDEST))
    assert len(terms) == 3
    active, bench_energised, bench_empty = terms
    assert active > 0 and bench_energised == bench_empty == 0.0
    assert chosen == [0]


# ─────────────────────────────────── Issue #418 / ADR-0125: the provision and the expiry, on f15
#: `evolve_value`'s deploy currency is damage, and the whole menu here is Nebula Beam's 210 scaled
#: by two probabilities — so a "large-magnitude negative" delta is one whose size is comparable to
#: that payoff. The rejected asymmetric build produced −26.25 on bench 0; every correct build
#: produces 0.00. The bar is set well below the former and well above float noise.
_LARGE_NEGATIVE = -1.0


def test_the_ignition_bench_is_priced_as_the_ignition_less_bench_beside_it():
    """**The ruled shape** (Issue #418 R4, developer-ruled 2026-08-06), on `ms_mirror_1001` f15.

    Bench 0 carries one Ignition Energy; bench 1 carries nothing. Two facts about that Ignition
    settle the whole reading, and they only work together:

    * **D3 — the provision.** Evolving re-reads the attached CARDS against the new stage, so the
      Ignition renders ``[0, 0, 0]`` on Mega Starmie ex, not the ``[0]`` it renders on a Staryu.
    * **D4 — the expiry.** ``turns_to_afford`` is a FORWARD clock, and the card is discarded at the
      end of this turn. A benched body cannot attack this turn, so those three units buy nothing and
      are gone before the next one: the honest clock is **3**, not the *"armed now"* 0 that D3 alone
      produces.

    Once the Ignition cannot be trusted for the future, the two benched Staryu ARE identical for
    this decider's purposes — which is exactly what the reading says: both arms 3, both deltas 0.00,
    a clean tie. The ACTIVE keeps its own delta untouched (it holds no Energy, so there is nothing
    to exclude), which is what makes the fix targeted rather than a blanket zeroing."""
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

    # The board this is measured on, asserted rather than assumed.
    assert [c.get("id") for c in (ign_raw.get("energyCards") or [])] == [17]
    assert ign_raw["energies"] == [0] and _e_raw.get("energies") == []

    # D3: the result side re-derives. `[0]` -> `[0, 0, 0]`, which is what the engine's own apply
    # seam writes for this evolve.
    assert ign_res["energies"] == [0, 0, 0]
    assert ign_res["energyCards"] == ign_raw["energyCards"]

    # D4, on BOTH sides: the vanishing card arms neither the Staryu nor the Mega Starmie ex.
    assert ign_b.arm == ign_r.arm == 3
    assert empty_b.arm == empty_r.arm == 3, "the Ignition-less control must be unchanged"
    assert ign_b.deploy() == empty_b.deploy() and ign_r.deploy() == empty_r.deploy()

    # …and the delta is a clean tie with the bench beside it, not a penalty for evolving.
    assert ign_r.deploy() - ign_b.deploy() == 0.0
    assert empty_r.deploy() - empty_b.deploy() == 0.0
    assert active_r.deploy() - active_b.deploy() > 0.0, (
        "the ACTIVE holds no Energy, so nothing is excluded there and its delta must stand")


def test_the_result_only_exclusion_regression_is_structurally_unreachable():
    """**A NEGATIVE test** (Issue #418 acceptance 4): the asymmetric fix — excluding the expiring
    Energy on the RESULT but not on the BODY — is a new, worse bug, and this pins its shape out.

    It judges the post-evolution honestly while still crediting the pre-evolution's vanishing card
    as forward progress, and the mismatch reads as a PENALTY for evolving: measured at −26.25 on
    bench 0, the worst score on the whole menu, for a substitution that changes nothing except which
    body an already-present, already-expiring Energy sits on.

    The assertion is on the SHAPE rather than on the number, so it survives a re-tuned payoff: no
    option on this menu may score a large-magnitude negative, and no two bodies differing ONLY in
    whether they carry an expiring Energy may be priced apart. Either would mean one side of the
    substitution is being read on a clock the other is not."""
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
    """The defect this term replaces was `_order_key` falling through to a lexicographic sort of a
    serialized board fragment, which is a function of the option's AREA rather than of the board.
    Reversing the menu on the widest real board must not move the winning BODY — under the old
    behaviour the pick was the same array position regardless of what stood in it."""
    pilot = _shipped_pilot()
    frame = parity_frame(*WIDEST)
    frame["obs"]["select"]["option"] = list(reversed(frame["obs"]["select"]["option"]))
    terms, chosen = _terms(pilot, frame)
    assert chosen == [2]                     # the Active, now last — the body moved, the pick with it
    assert terms[2] > terms[0] == terms[1] == 0.0


def test_a_forced_width_one_board_is_priced_but_cannot_move_anything():
    """Three of the seven boards are width-1. The term still prices them — abstaining on width
    would be a second, silent gate — but with one option there is nothing to rank, so this only
    asserts the value is real and finite rather than the fail-closed floor."""
    pilot = _shipped_pilot()
    terms, chosen = _terms(pilot, parity_frame("v2_ms_ml_5301", 17))
    assert len(terms) == 1 and terms[0] > 0.0
    assert chosen == [0]


# ─────────────────────────────────────────────────────────────────── the gate and the floor
#
# Every test below runs against a REAL corpus board with exactly ONE field changed, and each asserts
# the unmodified board first. That positive control is the point: a 0.0 on a board that was never
# going to score anyway proves nothing about the gate, and a purely synthetic fixture reads 0.0 for
# a reason that has nothing to do with the branch under test — `turns_to_afford` returns None
# without a real card table, `p_arrive` is then 0, and every leg collapses (CLAUDE.md: a negative
# result needs a positive control).
GATE_BOARD = ("v2_ms_mirror_5000", 15)      # width 2, one Active one Bench, BOTH options score


def _gateparity_frame():
    return parity_frame(*GATE_BOARD)


def _term(pilot, frame, option):
    obs, sel = frame["obs"], frame["obs"]["select"]
    board = pilot._board(obs)
    return pilot._evolve_target_tactical(obs, sel, board, option,
                                         pilot._context(obs, sel, board, option))


def test_the_gate_board_scores_before_anything_is_changed():
    """The positive control every test below leans on: on the untouched board both options price
    non-zero, so a 0.0 in the tests that follow is the GATE talking and not the board."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    assert all(_term(pilot, frame, o) != 0.0 for o in frame["obs"]["select"]["option"])


def test_off_ctx_18_the_term_is_silent():
    """Gated, like every sibling target term — so nothing outside this select can move."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    frame["obs"]["select"]["context"] = _MAIN
    assert all(_term(pilot, frame, o) == 0.0 for o in frame["obs"]["select"]["option"])


def test_a_non_card_option_is_silent():
    """The other half of the gate. Pricing an `_EVOLVE` (9) option here would double-count against
    `_evolve_decision`, which owns that option type."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    option = dict(frame["obs"]["select"]["option"][0], type=_EVOLVE)
    assert _term(pilot, frame, option) == 0.0


def test_an_opponent_owned_option_is_silent():
    """The evolution only ever lands on MY own bodies — the same own-body guard
    `_heal_target_tactical` carries, so a future card posing this select over both sides cannot have
    the term rank an opponent's board for it."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    yi = frame["obs"]["current"]["yourIndex"]
    option = dict(frame["obs"]["select"]["option"][0], playerIndex=1 - yi)
    assert _term(pilot, frame, option) == 0.0


def test_no_context_card_fails_closed_rather_than_reading_the_option():
    """A4. The target rides on the SELECT; the option's own (area, index) names the PRE-EVOLUTION.
    With no ``contextCard`` there is no target to price, and the term returns 0.0 rather than
    falling back to `_option_card_id` — which would silently compare each body against ITSELF and
    rank every option at a flat zero delta while looking like it had priced them."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    frame["obs"]["select"]["contextCard"] = None
    assert all(_term(pilot, frame, o) == 0.0 for o in frame["obs"]["select"]["option"])


def test_an_unresolvable_option_body_fails_closed():
    """An option pointing at a bench slot that does not exist — 0.0, never a guess."""
    pilot = _shipped_pilot()
    assert _term(pilot, _gateparity_frame(), card_opt(_BENCH, 7)) == 0.0


def test_the_target_is_read_off_the_select_and_not_off_the_option():
    """The claim the whole term rests on, asserted directly: point ``contextCard`` at the
    PRE-EVOLUTION and the substitution becomes body-for-itself, so every delta collapses to 0 — on
    the very board that scores non-zero with the real target. If the term were reading the option's
    own card (as `ctx.card_id` does at MAIN) this change could not move anything, because the
    option's card already IS the pre-evolution."""
    pilot = _shipped_pilot()
    frame = _gateparity_frame()
    real = [_term(pilot, frame, o) for o in frame["obs"]["select"]["option"]]
    frame["obs"]["select"]["contextCard"] = dict(frame["obs"]["select"]["contextCard"], id=STARYU)
    self_sub = [_term(pilot, frame, o) for o in frame["obs"]["select"]["option"]]
    assert any(v != 0.0 for v in real)
    assert self_sub == [0.0, 0.0]
