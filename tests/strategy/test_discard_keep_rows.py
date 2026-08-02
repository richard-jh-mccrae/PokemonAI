"""The forced-discard keep-value equation — its priced ROWS and the v2 needs-assignment that DECIDES.

Rehomed from `test_discard_shadow.py`, which Issue #261 item 2h deleted with the shadow it was named
after. The shadow was only ever the window: what these cases actually pin is the pricing in
`_discard_equation_rows` (worth, keep, pitch, and the per-card gate flags), which SURVIVES as the
keep-value v2 needs-assignment's input, and the pick v2 makes from it.

So each case is re-pointed one layer down and one layer out: the columns are read off the rows
directly, and every "the equation would pick X" assertion becomes "the DECIDER picks X" — read off
`dec.chosen`, through the shipped `needs_keep_value` path, with no v1 ranking and no ladder beneath
it (both deleted by the same item). That is strictly stronger, and it immediately earned its keep:
**two of the re-pointed cases do not pass**, because the old assertion was grading `eq_pick`, a
number nobody has acted on since `needs_keep_value` shipped ON. Measured on `main` at `ce28431`,
before item 2h touched anything — the shipped decider already sheds the wrong card on both. They are
kept as strict-xfail TARGETs at the bottom of this file, owned by Issue #294.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

DISCARD = 8
MEGA, SALVATORE, HILDA, WALLYS, CAPE, WATER = 1031, 1189, 1225, 1229, 1159, 3
CINDERACE, FILLER, IGNITION, LILLIES, HARLEQUIN = 666, 999, 17, 1227, 1223


def _setup(hand_ids, *, minc=2, powered=False):
    """A forced Discard over ``hand_ids``, through the SHIPPED discard path (`needs_keep_value` ON —
    v2 stands alone since item 2h). ``powered`` gives my Active its full attack cost (so
    ``active_fully_powered``)."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", cardType=3),
        HILDA: CardStat(HILDA, name="Hilda", cardType=3),
        WALLYS: CardStat(WALLYS, name="Wally's", cardType=3),
        CAPE: CardStat(CAPE, name="Hero's Cape", aceSpec=True, hpBonus=100, cardType=2),
        WATER: CardStat(WATER, name="Water", energyType=2, cardType=5),   # 5 = BASIC_ENERGY
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, cardType=0),   # a dead opener
        FILLER: CardStat(FILLER, name="Filler", cardType=1),              # a role-less Item spare
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=0),  # a burst
        LILLIES: CardStat(LILLIES, name="Lillie's", cardType=3),          # a draw engine Supporter
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),     # hand_disruption filler
    })
    funcs = CardFunctions({SALVATORE: ["search", "rush_evolve"], HILDA: ["search"],
                           WALLYS: ["heal", "clutch_heal"], CINDERACE: ["opener"],
                           IGNITION: ["discard_eot"], LILLIES: ["draw", "shuffle_hand"],
                           HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs, needs_keep_value=True)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    active = [{"id": MEGA, "hp": 330, "energies": [0] * 3}] if powered else [None]
    obs = {"current": {"players": [{"active": active, "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": minc, "maxCount": minc, "option": opts}}
    return pilot, obs


def _rows(pilot, obs):
    """The priced rows the decider consumes, keyed by option index."""
    select = obs["select"]
    board = pilot._board(obs, select)
    return pilot._discard_equation_rows(obs, select, board, select["option"])


def _by_cid(rows):
    return {r["cid"]: r for r in rows}


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_pitch_term_separates_dead_weight_from_a_live_spare_among_zero_keep():
    """Finding 3 (the seam-D grill): keep-cost alone cannot RANK a discard — a dreg and a dead card
    both correctly price keep 0. The PITCH-PREFERENCE term breaks that tie by DEADNESS: a spent
    `opener` (Cinderace, its role expired) is actively best gone. The filler sits at index 0, so a
    tie falling through to hand index would take the wrong card."""
    pilot, obs = _setup([FILLER, CINDERACE], minc=1)              # both worth 0 -> both keep 0
    by = _by_cid(_rows(pilot, obs))
    assert by[FILLER]["keep"] == 0.0 and by[CINDERACE]["keep"] == 0.0   # keep cannot separate them
    assert by[CINDERACE].get("dead_opener") is True
    assert by[CINDERACE]["pitch"] > by[FILLER]["pitch"]                 # deadness discriminates…
    assert pilot.explain(obs).chosen == [0]                             # …and the DECIDER does not
                                                                        # act on it — see the TARGET
                                                                        # below (Issue #294)


@pytest.mark.req("REQ-NEEDS-0007")
def test_a_spent_burst_is_fodder_only_once_the_active_is_fully_powered():
    """Ladder-win case `83454549-36`: a `discard_eot` burst (Ignition) is precious UNTIL the Active is
    fully powered — then it is SPENT, self-discards at end of turn anyway, and is dead weight the
    human pitches. Discard-context only (at a refresh it is a future attach, so this is NOT a general
    worth gate)."""
    unpowered, obs_u = _setup([FILLER, IGNITION], minc=1, powered=False)
    ru = _by_cid(_rows(unpowered, obs_u))
    assert ru[IGNITION]["keep"] == 30.0 and not ru[IGNITION].get("spent_burst")   # protected
    powered, obs_p = _setup([FILLER, IGNITION], minc=1, powered=True)
    rp = _by_cid(_rows(powered, obs_p))
    assert rp[IGNITION]["keep"] == 0.0 and rp[IGNITION]["spent_burst"] is True    # spent -> fodder
    assert rp[IGNITION]["pitch"] > rp[FILLER]["pitch"]
    assert powered.explain(obs_p).chosen == [0]           # …and again the DECIDER does not act on it


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_lower_worth_duplicate_sheds_first():
    """Ladder-win case `83967840-54` (sets-not-sums): two hand-DUPLICATE cards both price keep 0 (a
    sibling copies each), but a worth-10 tutor's redundancy is worth preserving over a worth-0 draw
    Supporter's. Salvatore (worth 10) sits at index 0, so a pick falling through to hand index would
    shed the tutor over the filler."""
    pilot, obs = _setup([SALVATORE, FILLER, SALVATORE, FILLER], minc=1)
    by = {r["i"]: r for r in _rows(pilot, obs)}
    assert by[0]["cid"] == SALVATORE and by[0]["keep"] == 0.0 and by[0]["worth"] == 10.0
    assert by[1]["cid"] == FILLER and by[1]["keep"] == 0.0 and by[1]["worth"] == 0.0
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.req("REQ-NEEDS-0007")
def test_an_engine_supporter_is_floored_over_disruption_filler():
    pilot, obs = _setup([LILLIES, HARLEQUIN], minc=1)
    by = _by_cid(_rows(pilot, obs))
    assert by[LILLIES]["engine_supporter"] is True and by[LILLIES]["keep"] > 0.0
    assert by[HARLEQUIN]["keep"] == 0.0 and not by[HARLEQUIN].get("engine_supporter")
    assert pilot.explain(obs).chosen == [1]            # pitch the disruption filler, keep the engine


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_full_working_prices_every_band_of_the_hand():
    """The keep bands, end to end on one hand: a wincon at ROLE_TIER, an ACE SPEC at its fallback, a
    `clutch_heal` at TAG_TIER, a Basic Energy at ENERGY_TIER, and a redundant tutor floored to 0."""
    pilot, obs = _setup([MEGA, CAPE, WALLYS, WATER, SALVATORE])
    by = _by_cid(_rows(pilot, obs))
    assert by[MEGA]["worth"] == 30.0 and by[MEGA]["keep"] == 30.0
    assert by[CAPE]["keep"] == 25.0                        # ACE SPEC fallback
    assert by[WALLYS]["keep"] == 20.0                      # clutch_heal TAG_TIER
    assert by[WATER]["keep"] == 8.0
    assert by[SALVATORE]["worth"] == 10.0 and by[SALVATORE]["keep"] == 0.0
    assert by[SALVATORE].get("redundant_tutor") is True


@pytest.mark.req("REQ-NEEDS-0007")
def test_a_discard_source_accel_energy_zeroes_its_keep():
    """The `fuel` bit: an Energy the deck's own accel pulls back OUT of the discard is not lost by
    being discarded, so its keep floor drops to 0."""
    pilot, obs = _setup([MEGA, WATER], minc=1)
    pilot._discard_fuel_cache = frozenset({2})              # Water is a discard-source accel target
    row = _by_cid(_rows(pilot, obs))[WATER]
    assert row["fuel"] is True and row["keep"] == 0.0


# ── TARGETS: the two ladder-win rulings the SHIPPED decider does not honour (Issue #294) ─────────
# Strict xfail, not deletion. Both cases were RULED (`83454549-36`, and the seam-D grill's Finding-3
# dead-opener case) and both are decided the wrong way in shipped play TODAY — measured on `main` at
# ce28431, before item 2h touched anything: `needs_keep_value` ON picks [0] where v1 and the ladder
# both pick [1]. `cheapest_removal` is indifferent among equal-keep cards, so the deadness the rows
# price never reaches the assignment.
#
# Item 2h is what makes this worth pinning: it deletes the shadow's `eq_pick` and the v1/ladder
# fallback, i.e. the last two places the gap was visible. A ruling whose only witness is deleted is
# the Issue #238 failure — 13 Corrections closed as "covered" by rungs a deletion pass had removed.
# Strict, so the day the assignment learns deadness these go RED rather than quietly green.

@pytest.mark.xfail(strict=True, reason="Issue #294: cheapest_removal is blind to the pitch term")
@pytest.mark.req("REQ-NEEDS-0007")
def test_TARGET_the_decider_sheds_the_dead_opener_over_the_live_spare():
    pilot, obs = _setup([FILLER, CINDERACE], minc=1)
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.xfail(strict=True, reason="Issue #294: cheapest_removal is blind to the pitch term")
@pytest.mark.req("REQ-NEEDS-0007")
def test_TARGET_the_decider_sheds_the_spent_burst_over_the_live_spare():
    pilot, obs = _setup([FILLER, IGNITION], minc=1, powered=True)
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.req("REQ-NEEDS-0005")
def test_v2_prices_duplicate_wincons_as_a_SET_not_a_sum():
    """THE v2 headline (the naivety v1 could not fix): v1's per-card `dup_hand` read BOTH duplicate
    wincons as free (keep 0 each — the sibling covers), so a forced discard-2 pitched a Mega. v2
    gives each copy the half-tier SUCCESSION slot — a spare wincon insures the line against
    attrition, never free — so the pair's set marginal is full+half and the true spares go instead."""
    pilot, obs = _setup([MEGA, MEGA, CAPE, WATER, SALVATORE])
    select = obs["select"]
    board = pilot._board(obs, select)
    rows = pilot._discard_equation_rows(obs, select, board, select["option"])
    keeps, eq2_pick = pilot._needs_v2(obs, board, rows, select["maxCount"])
    megas = [k for r, k in zip(rows, keeps) if r["cid"] == MEGA]
    assert len(megas) == 2 and all(k == 15.0 for k in megas)   # the succession marginal
    assert not {0, 1} <= set(eq2_pick)                          # NEVER pitch the pair
    assert set(eq2_pick) == {3, 4}                              # the spares go instead


@pytest.mark.req("REQ-NEEDS-0006")
def test_v2_STANDS_ALONE_as_the_discard_decider():
    """The per-family swap, now unhedged (item 2h): the v2 needs-assignment IS the discard decider —
    there is no seam-D v1 under it and no `_DISCARD` ladder under that. The duplicate-wincon pair v1
    pitched survives the DECISION, not just the shadow."""
    pilot, obs = _setup([MEGA, MEGA, CAPE, WATER, SALVATORE])
    assert set(pilot.explain(obs).chosen) == {3, 4}
    assert not {0, 1} <= set(pilot.explain(obs).chosen)         # both Megas kept
