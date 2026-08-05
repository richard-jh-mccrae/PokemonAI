"""Deferred-disruption cluster — two opponent-model priors authored default-OFF (weight 0, ADR-0009
by-id override), so these tests exercise the TRIGGER (`when()`), not a score delta:

  * `disrupt-the-tailored-hand`     — the MIRROR of `strip-the-stacked-engine-hand`: fires on a hand the
                                      opponent TAILORED DOWN (dumped last turn + now small), not a big one.
  * `unfair-stamp-comeback-posture` — DEFENSIVE half of the Unfair-Stamp doctrine: after I take a KO into
                                      an opponent that runs a post-KO hand disruptor, demote emptying my
                                      already-low hand. DOUBLE-inert (weight 0 AND trigger normally False).

Board is constructed directly (`common.pilot.Board(...)`) with only the relevant fields set; a Context
carries the option_type + tags the trigger reads (cf. tests/strategy/test_clutch_heal.py).
"""
from common.pilot import Board, Context
from common.strategy import Plan
from common.strategy.baseline import DISRUPTION_HYPOTHESES
from common.strategy.context import _PLAY, _ATTACH

_TAILORED = next(h for h in DISRUPTION_HYPOTHESES if h.id == "disrupt-the-tailored-hand")
_COMEBACK = next(h for h in DISRUPTION_HYPOTHESES if h.id == "unfair-stamp-comeback-posture")


def _ctx(*, option_type=_PLAY, tags=("hand_disruption",), board=None):
    return Context(plan=Plan.RACE, select_context=0, option_type=option_type, card_id=1,
                   tags=list(tags), board=board or Board())


# ── both ship default-OFF: wired + telemetry-visible, zero live weight until the ladder tunes ──

def test_both_hypotheses_ship_weight_zero_and_assumed():
    for h in (_TAILORED, _COMEBACK):
        assert h.weight == 0
        assert h.status == "assumed"


# ── disrupt-the-tailored-hand: dump + small hand fires; big hand / no-dump stays silent ──

def test_tailored_hand_fires_on_dump_plus_small_hand():
    board = Board(opp_last_turn_dumped=True, opp_hand_size=3)
    assert bool(_TAILORED.when(_ctx(board=board)))


def test_tailored_hand_silent_on_big_hand():
    # dumped last turn, but the hand is NOT tailored down small — nothing to scatter.
    board = Board(opp_last_turn_dumped=True, opp_hand_size=6)
    assert not _TAILORED.when(_ctx(board=board))


def test_tailored_hand_silent_without_the_dump():
    # small hand but no last-turn dump: no evidence they committed to a few kept cards.
    board = Board(opp_last_turn_dumped=False, opp_hand_size=2)
    assert not _TAILORED.when(_ctx(board=board))


def test_tailored_hand_needs_hand_disruption_tag_and_a_play():
    board = Board(opp_last_turn_dumped=True, opp_hand_size=2)
    assert not _TAILORED.when(_ctx(tags=["energy_denial"], board=board))   # wrong card
    assert not _TAILORED.when(_ctx(option_type=_ATTACH, board=board))       # not a PLAY


# ── unfair-stamp-comeback-posture: fires only on took_ko AND comeback_disruptor AND low hand ──

def test_comeback_posture_fires_when_all_three_conditions_hold():
    board = Board(opp_took_ko_this_turn=True, opp_comeback_disruptor=True, my_hand_size=2)
    assert bool(_COMEBACK.when(_ctx(board=board)))
    assert bool(_COMEBACK.when(_ctx(tags=["shuffle_hand"], board=board)))   # either hand-emptying tag


def test_comeback_posture_silent_without_the_disruptor_read():
    # DOUBLE-inert: opp_comeback_disruptor is False until a Brief asserts it, so the trigger is
    # normally False even before the weight-0 gate.
    board = Board(opp_took_ko_this_turn=True, opp_comeback_disruptor=False, my_hand_size=2)
    assert not _COMEBACK.when(_ctx(board=board))


def test_comeback_posture_silent_when_i_did_not_take_a_ko():
    board = Board(opp_took_ko_this_turn=False, opp_comeback_disruptor=True, my_hand_size=2)
    assert not _COMEBACK.when(_ctx(board=board))


def test_comeback_posture_silent_when_my_hand_is_not_low():
    # a healthy hand survives their Stamp — no demotion needed (conservative floor).
    board = Board(opp_took_ko_this_turn=True, opp_comeback_disruptor=True, my_hand_size=3)
    assert not _COMEBACK.when(_ctx(board=board))


def test_comeback_posture_needs_a_hand_emptying_play():
    board = Board(opp_took_ko_this_turn=True, opp_comeback_disruptor=True, my_hand_size=1)
    assert not _COMEBACK.when(_ctx(tags=["energy_denial"], board=board))    # not a hand-spend
    assert not _COMEBACK.when(_ctx(option_type=_ATTACH, board=board))        # not a PLAY
