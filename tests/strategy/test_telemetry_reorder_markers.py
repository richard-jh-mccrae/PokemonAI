"""Decision Telemetry reorder markers (ADR-0019): the @T record must SAY when the chosen option
did not come from a plain argmax over the emitted scores.

Three decide()-only selection steps make ``chosen`` diverge from the highest-``score`` option, so a
blunder-buster reading the live trace would otherwise see a "top-scored option not chosen" record
with no explanation and misread it as a scoring bug:

  * attack-last sequencing (``_finish_turn_last``): a turn-ending attack is held behind free
    development, so a lower-score develop is chosen — the held attack is marked ``deferred``.
  * the needy-Line attach tie-break (``attach_to_needy_line``): among EQUAL-score attaches, feed the
    win-condition Line base first.
  * the greedy grab (``_greedy_grab``): a multi-pick set chosen by dynamic gap-scoring, not top-N
    static score.

Behaviour is verified through the wire contract ``telemetry.to_record`` (what the tuner/inspector and
/blunder-buster actually read) — the markers are sparse (absent when the mechanism didn't fire), so an
untouched record stays byte-identical to the pre-marker era.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Decision, OptionTrace, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.telemetry import to_record
from pilot_helpers import DECK, PLAY, TO_HAND, attack_opt, card_opt, make_select, poke, state

ATTACKER = 900   # my Active: can attack, but not for a KO/win this turn
OPPA = 678       # opponent's Active (high HP -> the attack doesn't KO -> no lethal/planner commit)
BASIC = 800      # a basic Pokémon on the Bench (so the Bench is non-empty)
BALL = 801       # a `search` Item in hand -> the free tier-0 action the attack is held behind
ATK = 20         # attack id: cost 1, 100 dmg (chip, non-KO)


def _trace(index, score, **kw):
    return OptionTrace(index=index, score=score, plan=Plan.SETUP, card_id=kw.pop("card_id", None),
                       fired=[], **kw)


def _pilot(**kw):
    stats = DictCardStatProvider({
        ATTACKER: CardStat(ATTACKER, synthetic=True, name="attacker", hp=200, energyType=3, minAttackCost=1,
                           minCostDamage=100, maxDamage=100, attacks=(ATK,)),
        OPPA: CardStat(OPPA, synthetic=True, name="opp active", hp=200, energyType=7),
        BASIC: CardStat(BASIC, synthetic=True, name="benchie", hp=60, energyType=3),
        BALL: CardStat(BALL, synthetic=True, name="search item", hp=0),
    }, attacks={ATK: AttackStat(ATK, damage=100, cost=1)})
    return Pilot(Strategy(roles={ATTACKER: ["primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({BALL: ["search"]}), **kw)


@pytest.mark.req("REQ-SUB-0006")
def test_held_back_attack_is_marked_deferred_in_the_record():
    """Tracer: an attack-last deferral (``OptionTrace.deferred``) must ride into the @T opts so the
    reader sees WHY the higher-score attack lost to a develop. Sparse: the develop opt carries no key."""
    attack = _trace(0, 50.0, tactical=50.0, deferred=True)   # higher score, but held behind dev
    develop = _trace(1, 5.0, card_id=800)                    # chosen: free development goes first
    rec = to_record(Decision(chosen=[1], options=[attack, develop]))
    assert rec["opts"][0].get("deferred") is True            # the held attack is flagged
    assert "deferred" not in rec["opts"][1]                  # sparse: not on the non-deferred opt


@pytest.mark.req("REQ-SUB-0006")
def test_needy_line_attach_tiebreak_is_marked_in_the_record():
    """The ``attach_to_needy_line`` tie-break (feed the win-condition Line base among EQUAL-score
    attaches) rides as ``needy`` so an equal-score pick doesn't look arbitrary. Sparse."""
    needy = _trace(0, 10.0, card_id=800, attach_to_needy_line=True)   # chosen among equal scores
    other = _trace(1, 10.0, card_id=801)                             # same score, no Line need
    rec = to_record(Decision(chosen=[0], options=[needy, other]))
    assert rec["opts"][0].get("needy") is True               # the needy-Line attach is flagged
    assert "needy" not in rec["opts"][1]                     # sparse: not on the other option


