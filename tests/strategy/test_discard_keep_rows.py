"""The forced-discard keep-value equation — its priced ROWS and the v2 needs-assignment that DECIDES.

Rehomed from `test_discard_shadow.py`, which Issue #261 item 2h deleted with the shadow it was named
after. The shadow was only ever the window: what these cases actually pin is the pricing in
`_discard_equation_rows` (worth, keep, pitch, and the per-card gate flags), which SURVIVES as the
keep-value v2 needs-assignment's input, and the pick v2 makes from it.

So each case is re-pointed one layer down and one layer out: the columns are read off the rows
directly, and every "the equation would pick X" assertion becomes "the DECIDER picks X" — read off
`dec.chosen`, through the shipped keep-value v2 path, with no v1 ranking and no ladder beneath
it (both deleted by the same item). That is strictly stronger, and it immediately earned its keep:
**two of the re-pointed cases did not pass**, because the old assertion was grading `eq_pick`, a
number nobody had acted on since v2 took the select. They were held as strict-xfail
TARGETs owned by Issue #294; ADR-0106 closed that gap by giving `needs.cheapest_removal`'s
ranking key a DEADNESS leg above residual worth, and both are now asserted outright inside the two
tests that price their rows.
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
    """A forced Discard over ``hand_ids``, through the SHIPPED discard path — keep-value v2 decides
    it unconditionally (it stands alone since Issue #261 item 2h, and Issue #319 deleted the
    `needs_keep_value` flag that had stopped gating it). ``powered`` gives my Active its full attack
    cost (so ``active_fully_powered``)."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", cardType=3),
        HILDA: CardStat(HILDA, name="Hilda", cardType=3),
        WALLYS: CardStat(WALLYS, synthetic=True, name="Wally's", cardType=3),
        CAPE: CardStat(CAPE, synthetic=True, name="Hero's Cape", aceSpec=True, hpBonus=100, cardType=2),
        WATER: CardStat(WATER, synthetic=True, name="Water", energyType=2, cardType=5),   # 5 = BASIC_ENERGY
        CINDERACE: CardStat(CINDERACE, synthetic=True, name='Cinderace', hp=160, cardType=0),   # a dead opener
        FILLER: CardStat(FILLER, synthetic=True, name="Filler", cardType=1),              # a role-less Item spare
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=0),  # a burst
        LILLIES: CardStat(LILLIES, synthetic=True, name="Lillie's", cardType=3),          # a draw engine Supporter
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),     # hand_disruption filler
    })
    funcs = CardFunctions({SALVATORE: ["search", "rush_evolve"], HILDA: ["search"],
                           WALLYS: ["heal", "clutch_heal"], CINDERACE: ["opener"],
                           IGNITION: ["discard_eot", "provides:1", "provides_evo:3"], LILLIES: ["draw", "shuffle_hand"],
                           HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs)
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
    assert by[CINDERACE]["deadness"] > by[FILLER]["deadness"]           # deadness discriminates…
    assert pilot.explain(obs).chosen == [1]                             # …and the DECIDER acts on it
                                                                        # (ADR-0106 — the exact
                                                                        # tie used to fall to the
                                                                        # menu index and take [0])


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
    assert rp[IGNITION]["deadness"] > rp[FILLER]["deadness"]
    # …and the DECIDER acts on it (ADR-0106). This is the case residual worth alone gets
    # BACKWARDS: the spent burst still carries catalog worth 30 against the filler's 0, so a
    # worth-first tie-break sheds the live spare and keeps the corpse. Deadness ranks above it.
    assert powered.explain(obs_p).chosen == [1]


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
def test_a_discard_source_accel_energy_zeroes_its_keep_but_is_not_DEAD():
    """The `fuel` bit: an Energy the deck's own accel pulls back OUT of the discard is not lost by
    being discarded, so its keep floor drops to 0.

    It is cheap to pitch and it is NOT dead weight, which is why the two terms split (ADR-0106):
    its ROLE has not expired, and `needs.pitch_gain` already prices the pitch in the removal SCORE.
    Ranking on it as well double-prices it and sheds an Energy that is the only funder of an attack
    (`83966336|0|decision|27`)."""
    pilot, obs = _setup([MEGA, WATER], minc=1)
    pilot._discard_fuel_cache = frozenset({2})              # Water is a discard-source accel target
    row = _by_cid(_rows(pilot, obs))[WATER]
    assert row["fuel"] is True and row["keep"] == 0.0
    assert row["pitch"] == 1 and row["deadness"] == 0


# The two strict-xfail TARGETs that stood here are GONE because the gap they named is closed
# (ADR-0106, Issue #294): `cheapest_removal`'s ranking key gained a deadness leg above residual
# worth, so the assignment acts on the deadness the rows have always priced. Their assertions were
# `chosen == [1]` on exactly the two boards the first two tests above already build, so folding them
# up is what removes the duplication rather than leaving one ruling stated twice — each of those
# tests now grades its ruled case end to end, rows AND decision (`83454549-36` for the spent burst,
# the seam-D grill's Finding 3 for the dead opener). Recorded rather than silently dropped, because
# a deleted xfail and a deleted ruling look the same in a diff.


@pytest.mark.req("REQ-NEEDS-0007")
def test_deadness_is_one_bit_however_many_ways_a_card_is_expired():
    """`deadness` is CATEGORICAL where `pitch` is a count (ADR-0106). Nothing has ruled that a
    card expired two ways is *deader* than one expired a single way, and an order asserted from
    ignorance is what ADR-0091 decision 2 rejects — so the ranking leg reads one bit. Salvatore is
    both a `redundant_tutor` (the wincon is in hand) and a hand DUPLICATE, and the Mega in hand makes
    a second tutor genuinely dead; its `pitch` count still records every reason."""
    pilot, obs = _setup([MEGA, SALVATORE, SALVATORE], minc=1)
    row = _by_cid(_rows(pilot, obs))[SALVATORE]
    assert row["redundant_tutor"] is True
    assert row["deadness"] == 1 and row["pitch"] >= 1
    assert pilot.explain(obs).chosen != [0]                 # never the Mega


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
