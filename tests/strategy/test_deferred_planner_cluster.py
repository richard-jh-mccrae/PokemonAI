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
from common.effects import CardEffects as _CardEffects
from common.pilot import Board, Context, Pilot
from common.runtime import PROFILE
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy
from common.strategy.baseline import SEQUENCING_HYPOTHESES
from common.strategy.context import KO_SCORE, _ATTACH, _PLAY
from common.strategy.planner import (_PLANNER_DECKOUT_TURNS, _PLANNER_DECKOUT_W,
                                     _PLANNER_ENABLER_FREE, _PLANNER_ENABLER_ITEM_BASE,
                                     _PLANNER_ENABLER_ITEM_SLOT, _RARE_CANDY_ID)
from pilot_helpers import PLAY, make_select, opt, poke, state

_NEW_FLAGS = ("ko_target_whiff", "opp_resource_reads", "enabler_item_composer")
_SUPPORTER = next(h for h in SEQUENCING_HYPOTHESES if h.id == "dont-spend-unneeded-supporter")


def _pilot(**kw) -> Pilot:
    """A lib-free Pilot (no engine, no scout) for exercising the pure planner/board helpers."""
    return Pilot(Strategy(), [1] * 60, **kw)


def _deck_pilot(deck, **kw) -> Pilot:
    """A lib-free Pilot with a caller-supplied deck (the composer reads ``self.deck``)."""
    return Pilot(Strategy(), deck, **kw)


# ═══════════════ shared: the three flags are ARMED-ON in the PROFILE, OFF at the ctor default ═══════════════

def test_new_profile_flags_are_armed_on_for_ladder_testing():
    # Armed ON in the deployment PROFILE (2026-07-14, ladder-testing) — a deliberate opt-in, verified
    # by the full suite showing zero correction-corpus regressions with the flags on.
    for flag in _NEW_FLAGS:
        assert flag in PROFILE, f"{flag} missing from runtime PROFILE"
        assert PROFILE[flag] is True, f"{flag} is armed ON for ladder-testing"


def test_new_flags_still_default_off_at_the_ctor():
    # The pilot CTOR default stays False (PROFILE is the deployment override) so the inert-when-off
    # unit tests below remain meaningful and a raw-constructed Pilot is unaffected.
    pilot = _pilot()
    for flag in _NEW_FLAGS:
        assert getattr(pilot, flag) is False, f"{flag} ctor default must stay False"


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
    assert pilot._item_evolve_ko_candidate(obs, sel, Board(), option, {"id": 1, "hp": 60}, {}, True) is None


# ══════════════════════════════ BUILD 4 — one-Supporter-per-turn slot accounting ══════════════════════════════
#
# Replaces the flat `_PLANNER_ENABLER_ITEM=4` proxy: the Item enabler's advantage over the Supporter-tutor
# path is CONDITIONAL on actually preserving the scarce one-Supporter-per-turn slot. The gap WIDENS only when
# a slot-competing Supporter (a `gust` Boss's Orders / another high-value Supporter) is in hand, and SHRINKS
# otherwise. Everything stays sub-prize — a same-KO enabler tiebreak, never a reorder over a real prize.

def _slot_pilot(hand_ids, stat_by_id):
    return _pilot(stats=DictCardStatProvider(stat_by_id),
                  functions=_CardFunctions({cid: [] for cid in stat_by_id}),
                  enabler_item_composer=True), Board(hand_ids=frozenset(hand_ids))


def test_item_enabler_cost_bands_stay_ordered_and_sub_prize():
    # free-evolve (8) > item-when-slot-competed (6) > item-when-uncompeted (2) > supporter-tutor (0);
    # all comfortably below one prize (KO_SCORE), so they only ever break a same-KO enabler tie.
    assert _PLANNER_ENABLER_FREE > _PLANNER_ENABLER_ITEM_SLOT > _PLANNER_ENABLER_ITEM_BASE > 0
    assert _PLANNER_ENABLER_ITEM_SLOT < KO_SCORE


