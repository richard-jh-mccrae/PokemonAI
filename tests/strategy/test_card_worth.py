"""The replaceability-floor keep-value: `keep_cost(X) = role_value(X) x (1 - re-access_odds(X))`.

The `common.card_worth` tier table is the ONE tuned currency; the fetch closure, pointed BACKWARDS,
supplies the redundancy.
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
    """X's own deck copies PLUS every deck-search tutor whose FETCH clause reaches X."""
    ml = _shipped_pilot("mega_lucario")
    counts = {678: 1, 1121: 4, 1145: 2, 1152: 4, 6: 10}   # Mega Lucario ex + Ultra Ball + Mega Signal
    assert ml._card_reaccess_outs(678, counts) == 1 + 4 + 2       # Poké Pad (1152) excluded: Rule Box
    assert ml._card_reaccess_outs(6, {6: 10, 1142: 4}) == 10 + 4  # + Fighting Gong, a Basic {F} fetch
    assert ml._card_reaccess_outs(6, {6: 10, 1152: 4}) == 10        # Poké Pad fetches Pokémon, not energy
    assert ml._card_reaccess_outs(999999, counts) == 0             # unknown card -> no outs


@pytest.mark.req("REQ-WORTH-0007")
def test_role_value_derives_worth_for_an_undeclared_line_member():
    """A middle Line stage is a plan piece even when the deck declared only the base. WORTH-ONLY: the
    Line-membership fact enters the value currency but NOT `_roles_of` / `c.roles`."""
    from common.card_worth import ROLE_TIER
    dx = _shipped_pilot("dragapult_ex")
    assert dx._role_value(121) == ROLE_TIER["win_condition"]        # payoff: unchanged (30)
    assert dx._role_value(119) == ROLE_TIER["win_condition_base"]   # declared base: unchanged (20)
    assert dx._role_value(120) == ROLE_TIER["win_condition_base"]   # DERIVED middle stage: was 0
    # the derivation is WORTH-ONLY — `c.roles` (what the rungs read) is untouched
    assert "win_condition_base" not in dx._roles_of(120)
    # A non-Line card gets only its shared function value: no spurious Line derivation.
    assert dx._role_value(1120) == 6.0                             # Crushing Hammer: energy denial


@pytest.mark.req("REQ-WORTH-0001")
def test_role_value_reads_the_tuned_tier_table():
    """MAX over a card's declared/derived roles, with the energy and ACE-SPEC fallbacks."""
    from common.card_worth import ROLE_TIER, ENERGY_TIER, ACE_SPEC_TIER
    ml = _shipped_pilot("mega_lucario")
    assert ml._role_value(678) == ROLE_TIER["win_condition"]       # Mega Lucario ex: the wincon tier
    assert ml._role_value(6) == ENERGY_TIER                        # a typed Basic Energy
    ms = _shipped_pilot("mega_starmie")
    assert ms._role_value(1100) == ACE_SPEC_TIER                   # Energy Search Pro: an ACE SPEC one-of
    assert ml._role_value(999999) == 0                             # unknown card -> no declared worth


@pytest.mark.req("REQ-WORTH-0001")
def test_role_value_pure_function_owns_the_tier_and_fallbacks():
    """The Pilot-free primitive `_role_value` delegates to: deck-agnostic, zero card facts."""
    from common.card_worth import role_value, ROLE_TIER, ENERGY_TIER, ACE_SPEC_TIER
    assert role_value(["win_condition", "accel_source"]) == ROLE_TIER["win_condition"]   # max over roles
    assert role_value([]) == 0.0
    assert role_value([], is_typed_basic_energy=True) == ENERGY_TIER
    assert role_value([], is_ace_spec=True) == ACE_SPEC_TIER
    # MAX semantics: an ACE SPEC that also declares a modest role is still one-per-deck irreplaceable.
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
    """Situational Trainers / Special Energy carry their keep-value in behavioural TAGS, so worth is
    the MAX claim across roles, tags, and the ACE-SPEC / energy fallbacks (ADR-0065)."""
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


