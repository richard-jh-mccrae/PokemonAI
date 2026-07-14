"""Deferred-planner cluster — four opponent-model-driven / new-planner consumers wired DEFAULT-OFF so
they change NO live behavior until the ladder validates them (cf. tests/agents/test_runtime.py for the
PROFILE contract and tests/strategy/test_deferred_disruption_cluster.py for the weight-0 trigger idiom):

  * BUILD 1 `ko_target_whiff`       — KO/snipe-target TIEBREAK toward the body the opponent is least able
                                      to replace (lowest `copies_left_odds`); pure tiebreak, fails OPEN.
  * BUILD 2 `opp_resource_reads`    — a sub-prize nudge toward pressing KO/grind lines when the opponent
                                      is near deck-out (`opp_deckout_in_turns`, SOUND).
  * BUILD 3 `enabler_item_composer` — the ko_for_prizes Item-tutor→evolve→KO composer (prefer a cheaper
                                      Item enabler over the scarce Supporter tutor).
  * BUILD 4 `dont-spend-unneeded-supporter` — a weight-0 Hypothesis gated on the new `Board.turn_goal_satisfied`
                                      predicate (fails SAFE to False).

These tests exercise the FLAG DEFAULTS (all off), the inert code paths, and the trigger — never a live
score delta (every seam is off / weight 0).
"""
import types

from common.cards import CardFunctions as _CardFunctions
from common.pilot import Board, Context, Pilot
from common.runtime import PROFILE
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy
from common.strategy.baseline import SEQUENCING_HYPOTHESES
from common.strategy.context import _ATTACH, _PLAY
from common.strategy.planner import _PLANNER_DECKOUT_TURNS, _PLANNER_DECKOUT_W
from pilot_helpers import PLAY, make_select, opt, state

_NEW_FLAGS = ("ko_target_whiff", "opp_resource_reads", "enabler_item_composer")
_SUPPORTER = next(h for h in SEQUENCING_HYPOTHESES if h.id == "dont-spend-unneeded-supporter")


def _pilot(**kw) -> Pilot:
    """A lib-free Pilot (no engine, no scout) for exercising the pure planner/board helpers."""
    return Pilot(Strategy(), [1] * 60, **kw)


# ══════════════════════════════ shared: every new flag ships OFF ══════════════════════════════

def test_every_new_profile_flag_defaults_false():
    for flag in _NEW_FLAGS:
        assert flag in PROFILE, f"{flag} missing from runtime PROFILE"
        assert PROFILE[flag] is False, f"{flag} must ship OFF"


def test_default_built_pilot_reads_the_flags_off():
    pilot = _pilot()
    for flag in _NEW_FLAGS:
        assert getattr(pilot, flag) is False


# ══════════════════════════════ BUILD 1 — ko_target_whiff tiebreak ══════════════════════════════

def _opp_stub(odds_by_id):
    return types.SimpleNamespace(copies_left_odds=lambda cid: odds_by_id.get(cid, 1.0))


def test_whiff_odds_reads_the_opponent_model():
    pilot = _pilot()
    board = Board(opponent=_opp_stub({101: 0.2, 102: 0.9}))
    assert pilot._whiff_odds(board, {"id": 101}) == 0.2
    assert pilot._whiff_odds(board, {"id": 102}) == 0.9


def test_whiff_odds_fails_open_without_a_read():
    pilot = _pilot()
    assert pilot._whiff_odds(Board(), {"id": 101}) == 1.0            # no Opponent Model → assume replaceable
    board = types.SimpleNamespace(opponent=types.SimpleNamespace(
        copies_left_odds=lambda cid: (_ for _ in ()).throw(RuntimeError())))
    assert pilot._whiff_odds(board, {"id": 101}) == 1.0             # a raising model degrades to 1.0


def test_whiff_tiebreak_is_pure_lower_odds_among_equal_rank():
    # The exact key the flag-ON branch uses: (rank, -whiff_odds). Rank dominates; among equal ranks the
    # LOWER-odds (least-replaceable) body wins — never a reorder that promotes a lesser threat.
    pilot = _pilot()
    board = Board(opponent=_opp_stub({101: 0.9, 102: 0.2}))
    ranked = [(5, {"id": 101}), (5, {"id": 102})]                   # equal rank
    _, top = max(ranked, key=lambda t: (t[0], -pilot._whiff_odds(board, t[1])))
    assert top["id"] == 102                                          # lower odds preferred on the tie
    ranked = [(9, {"id": 101}), (5, {"id": 102})]                   # unequal rank
    _, top = max(ranked, key=lambda t: (t[0], -pilot._whiff_odds(board, t[1])))
    assert top["id"] == 101                                          # higher rank wins despite worse odds


# ══════════════════════════════ BUILD 2 — opp_resource_reads deck-out nudge ══════════════════════════════

def test_deckout_grind_bonus_inert_when_flag_off():
    pilot = _pilot()                                                # opp_resource_reads default False
    assert pilot._deckout_grind_bonus(Board(opp_deckout_in_turns=1)) == 0.0