def test_item_gap_widens_when_a_gust_supporter_competes_for_the_slot():
    # A gust Supporter (Boss's Orders) in hand wants THIS turn's one Supporter slot — the Item enabler that
    # keeps the slot free earns the WIDER credit.
    boss = CardStat(cardId=700, cardType=3)                          # cardType 3 = Supporter
    pilot = _pilot(stats=DictCardStatProvider({700: boss}),
                   functions=_CardFunctions({700: ["gust"]}))
    board = Board(hand_ids=frozenset({700}), no_supporter_in_hand=False)
    assert pilot._gust_supporter_in_hand(board) is True
    assert pilot._item_enabler_cost(board) == _PLANNER_ENABLER_ITEM_SLOT


def test_item_gap_widens_for_any_high_value_supporter_in_hand():
    # A non-gust Supporter also claims the slot (`no_supporter_in_hand` False) → wide credit.
    supp = CardStat(cardId=701, cardType=3)
    pilot = _pilot(stats=DictCardStatProvider({701: supp}),
                   functions=_CardFunctions({701: ["draw"]}))
    board = Board(hand_ids=frozenset({701}), no_supporter_in_hand=False)
    assert pilot._gust_supporter_in_hand(board) is False            # not a gust, but still a Supporter
    assert pilot._item_enabler_cost(board) == _PLANNER_ENABLER_ITEM_SLOT


def test_item_gap_shrinks_when_no_supporter_competes():
    # No Supporter in hand → keeping the slot is nearly free → the SHRUNK credit.
    pilot = _pilot(stats=DictCardStatProvider({}), functions=_CardFunctions({}))
    board = Board(hand_ids=frozenset(), no_supporter_in_hand=True)
    assert pilot._gust_supporter_in_hand(board) is False
    assert pilot._item_enabler_cost(board) == _PLANNER_ENABLER_ITEM_BASE


# ══════════════ BUILD 3+5 — SOUND energy-enabler chaining (tutor_energy unlock; accel under-fired) ══════════════
#
# The composer caps the attacker's Energy at body_energy + extra (extra ≤ 1 manual attach). A KO that needs
# MORE Energy becomes visible ONLY when that extra attach is PROVABLY available this turn: a playable
# `tutor_energy` card can fetch the single manual attach the plain line lacks. An accelerator's extra Energy
# is deliberately NOT counted (unbounded for a composed attacker) — the line under-fires instead.

_EVO_ID, _BASE_ID, _ITEM_ID, _ETUTOR_ID, _AID = 202, 201, 203, 204, 9902
_ENERGY_ID = 205                          # the Basic Energy the tutor actually fetches


def _energy_chain_pilot(*, energy_tutor_is_supporter=False, deck=None):
    """Pilot whose deck holds a Mega evolution (`_EVO_ID`, needs 2 Energy to KO) of an in-play Basic
    (`_BASE_ID`), plus a `tutor_energy` card (`_ETUTOR_ID`, Item by default) that could supply the 2nd attach."""
    etutor_type = 3 if energy_tutor_is_supporter else 1
    stats = DictCardStatProvider({
        _BASE_ID: CardStat(cardId=_BASE_ID, name="Base", hp=70),                  # Basic (evolvesFrom None)
        _EVO_ID: CardStat(cardId=_EVO_ID, name="Evo", hp=200, megaEx=True,
                          evolvesFrom="Base", attacks=(_AID,)),
        _ITEM_ID: CardStat(cardId=_ITEM_ID, cardType=1),                          # the Mega Signal Item
        _ETUTOR_ID: CardStat(cardId=_ETUTOR_ID, cardType=etutor_type),
        _ENERGY_ID: CardStat(cardId=_ENERGY_ID, cardType=5, energyType=2),        # a Basic Energy
    }, {_AID: AttackStat(attackId=_AID, damage=200, cost=2, damageMax=200)})      # 2-Energy 200-dmg KO
    fns = _CardFunctions({_ITEM_ID: ["tutor_mega"], _ETUTOR_ID: ["tutor_energy"]})
    # The Attach Budget reads the YIELD off an Effect Clause, never off the tag — tags only route
    # (ADR-0067). A tagged card with no clause contributes ZERO, so the fixture has to say what its
    # tutor actually fetches, exactly as `test_attach_budget_coverage.py` demands of a shipped deck.
    effects = _CardEffects({_ETUTOR_ID: [{"kind": "fetch", "target": "basic_energy",
                                          "zone": "deck"}]})
    return _deck_pilot([_EVO_ID] + (deck or [_BASE_ID] * 49 + [_ENERGY_ID] * 10),
                  stats=stats, functions=fns,
                  effects=effects, enabler_item_composer=True)


