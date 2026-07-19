"""WP6 — the replaceability-floor keep-value (hypergeometric-fetch-closure §Rounds 6-8).

`keep_cost(X) = role_value(X) × (1 − re-access_odds(X))` — the gamble's gain-side closure pointed
BACKWARDS: a card that shuffles into the deck costs its role value scaled by how UN-recoverable it is.
A wincon with two Mega Signal live shuffles cheap; a closure-unreachable one-of shuffles at ~full role
value. The `common.card_worth` tier table is the ONE tuned currency; the closure supplies the redundancy.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


@pytest.mark.req("REQ-WORTH-0001")
def test_reaccess_outs_are_the_closure_pointed_backwards():
    """`_card_reaccess_outs(X)` = X's own deck copies PLUS every deck-search tutor whose FETCH clause
    reaches X (`_fetch_target_matches`) — Mega Lucario ex is reached by Ultra Ball (any Pokémon) and
    Mega Signal (mega) but NOT Poké Pad (no-Rule-Box), exactly the closure the gamble gain side uses."""
    ml = _shipped_pilot("mega_lucario")
    counts = {678: 1, 1121: 4, 1145: 2, 1152: 4, 6: 10}   # Mega Lucario ex + Ultra Ball + Mega Signal
    assert ml._card_reaccess_outs(678, counts) == 1 + 4 + 2       # Poké Pad (1152) excluded: Rule Box
    # A {F} Basic Energy: reached by Fighting Gong ({F}) and (were it in deck) Energy Search — here just
    # its own copies plus Fighting Gong, which fetches a Basic {F} Energy.
    assert ml._card_reaccess_outs(6, {6: 10, 1142: 4}) == 10 + 4
    assert ml._card_reaccess_outs(6, {6: 10, 1152: 4}) == 10        # Poké Pad fetches Pokémon, not energy
    assert ml._card_reaccess_outs(999999, counts) == 0             # unknown card -> no outs


@pytest.mark.req("REQ-WORTH-0001")
def test_role_value_reads_the_tuned_tier_table():
    """Base worth = the general role→points tier (`common.card_worth.ROLE_TIER`), max over a card's
    declared/derived roles, with the energy and ACE-SPEC fallbacks. Deck-agnostic: deck-genie never
    invents numbers (spec §Round 9)."""
    from common.card_worth import ROLE_TIER, ENERGY_TIER, ACE_SPEC_TIER
    ml = _shipped_pilot("mega_lucario")
    assert ml._role_value(678) == ROLE_TIER["win_condition"]       # Mega Lucario ex: the wincon tier
    assert ml._role_value(6) == ENERGY_TIER                        # a typed Basic Energy
    ms = _shipped_pilot("mega_starmie")
    assert ms._role_value(1100) == ACE_SPEC_TIER                   # Energy Search Pro: an ACE SPEC one-of
    assert ml._role_value(999999) == 0                             # unknown card -> no declared worth


@pytest.mark.req("REQ-WORTH-0001")
def test_role_value_pure_function_owns_the_tier_and_fallbacks():
    """`card_worth.role_value(roles, is_ace_spec, is_typed_basic_energy)` is the Pilot-free worth
    primitive the Pilot's `_role_value` delegates to (WP7): the tier max over roles, the ACE-SPEC and
    typed-Basic-Energy fallbacks for an un-Roled card, 0 otherwise — deck-agnostic, zero card facts."""
    from common.card_worth import role_value, ROLE_TIER, ENERGY_TIER, ACE_SPEC_TIER
    assert role_value(["win_condition", "accel_source"]) == ROLE_TIER["win_condition"]   # max over roles
    assert role_value([]) == 0.0
    assert role_value([], is_typed_basic_energy=True) == ENERGY_TIER
    assert role_value([], is_ace_spec=True) == ACE_SPEC_TIER
    # MAX semantics (revised with the TAG_TIER build): the best claim wins — an ACE SPEC that also
    # declares a modest role is still one-per-deck irreplaceable (25 > engine 12).
    assert role_value(["engine"], is_ace_spec=True) == ACE_SPEC_TIER
    assert role_value(["not_a_real_role"]) == 0.0                            # unknown role -> no worth
    # parity: the Pilot delegator reproduces the pure function on real cards
    ml = _shipped_pilot("mega_lucario")
    for cid in (678, 6, 999999):
        st = ml.stats.get(cid)
        expect = role_value(ml._roles_of(cid),
                            is_ace_spec=bool(st is not None and getattr(st, "aceSpec", False)),
                            is_typed_basic_energy=bool(st is not None and getattr(st, "is_typed_basic_energy", False)))
        assert ml._role_value(cid) == expect


@pytest.mark.req("REQ-WORTH-0004")
def test_role_value_reads_tag_derived_worth():
    """The worth-coverage fix (ADR-0065 §Build status, TAG_TIER): situational Trainers / special Energy carry
    their keep-value in behavioural TAGS the discard ladder already trusts (`keep-key` −30 covers
    `discard_eot`; `dont-waste-clutch-heal`; `keep-gust-and-recovery` −10) — `role_value` now reads a
    TAG_TIER so the ONE currency covers them. Worth = the MAX claim across roles, tags, and the
    ACE-SPEC / energy fallbacks."""
    from common.card_worth import role_value, ROLE_TIER, TAG_TIER, ACE_SPEC_TIER
    assert role_value([], tags=["discard_eot"]) == TAG_TIER["discard_eot"]      # the Ignition burst
    assert role_value([], tags=["clutch_heal"]) == TAG_TIER["clutch_heal"]      # Wally's Compassion
    assert role_value([], tags=["gust"]) == TAG_TIER["gust"]                    # Boss's Orders
    assert role_value([], tags=["recycle"]) == TAG_TIER["recycle"]              # Night Stretcher
    assert role_value([], tags=["hand_disruption"]) == 0.0                      # an untiered tag: no claim
    # MAX-join: the best claim wins — a declared role does not CAP a higher tag/fallback worth.
    assert role_value(["accel_source"], tags=["discard_eot"]) == max(
        ROLE_TIER["accel_source"], TAG_TIER["discard_eot"])
    assert role_value(["win_condition"], tags=["gust"]) == ROLE_TIER["win_condition"]
    assert role_value(["engine"], is_ace_spec=True) == ACE_SPEC_TIER            # 25 > engine 12


@pytest.mark.req("REQ-WORTH-0001")
def test_keep_cost_is_role_value_scaled_by_irreplaceability():
    """`keep_cost = role_value × (1 − re-access odds)` over the shuffle-grown pool (+1 for the shuffled
    held copy rejoining the deck). The SAME wincon costs almost nothing to shuffle with its tutors live
    and near its full role value with them gone — the replaceability floor, graded, zero new constants."""
    from math import isclose
    from common.card_worth import ROLE_TIER
    from common.deck_odds import draw_hit_probability
    ml = _shipped_pilot("mega_lucario")
    pool, draws = 40, 6
    live = {678: 1, 1121: 4, 1145: 2}                     # wincon + Ultra Ball + Mega Signal in deck
    outs = ml._card_reaccess_outs(678, live) + 1          # +1: the shuffled copy rejoins the deck
    expect = ROLE_TIER["win_condition"] * (1 - draw_hit_probability(outs, pool, draws))
    assert isclose(ml._keep_cost(678, live, pool, draws), expect)
    gone = {678: 1}                                       # the one-of, no tutors: near-full role value
    cheap = ml._keep_cost(678, live, pool, draws)
    dear = ml._keep_cost(678, gone, pool, draws)
    assert cheap < dear <= ROLE_TIER["win_condition"]
    assert ml._keep_cost(999999, live, pool, draws) == 0.0   # a role-less card is free to shuffle


@pytest.mark.req("REQ-WORTH-0005")
def test_hand_keep_prices_duplicates_marginally_and_excludes_the_played_refresh_once():
    """The duplicate-copy reconciliation (ADR-0065 §Build status): BOTH keep-value sites (the gamble
    keep-floor, the refresh SHED) read the ONE `_hand_keep` summation. k held copies of a card each
    charge with all k shuffled siblings as outs (the first sets-not-sums step, spec §Round 7) — dearer
    than the retired SHED frozenset dedup (one charge per distinct card, duplicates free) and cheaper
    than the retired gamble form (k independent one-ofs at +1 out each). The played refresh is
    excluded ONCE — a second held copy of it still shuffles and still charges. A duplicate-free hand
    prices exactly as before the reconciliation."""
    from math import isclose
    from common.card_worth import ROLE_TIER
    from common.deck_odds import draw_hit_probability
    ml = _shipped_pilot("mega_lucario")
    pool, draws = 40, 6
    counts = {678: 1, 1121: 4, 1145: 2}                   # wincon + Ultra Ball + Mega Signal in deck
    single = ml._keep_cost(678, counts, pool, draws)      # the lone-copy charge (+1 out), unchanged
    assert single > 0
    # duplicate-free hand: the summation IS the old per-copy sum — behaviour unchanged
    assert isclose(ml._hand_keep([678], None, counts, pool, draws), single)
    # two held copies: each charges with BOTH shuffled siblings as outs — 2 × the (+2 outs) charge,
    # strictly between one dedup charge and two independent one-of charges
    outs2 = ml._card_reaccess_outs(678, counts) + 2
    per_copy2 = ROLE_TIER["win_condition"] * (1 - draw_hit_probability(outs2, pool, draws))
    dup = ml._hand_keep([678, 678], None, counts, pool, draws)
    assert isclose(dup, 2 * per_copy2)
    assert single < dup < 2 * single
    # the played refresh is excluded ONCE — its duplicate held copy still charges (as a lone copy)
    assert isclose(ml._hand_keep([678, 678], 678, counts, pool, draws), single)
    # a role-less hand stays free regardless of duplication
    assert ml._hand_keep([999999, 999999], None, counts, pool, draws) == 0.0


@pytest.mark.req("REQ-WORTH-0006")
def test_pre_anchor_keep_cost_weights_the_prize_split():
    """PRE-ANCHOR the cost side prices the prize split exactly like the gain side (`_prize_split_hit`):
    the unseen re-access outs split hypergeometrically over deck + face-down prizes, while the
    shuffled held copy joins the pool as a CERTAIN out (a hand card is never prize-assignable).
    Before this, the cost side counted possibly-prized outs at full strength against a prize-free
    pool — re-access overestimated, keep under-charged, a pre-anchor pro-gamble bias the
    prize-weighted gain side never had. Weighting can only LOWER re-access, so keep-cost RISES
    pre-anchor; with no hidden prizes the plain window draw is reproduced exactly."""
    from math import comb, isclose
    from common.card_worth import ROLE_TIER
    from common.deck_odds import draw_hit_probability
    ml = _shipped_pilot("mega_lucario")
    pool, draws, k, d = 40, 6, 6, 34                     # 6 face-down prizes, 34 hidden deck cards
    counts = {678: 1, 1121: 4, 1145: 2}                  # unseen outs: wincon + Ultra Ball + Mega Signal
    u = ml._card_reaccess_outs(678, counts)
    h = d + k
    expect_re = sum(comb(d, j) * comb(k, u - j) / comb(h, u)
                    * draw_hit_probability(j + 1, pool, draws)    # +1: the shuffled copy, certain
                    for j in range(max(0, u - k), min(u, d) + 1))
    expect = ROLE_TIER["win_condition"] * (1 - expect_re)
    got = ml._keep_cost(678, counts, pool, draws, prizes_hidden=k, deck_count=d)
    assert isclose(got, expect)
    # the weighting only ever RAISES keep vs the unweighted read of the same unseen counts
    assert got > ml._keep_cost(678, counts, pool, draws)
    # prizes_hidden=0 → the plain window draw, byte-identical to the anchored path
    assert ml._keep_cost(678, counts, pool, draws, prizes_hidden=0) == ml._keep_cost(678, counts, pool, draws)
    # _hand_keep threads the split through to each copy
    assert isclose(ml._hand_keep([678], None, counts, pool, draws,
                                 prizes_hidden=k, deck_count=d), got)
    # `certain` edges of the split primitive: the gain side (certain=0) is unchanged; zero unseen
    # outs still redraw the certain shuffled copy
    assert (ml._prize_split_hit(u, d, k, pool, draws)
            == ml._prize_split_hit(u, d, k, pool, draws, certain=0))
    assert isclose(ml._prize_split_hit(0, d, k, pool, draws, certain=1),
                   draw_hit_probability(1, pool, draws))
    assert ml._prize_split_hit(0, d, k, pool, draws) == 0.0


@pytest.mark.req("REQ-WORTH-0001")
def test_keep_cost_deadline_odds_gates_the_worth():
    """The gate library's deadline factor (ADR-0065 Stage 1): ``keep_cost`` scales by ``deadline_odds``
    — 1.0 (default) leaves the closure value unchanged, 0.0 collapses it to nothing (an undeployable
    evolution is a dead card, free to shuffle), and it factors linearly in between."""
    from common.card_worth import keep_cost
    base = keep_cost(30.0, 0.4)                       # deadline_odds defaults to 1.0
    assert keep_cost(30.0, 0.4, 1.0) == base
    assert keep_cost(30.0, 0.4, 0.0) == 0.0
    assert keep_cost(30.0, 0.4, 0.5) == base * 0.5