def test_deckout_grind_bonus_fires_only_near_deckout_when_on():
    pilot = _pilot(opp_resource_reads=True)
    assert pilot._deckout_grind_bonus(Board(opp_deckout_in_turns=_PLANNER_DECKOUT_TURNS)) == _PLANNER_DECKOUT_W
    assert pilot._deckout_grind_bonus(Board(opp_deckout_in_turns=_PLANNER_DECKOUT_TURNS + 1)) == 0.0
    assert pilot._deckout_grind_bonus(Board(opp_deckout_in_turns=None)) == 0.0   # unknown = silent (sound)


def test_deckout_bonus_stays_sub_prize():
    from common.strategy.context import KO_SCORE
    assert _PLANNER_DECKOUT_W < KO_SCORE                            # never reorders a real prize delta


# ══════════════════════════════ BUILD 3 — enabler_item_composer ══════════════════════════════

def _item_pilot(item_id, tags, card_type=1, **kw):
    stats = DictCardStatProvider({item_id: CardStat(cardId=item_id, cardType=card_type)})
    fns = _CardFunctions({item_id: tags})
    return _pilot(stats=stats, functions=fns, **kw)


def _play_from_hand(item_id):
    sel = make_select([opt(PLAY, index=0)], current=state(hand=[item_id]))
    return sel, sel["select"], sel["select"]["option"][0]


def test_is_item_pokemon_tutor_recognizes_a_mega_fetch_item():
    pilot = _item_pilot(1145, ["search", "tutor_mega"])            # Mega Signal shape (Item + tutor_mega)
    obs, sel, option = _play_from_hand(1145)
    assert pilot._is_item_pokemon_tutor(obs, sel, option) is True


def test_is_item_pokemon_tutor_rejects_a_supporter_and_a_non_tutor():
    # A Supporter (cardType 3) with the same fetch tag is NOT an Item tutor — it's the scarce slot.
    pilot = _item_pilot(9001, ["search", "tutor_mega"], card_type=3)
    obs, sel, option = _play_from_hand(9001)
    assert pilot._is_item_pokemon_tutor(obs, sel, option) is False
    # An Item with no pokemon-fetch tag (energy tutor) is not this composer's first step.
    pilot = _item_pilot(9002, ["search", "tutor_energy"], card_type=1)
    obs, sel, option = _play_from_hand(9002)
    assert pilot._is_item_pokemon_tutor(obs, sel, option) is False


def test_composer_branch_is_gated_off_by_default():
    # The flag default OFF is the gate: `_ko_for_prizes_lines` only enters the Item-composer branch when
    # `enabler_item_composer` is True, so with the default it is inert regardless of the menu.
    assert _pilot().enabler_item_composer is False
    assert _item_pilot(1145, ["tutor_mega"]).enabler_item_composer is False


def test_composer_no_ops_without_stats():
    # Fail-safe: no stat provider → no composite line (never crashes).
    pilot = _pilot(enabler_item_composer=True)
    obs, sel, option = _play_from_hand(1145)
    assert pilot._item_evolve_ko_candidate(obs, sel, Board(), option, {"id": 1, "hp": 60}, {}, 1, True) is None


# ══════════════════════════════ BUILD 4 — turn_goal_satisfied + the Hypothesis ══════════════════════════════

def test_turn_goal_satisfied_field_exists_and_defaults_false():
    assert Board().turn_goal_satisfied is False


def test_turn_goal_satisfied_derivation_fails_safe_to_false():
    pilot = _pilot()
    assert pilot._turn_goal_satisfied(Board(), None) is False        # no plan → False
    from common.strategy import GamePlan
    board = Board(game_plan=GamePlan(directed_goal="ko_on_path", confidence=0.9), line_ready=True)
    assert pilot._turn_goal_satisfied(board, None) is False          # even a confident plan → False (sound)


def test_supporter_hypothesis_ships_weight_zero_and_assumed():
    assert _SUPPORTER.weight == 0
    assert _SUPPORTER.status == "assumed"


def _ctx(*, option_type=_PLAY, tags=("draw",), card_type=3, board=None):
    stat = CardStat(cardId=1, cardType=card_type)
    return Context(plan=Plan.RACE, select_context=0, option_type=option_type, card_id=1,
                   tags=list(tags), stat=stat, board=board or Board())


def test_supporter_when_fires_on_a_satisfied_goal():
    board = Board(turn_goal_satisfied=True)
    assert bool(_SUPPORTER.when(_ctx(board=board)))                          # draw supporter
    assert bool(_SUPPORTER.when(_ctx(tags=["gust"], board=board)))          # Boss's Orders
    assert bool(_SUPPORTER.when(_ctx(tags=["rush_evolve"], board=board)))   # evolution tutor


def test_supporter_when_silent_when_goal_not_satisfied():
    assert not _SUPPORTER.when(_ctx(board=Board(turn_goal_satisfied=False)))


def test_supporter_when_silent_off_target():
    board = Board(turn_goal_satisfied=True)
    assert not _SUPPORTER.when(_ctx(card_type=1, board=board))              # an Item, not a Supporter
    assert not _SUPPORTER.when(_ctx(tags=["dig"], board=board))             # a genuine dig keeps value
    assert not _SUPPORTER.when(_ctx(option_type=_ATTACH, board=board))      # not a PLAY