def _prime(pilot, obs):
    """Build the StateModel the planner reads. In production `_board` always runs first; a test that
    calls a planner internal straight has to establish the same precondition or it is measuring a
    fail-closed zero."""
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    return pilot


def _energy_chain_obs(*, hand):
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(_BASE_ID, energy=1, hp=70),
                                    opp_active=poke(320, hp=190), turn=2, hand=hand))
    return obs, obs["select"], obs["select"]["option"][0]


def _chain_board(**kw):
    base = dict(hand_ids=frozenset({_ITEM_ID, _ETUTOR_ID}), deck_known_counts={_EVO_ID: 1},
                basic_energy_in_deck=True, no_supporter_in_hand=True)
    base.update(kw)
    return Board(**base)


def test_composer_finds_the_ko_only_with_the_tutored_attach():
    obs, sel, option = _energy_chain_obs(hand=[_ITEM_ID, _ETUTOR_ID])
    pilot = _prime(_energy_chain_pilot(), obs)
    opp = {"id": 320, "hp": 190}
    # base extra=0 (no reusable Energy in hand): the tutor makes the single attach available → 200-dmg KO.
    got = pilot._item_evolve_ko_candidate(obs, sel, _chain_board(), option, opp, {}, True)
    assert got is not None and got[0] == 1                              # a 1-prize KO composed
    # Remove the tutor — from the HAND, not just from the hand-built Board: the Attach Budget reads
    # the model's hand, so a Board that disagrees with the observation is describing two boards.
    obs2, sel2, option2 = _energy_chain_obs(hand=[_ITEM_ID])
    bare = _prime(_energy_chain_pilot(), obs2)
    none = bare._item_evolve_ko_candidate(obs2, sel2, _chain_board(hand_ids=frozenset({_ITEM_ID})),
                                          option2, opp, {}, True)
    assert none is None                     # body's 1 Energy can't pay the 2-Energy attack alone


def test_energy_chain_line_appears_only_with_the_flag_on():
    # Drive the real dispatch (`_ko_for_prizes_lines`): the tutored-attach composite is a line WITH the flag
    # on, and NOTHING with it off (the branch is gated, and the item is not an energy-tutor so the fallback
    # `_supporter_ko_candidate` produces nothing either).
    obs, sel, option = _energy_chain_obs(hand=[_ITEM_ID, _ETUTOR_ID])
    board = _chain_board()

    on = _prime(_energy_chain_pilot(), obs)
    lines_on = on._ko_for_prizes_lines(obs, sel, board, sel["option"], None)
    assert any("item tutor" in ln.rationale for ln in lines_on)

    off = _prime(_energy_chain_pilot(), obs)
    off.enabler_item_composer = False
    assert off._ko_for_prizes_lines(obs, sel, board, sel["option"], None) == []


# ══════════════════════════════ BUILD 1 — Rare Candy (Basic→Stage-2 skip) ══════════════════════════════
#
# Rare Candy (id 1079) is NOT a tutor: the Stage-2 must ALREADY be in hand. Legal line: play Rare Candy →
# choose an in-play Basic (not appearThisTurn, not turn ≤ 1) → put an in-hand Stage-2 whose chain roots at
# that Basic onto it, SKIPPING the Stage-1 → attach → KO. NONE of the 3 agent decks run Rare Candy today, so
# the branch is inert for them — forward-looking generality, exercised only here.

_RC_BASIC, _RC_MID, _RC_TOP, _RC_AID = 210, 211, 212, 9903