@pytest.mark.req("REQ-WORTH-0008")
def test_function_worth_is_shared_across_decks_and_only_end_may_be_free():
    """Issue #507: card functions own the portable floor; deck roles need not repeat card facts."""
    from common.card_worth import FUNCTION_TIER, KNOWN_CARD_FLOOR, role_value
    ms = _shipped_pilot("mega_starmie")
    dx = _shipped_pilot("dragapult_ex")
    ml = _shipped_pilot("mega_lucario")
    assert ms._role_value(1120) == dx._role_value(1120) == FUNCTION_TIER["energy_denial"] == 6.0
    assert ms._role_value(1121) == dx._role_value(1121) == ml._role_value(1121) == 10.0
    assert ms._role_value(1122) == 10.0                              # Pokégear: dig/search band
    assert ms._role_value(1223) == ms._role_value(1227) == 8.0       # Harlequin / Lillie: refresh
    assert role_value([], is_known_card=True) == KNOWN_CARD_FLOOR == 5.0
    assert role_value([]) == 0.0                                     # unknown fact, not a free action


@pytest.mark.req("REQ-WORTH-0008")
def test_deck_override_can_raise_but_not_lower_the_shared_function_worth(monkeypatch):
    ms = _shipped_pilot("mega_starmie")
    monkeypatch.setitem(ms.strategy.worth_overrides, 1120, 14.0)
    assert ms._role_value(1120) == 14.0
    monkeypatch.setitem(ms.strategy.worth_overrides, 1120, 1.0)
    assert ms._role_value(1120) == 6.0


@pytest.mark.req("REQ-WORTH-0001")
def test_keep_cost_is_role_value_scaled_by_irreplaceability():
    """Over the shuffle-grown pool: +1 out for the shuffled held copy rejoining the deck."""
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
    """BOTH keep-value sites read the ONE `_hand_keep` summation: k held copies each charge with all k
    shuffled siblings as outs, and the played refresh is excluded ONCE."""
    from math import isclose
    from common.card_worth import ROLE_TIER
    from common.deck_odds import draw_hit_probability
    ml = _shipped_pilot("mega_lucario")
    pool, draws = 40, 6
    counts = {678: 1, 1121: 4, 1145: 2}                   # wincon + Ultra Ball + Mega Signal in deck
    single = ml._keep_cost(678, counts, pool, draws)      # the lone-copy charge (+1 out), unchanged
    assert single > 0
    assert isclose(ml._hand_keep([678], None, counts, pool, draws), single)
    # two held copies: each charges with BOTH shuffled siblings as outs
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
    """PRE-ANCHOR, unseen re-access outs split hypergeometrically over deck + face-down prizes while
    the shuffled held copy joins as a CERTAIN out — a hand card is never prize-assignable."""
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
    # `certain` edges: the gain side (certain=0) is unchanged, and zero unseen outs still redraw it.
    assert (ml._prize_split_hit(u, d, k, pool, draws)
            == ml._prize_split_hit(u, d, k, pool, draws, certain=0))
    assert isclose(ml._prize_split_hit(0, d, k, pool, draws, certain=1),
                   draw_hit_probability(1, pool, draws))
    assert ml._prize_split_hit(0, d, k, pool, draws) == 0.0


@pytest.mark.req("REQ-WORTH-0001")
def test_keep_cost_deadline_odds_gates_the_worth():
    """``deadline_odds`` factors LINEARLY: 0.0 collapses the worth (an undeployable evolution is dead)."""
    from common.card_worth import keep_cost
    base = keep_cost(30.0, 0.4)                       # deadline_odds defaults to 1.0
    assert keep_cost(30.0, 0.4, 1.0) == base
    assert keep_cost(30.0, 0.4, 0.0) == 0.0
    assert keep_cost(30.0, 0.4, 0.5) == base * 0.5
