"""The forced-discard keep-value equation — its priced ROWS and the v2 needs-assignment that DECIDES.
Each case reads the columns off `_discard_equation_rows` directly AND asserts the decision off
`dec.chosen`, through the shipped keep-value v2 path with no v1 ranking and no ladder beneath it.
ADR-0106 gave `needs.cheapest_removal`'s ranking key a DEADNESS leg above residual worth.
"""
import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

DISCARD = 8
MEGA, SALVATORE, HILDA, WALLYS, CAPE, WATER = 1031, 1189, 1225, 1229, 1159, 3
CINDERACE, FILLER, IGNITION, LILLIES, HARLEQUIN = 666, 999, 17, 1227, 1223


def _setup(hand_ids, *, minc=2, powered=False):
    """A forced Discard over ``hand_ids`` through the SHIPPED path, which keep-value v2 decides
    unconditionally. ``powered`` gives my Active its full attack cost (`active_fully_powered`)."""
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
                           IGNITION: ignition_tags(), LILLIES: ["draw", "shuffle_hand"],
                           HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=funcs, leaf_followups=True)
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
    """Deadness outranks the portable cost shared by two otherwise role-less known cards."""
    pilot, obs = _setup([FILLER, CINDERACE], minc=1)
    by = _by_cid(_rows(pilot, obs))
    assert by[FILLER]["worth"] == 5.0 and by[CINDERACE]["worth"] == 5.0
    assert by[FILLER]["keep"] == 5.0 and by[CINDERACE]["keep"] == 5.0
    assert by[CINDERACE].get("dead_opener") is True
    assert by[CINDERACE]["deadness"] > by[FILLER]["deadness"]           # deadness discriminates…
    assert pilot.explain(obs).chosen == [1]                             # …and the DECIDER acts on it


@pytest.mark.req("REQ-NEEDS-0007")
def test_a_spent_burst_is_fodder_only_once_the_active_is_fully_powered():
    """A `discard_eot` burst is precious UNTIL the Active is fully powered, then it self-discards at
    end of turn anyway. Discard-context ONLY — at a refresh it is still a future attach."""
    unpowered, obs_u = _setup([FILLER, IGNITION], minc=1, powered=False)
    ru = _by_cid(_rows(unpowered, obs_u))
    assert ru[IGNITION]["keep"] == 30.0 and not ru[IGNITION].get("spent_burst")   # protected
    powered, obs_p = _setup([FILLER, IGNITION], minc=1, powered=True)
    rp = _by_cid(_rows(powered, obs_p))
    assert rp[IGNITION]["keep"] == 0.0 and rp[IGNITION]["spent_burst"] is True    # spent -> fodder
    assert rp[IGNITION]["deadness"] > rp[FILLER]["deadness"]
    assert powered.explain(obs_p).chosen == [1]


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_lower_worth_duplicate_sheds_first():
    """Two hand-DUPLICATES both price keep 0, but the worth-10 tutor's redundancy is worth preserving.
    Salvatore sits at index 0, so a pick falling through to hand index sheds the tutor."""
    pilot, obs = _setup([SALVATORE, FILLER, SALVATORE, FILLER], minc=1)
    by = {r["i"]: r for r in _rows(pilot, obs)}
    assert by[0]["cid"] == SALVATORE and by[0]["keep"] == 0.0 and by[0]["worth"] == 10.0
    assert by[1]["cid"] == FILLER and by[1]["keep"] == 0.0 and by[1]["worth"] == 5.0
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.req("REQ-NEEDS-0007")
def test_an_engine_supporter_is_floored_over_disruption_filler():
    pilot, obs = _setup([LILLIES, HARLEQUIN], minc=1)
    by = _by_cid(_rows(pilot, obs))
    assert by[LILLIES]["engine_supporter"] is True and by[LILLIES]["keep"] > 0.0
    assert by[HARLEQUIN]["keep"] == 8.0 and not by[HARLEQUIN].get("engine_supporter")
    assert pilot.explain(obs).chosen == [1]            # pitch the disruption filler, keep the engine


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_full_working_prices_every_band_of_the_hand():
    """A wincon at ROLE_TIER, an ACE SPEC at its fallback, a `clutch_heal` at TAG_TIER, a Basic Energy
    at ENERGY_TIER, and a redundant tutor floored to 0."""
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
    """An Energy the deck's own accel pulls back OUT of the discard is cheap to pitch but NOT dead —
    its ROLE has not expired, and `needs.pitch_gain` already prices the pitch (ADR-0106)."""
    pilot, obs = _setup([MEGA, WATER], minc=1)
    pilot._discard_fuel_cache = frozenset({2})              # Water is a discard-source accel target
    row = _by_cid(_rows(pilot, obs))[WATER]
    assert row["fuel"] is True and row["keep"] == 0.0
    assert row["pitch"] == 1 and row["deadness"] == 0


# Two strict-xfail TARGETs stood here until ADR-0106 closed the gap they named; their rulings were
# folded into the two tests above, which now grade the same boards end to end (rows AND decision).


@pytest.mark.req("REQ-NEEDS-0007")
def test_deadness_is_one_bit_however_many_ways_a_card_is_expired():
    """`deadness` is CATEGORICAL where `pitch` is a count (ADR-0106): nothing has ruled a card expired
    two ways *deader*, and an order asserted from ignorance is what ADR-0091 decision 2 rejects."""
    pilot, obs = _setup([MEGA, SALVATORE, SALVATORE], minc=1)
    row = _by_cid(_rows(pilot, obs))[SALVATORE]
    assert row["redundant_tutor"] is True
    assert row["deadness"] == 1 and row["pitch"] >= 1
    assert pilot.explain(obs).chosen == [1]


@pytest.mark.req("REQ-NEEDS-0005")
def test_v2_prices_duplicate_wincons_as_a_SET_not_a_sum():
    """A per-card `dup_hand` reads BOTH duplicate wincons as free, so a forced discard-2 pitches one.
    Each copy gets the half-tier SUCCESSION slot instead: the pair's set marginal is full+half."""
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
def test_leaf_differencing_stands_alone_as_the_discard_decider():
    """The leaf preserves the exact hand-ledger result without the retired Needs decider."""
    pilot, obs = _setup([MEGA, MEGA, CAPE, WATER, SALVATORE])
    chosen = pilot.explain(obs).chosen
    assert set(chosen) == {3, 4}
    assert not {0, 1} <= set(chosen)
    assert not hasattr(pilot, "_discard_needs_pick")


@pytest.mark.req("REQ-NEEDS-0007")
def test_all_seven_mega_starmie_corrections_run_through_the_leaf_owner():
    """The shipped population is priced by the iterative leaf, never the deferred deck owner."""
    from corpus_helpers import corpus_index
    from train.tune import _build_pilot

    records = [c for c in corpus_index().values()
               if c.agent == "mega_starmie" and (c.obs.get("select") or {}).get("context") == DISCARD]
    assert len(records) == 7
    for record in records:
        pilot = _build_pilot("mega_starmie")[0]
        calls = []
        leaf = pilot._leaf_discard_picks
        pilot._leaf_discard_picks = lambda *args, **kwargs: (calls.append(True) or leaf(*args, **kwargs))
        pilot._deferred_deck_discard_picks = lambda *_args, **_kwargs: pytest.fail(
            "Mega Starmie reached the deferred Needs owner")

        chosen = pilot.explain(record.obs).chosen

        assert calls == [True]
        assert set(record.correct) <= set(chosen)