def _rare_candy_pilot():
    stats = DictCardStatProvider({
        _RC_BASIC: CardStat(cardId=_RC_BASIC, name="RcBase", hp=60),               # Basic (evolvesFrom None)
        _RC_MID: CardStat(cardId=_RC_MID, name="RcMid", hp=90, evolvesFrom="RcBase"),   # the skipped Stage-1
        _RC_TOP: CardStat(cardId=_RC_TOP, name="RcTop", hp=200, stage2=True,
                          evolvesFrom="RcMid", attacks=(_RC_AID,)),                 # the in-hand Stage-2
        _RARE_CANDY_ID: CardStat(cardId=_RARE_CANDY_ID, cardType=1),               # Rare Candy (Item)
    }, {_RC_AID: AttackStat(attackId=_RC_AID, damage=200, cost=1, damageMax=200)})  # 1-Energy 200-dmg KO
    fns = _CardFunctions({_RARE_CANDY_ID: []})                                     # Rare Candy: no tag today
    return _deck_pilot([_RARE_CANDY_ID, _RC_TOP, _RC_BASIC, _RC_MID], stats=stats, functions=fns,
                  enabler_item_composer=True)


def _rare_candy_call(pilot, *, turn=2, appear_this_turn=False, hand=(_RC_TOP,), extra=0):
    body = poke(_RC_BASIC, energy=1, hp=60)
    if appear_this_turn:
        body["appearThisTurn"] = True
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=body, opp_active=poke(320, hp=190), turn=turn,
                                    hand=[_RARE_CANDY_ID]))
    board = Board(turn=turn, hand_ids=frozenset(hand), basic_energy_in_deck=True,
                  no_supporter_in_hand=True)
    _prime(pilot, obs)          # the line now prices by the Attach Budget, which lives on the
                                # StateModel — without this it measures a fail-closed zero (ADR-0075)
    return pilot._rare_candy_ko_candidate(obs, obs["select"], board, obs["select"]["option"][0],
                                          {"id": 320, "hp": 190}, {}, True)


def test_is_rare_candy_matches_by_id():
    pilot = _rare_candy_pilot()
    obs = make_select([opt(PLAY, index=0)], current=state(hand=[_RARE_CANDY_ID]))
    assert pilot._is_rare_candy(obs, obs["select"], obs["select"]["option"][0]) is True
    other = make_select([opt(PLAY, index=0)], current=state(hand=[999]))
    assert pilot._is_rare_candy(other, other["select"], other["select"]["option"][0]) is False


def test_stage2_roots_at_verifies_the_two_hop_chain():
    pilot = _rare_candy_pilot()
    top = pilot.stats.get(_RC_TOP)
    assert pilot._stage2_roots_at(top, "RcBase") is True               # RcTop←RcMid←RcBase
    assert pilot._stage2_roots_at(top, "Nope") is False                # wrong Basic


def test_rare_candy_composes_a_ko():
    got = _rare_candy_call(_rare_candy_pilot())
    assert got is not None and got[0] == 1                             # a 1-prize KO via the Stage-2 skip


def test_rare_candy_refused_on_turn_one():
    assert _rare_candy_call(_rare_candy_pilot(), turn=1) is None       # illegal on your first turn


def test_rare_candy_refused_on_an_appear_this_turn_basic():
    assert _rare_candy_call(_rare_candy_pilot(), appear_this_turn=True) is None


def test_rare_candy_refused_when_the_stage2_is_not_in_hand():
    assert _rare_candy_call(_rare_candy_pilot(), hand=()) is None      # Stage-2 not in hand → no line


def test_rare_candy_line_appears_only_with_the_flag_on():
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(_RC_BASIC, energy=1, hp=60),
                                    opp_active=poke(320, hp=190), turn=2, hand=[_RARE_CANDY_ID]))
    board = Board(turn=2, hand_ids=frozenset({_RC_TOP}), basic_energy_in_deck=True,
                  no_supporter_in_hand=True)
    on = _prime(_rare_candy_pilot(), obs)     # the Budget lives on the StateModel (ADR-0075)
    lines_on = on._ko_for_prizes_lines(obs, obs["select"], board, obs["select"]["option"], None)
    assert any("rare candy" in ln.rationale for ln in lines_on)

    off = _prime(_rare_candy_pilot(), obs)
    off.enabler_item_composer = False
    assert off._ko_for_prizes_lines(obs, obs["select"], board, obs["select"]["option"], None) == []


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