@pytest.mark.req("REQ-SUB-0006")
def test_reordered_decision_carries_a_top_level_flag():
    """When ``_finish_turn_last`` resequenced the MAIN menu, ``chosen`` is NOT argmax(score); the
    record says so up front with ``reordered`` so the reader doesn't expect the top score to win."""
    a = _trace(0, 50.0, tactical=50.0, deferred=True)
    b = _trace(1, 5.0, card_id=800)
    assert to_record(Decision(chosen=[1], options=[a, b], reordered=True))["reordered"] is True
    assert "reordered" not in to_record(Decision(chosen=[0], options=[a, b]))   # sparse: default off


@pytest.mark.req("REQ-SUB-0006")
def test_greedy_grab_decision_carries_a_top_level_flag():
    """A multi-pick ``_greedy_grab`` set is chosen by dynamic gap-scoring, so the chosen SET isn't the
    top-N static scores; ``grabbed`` tells the reader not to reconcile it against static order."""
    a = _trace(0, 30.0)
    b = _trace(1, 20.0)
    assert to_record(Decision(chosen=[0, 1], options=[a, b], grabbed=True))["grabbed"] is True
    assert "grabbed" not in to_record(Decision(chosen=[0], options=[a, b]))   # sparse: default off


@pytest.mark.req("REQ-SUB-0006")
def test_real_attack_last_decision_emits_deferred_and_reordered():
    """End-to-end plumbing: a real ``Pilot.explain`` on an attack-last board (chip attack + a free
    Item) resequences the menu, so the emitted record chooses the Item, flags the held attack
    ``deferred``, AND carries the top-level ``reordered`` — the full 'why' a trace reader needs.

    The free action is a `search` Item (`dig-before-commit` +20), not a bare Basic develop. Since
    ADR-0086 a develop carries no flat endorsement — it is priced by the Deploy Marginal — and on this
    board a roleless second body genuinely fills no need, so it scores 0 and nothing resequences. That
    is the equation answering correctly; it just leaves nothing for a TELEMETRY test to observe."""
    board = state(active=poke(ATTACKER, energy=1, hp=200, max_hp=200),
                  bench=[poke(BASIC, hp=60, max_hp=60)],   # non-empty bench: the chip attack out-scores
                  hand=[BALL],                             # one free tier-0 action, so the resequence flips
                  opp_active=poke(OPPA, hp=200, max_hp=200), prizes=2, opp_prizes=2)
    obs = make_select([attack_opt(ATK), {"type": PLAY, "index": 0}], current=board)
    rec = to_record(_pilot(deploy_value=True).explain(obs))
    assert rec["chosen"] == [1]                               # the free develop goes first (attack-last)
    assert rec["opts"][0].get("deferred") is True             # the held chip attack is flagged
    assert rec.get("reordered") is True                       # top-level: chosen != argmax(score)


@pytest.mark.req("REQ-SUB-0006")
def test_real_greedy_grab_decision_emits_grabbed():
    """End-to-end: a real multi-pick grab (``_greedy_grab`` at a TO_HAND search) carries the top-level
    ``grabbed`` so a reader knows the chosen SET came from dynamic gap-scoring, not top-N static score."""
    board = state(active=poke(ATTACKER, energy=0, hp=200, max_hp=200),
                  opp_active=poke(OPPA, hp=200, max_hp=200), prizes=2, opp_prizes=2)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND, min_count=0,
                      max_count=2, deck=[{"id": BASIC}, {"id": BASIC}], current=board)
    assert to_record(_pilot().explain(obs)).get("grabbed") is True
