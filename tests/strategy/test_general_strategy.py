"""General Strategy — the deck-agnostic seed hypotheses (see docs/general-strategy.md)."""
import pytest

from common.cards import CardFunctions
from common.strategy.baseline import SNIPE_HYPOTHESES
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import (
    ACTIVE, ATTACH, ATTACH_FROM, BENCH, DAMAGE, HAND, MAIN, MULLIGAN, NO, PLAY, SETUP_ACTIVE, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-GEN-0063")
def test_global_retirement_keeps_only_c10_guards_and_deck_local_rungs():
    """Issue #459 globally keeps only C10 guards while deck-local third-deck rungs remain."""
    # Do not import `agents.<deck>.strategy` directly: kaggle_environments exposes a conflicting
    # top-level `agents` module in CI. The shipped builder is also the runtime wiring under test.
    from train.tune import _build_pilot

    lucario = _build_pilot("mega_lucario")[0].strategy
    dragapult = _build_pilot("dragapult_ex")[0].strategy

    assert {hypothesis.id for hypothesis in GENERAL_STRATEGY.hypotheses} == {
        "dont-search-an-empty-deck",
        "keep-a-startable-hand",
        "honor-preferred-start",
    }
    assert lucario.hypotheses
    assert dragapult.hypotheses


# REQ-GEN-0001's `dig-before-commit` test went with the rung (Issue #386). Successors:
# `tests/cards/test_card_functions_oracle.py` and `tests/strategy/test_fetch_doctrine.py`.

# REQ-GEN-0002's `dont-bench-multiprize` tests went with the rung (ADR-0086). Its job is now the
# Deploy Marginal's EXPOSURE leg — `test_deploy_value.py`.


@pytest.mark.req("REQ-GEN-0003")
def test_the_empty_bench_guard_is_the_filter_and_no_longer_also_a_rung():
    """ONE guard per fact (ADR-0096). The FILTER runs after `_finish_turn_last`, so it wins outright
    and `keep-a-bench` guarded nothing — but the BEHAVIOUR must still hold."""
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, hp=70)})   # a Pokémon (hp > 0)
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    play_basic = opt(PLAY, area=HAND, index=0)

    assert not any(h.id == "keep-a-bench" for h in GENERAL_STRATEGY.hypotheses)

    END = 14                                 # OptionType.END — the turn-ender
    empty = make_select([opt(END), play_basic],
                        current=state(active=poke(999), hand=[700]), context=MAIN)
    assert pilot.decide(empty) == [1]        # the FILTER forces the body ahead of ending the turn




# REQ-GEN-0005's `pre-position-attacker` test went with the rung (ADR-0086). Keeping the next
# attacker coming is now the ASSIGNMENT leg, which a flat +25 could not express.


@pytest.mark.req("REQ-GEN-0011")
def test_dont_feed_the_doomed_attaches_to_the_bench_when_the_active_will_die():
    WATER, LIGHTNING = 3, 4
    # Both of my bodies need a real attack for the decider to price: a stat-blind body earns no build
    # on either side of the gate, and the pin would then pass on a coincidence rather than on the rule.
    stats = DictCardStatProvider({
        700: CardStat(700, synthetic=True, energyType=WATER, weakness=LIGHTNING, hp=70,    # my Active (Weak to L)
                      maxDamage=60, maxDamageCost=2, minAttackCost=1, attacks=(7001,)),
        900: CardStat(900, synthetic=True, energyType=LIGHTNING, maxDamage=120),           # opp Active: 120, Lightning
        800: CardStat(800, synthetic=True, energyType=WATER, hp=110,                       # my benched successor
                      maxDamage=60, maxDamageCost=2, minAttackCost=1, attacks=(8001,)),
    }, attacks={
        7001: AttackStat(7001, damage=60, cost=2, energyTypes=(WATER, WATER)),
        8001: AttackStat(8001, damage=60, cost=2, energyTypes=(WATER, WATER)),
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # ATTACH_FROM (pick Pokémon to attach to): opt0 = my Active (30 HP left, doomed — 120 x2
    # Weakness >> 30), opt1 = my Bench. Don't sink Energy into the dying Active.
    obs = make_select([card_opt(ACTIVE, 0), card_opt(BENCH, 0)], context=ATTACH_FROM,
                      current=state(active=poke(700, hp=30), bench=[poke(800, hp=110)],
                                    opp_active=poke(900, hp=160)))
    # `dont-feed-the-doomed` is DELETED (Issue #139, ADR-0069 §7): the SURVIVAL gate zeroes a doomed body's
    # forward build outright, so a dying Active simply earns nothing to bank.
    rows = {r["i"]: r for r in pilot.explain(obs).attach_working["eq"]}
    assert rows[0]["doomed"] is True and rows[0]["build"] == 0.0
    assert rows[1]["build"] > 0.0
    assert pilot.decide(obs) == [1]   # attach to Bench successor, not doomed Active




@pytest.mark.req("REQ-GEN-0008")
def test_keep_a_startable_hand_declines_to_mulligan_a_startable_opener():
    OPENER = 666
    mull = make_select([opt(YES), opt(NO)], context=MULLIGAN, current=state(hand=[OPENER]))

    # `opener` Function Tag in hand -> keep (No), don't redraw and hand opponent a card.
    by_tag = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                   functions=CardFunctions({OPENER: ["opener"]}))
    assert by_tag.decide(mull) == [1]
    assert "keep-a-startable-hand" in _fired(by_tag.explain(mull).options[0])

    # (The `starter` Role was retired here by ADR-0079: it was only declared on Basics, and a hand
    #  holding any Basic never reaches this prompt at all — `docs/rulebook.txt` L224.)

    # neither signal -> ungoverned, defaults to redraw blunder.
    baseline = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert baseline.decide(mull) == [0]






@pytest.mark.req("REQ-GEN-0062")
def test_honor_preferred_start_penalizes_the_coin_toss_option_that_contradicts_the_deck():
    # Folded from mega_starmie `prefer-going-second`: deck declares
    # params["preferred_start"] = "first" | "second"; general selector honors it.
    IS_FIRST = 41
    toss = make_select([opt(YES), opt(NO)], context=IS_FIRST, current=state())

    second = Pilot(Strategy(params={"preferred_start": "second"}), deck=[1] * 60,
                   general_strategy=GENERAL_STRATEGY)
    assert second.decide(toss) == [1]                                   # NO = go second
    assert "honor-preferred-start" in _fired(second.explain(toss).options[0])
    assert "honor-preferred-start" not in _fired(second.explain(toss).options[1])

    first = Pilot(Strategy(params={"preferred_start": "first"}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY)
    assert first.decide(toss) == [0]                                    # YES = go first
    assert "honor-preferred-start" in _fired(first.explain(toss).options[1])

    undeclared = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert not any("honor-preferred-start" in _fired(o) for o in undeclared.explain(toss).options)


@pytest.mark.req("REQ-GEN-0007")
def test_power_up_attacker_attaches_energy_rather_than_passing():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    # The attach wins on ORDERING, not score: an unendorsed do-nothing play sequences with the
    # turn-enders while the attach holds its own tier.
    obs = make_select([opt(ATTACH), opt(PLAY)], current=state())   # state() -> SETUP
    assert pilot.decide(obs) == [0]


# Three snipe TARGET rung tests were DELETED with their rungs (ADR-0085). The requirements survive
# in `test_snipe_relevance.py`'s `imminence` and `forward` legs.

@pytest.mark.req("REQ-GEN-0022")
def test_only_snipe_rules_fire_at_a_damage_select():
    # The no-double-count gate is whitelist-by-omission, so the whitelist is DERIVED from the snipe
    # cluster itself and a 5th snipe rule cannot silently drift it.
    allowed = {h.id for h in SNIPE_HYPOTHESES}
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
        900: CardStat(900, synthetic=True, name="Zubat", maxDamage=30),
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(333, hp=80), poke(900, energy=1, hp=60)]))
    for o in pilot.explain(obs).options:
        assert _fired(o) <= allowed


# `build-before-attack` was removed: `_finish_turn_last` sequences development ahead of the
# turn-ending attack structurally, so a blanket chip penalty suppressed useful chips for nothing.

# `doctrine_tool.py` and its five rungs are gone (Issue #386). A Tool that buys a survival turn is
# now `survival` on the composed end board (`deploy_value`, ADR-0086).
_WATER, _LIGHTNING, _FIRE = 3, 4, 2
_HP_TOOL, _WINCON = 1159, 900


def _hp_tool_pilot(*, hp_bonus=100, opp_type=_FIRE, opp_dmg=400, wincon_role=True):
    """Active win-condition (330 HP, Weak to Lightning) vs an attacker dealing `opp_dmg`, with a
    +`hp_bonus` Tool in hand. `opp_type` == the wincon's weakness doubles the incoming hit."""
    stats = DictCardStatProvider({
        _WINCON: CardStat(_WINCON, synthetic=True, hp=330, energyType=_WATER, weakness=_LIGHTNING),
        _HP_TOOL: CardStat(_HP_TOOL, synthetic=True, hp=0, hpBonus=hp_bonus),
        800: CardStat(800, synthetic=True, energyType=opp_type, maxDamage=opp_dmg),
    })
    roles = {_WINCON: ["win_condition"]} if wincon_role else {}
    return Pilot(Strategy(roles=roles), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({_HP_TOOL: ["tool"]}))


def _attach_hp_tool():
    # ATTACH +HP Tool (hand idx 0) onto my full-HP (330) Active win-condition, facing card 800.
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(_WINCON, hp=330), opp_active=poke(800, hp=200),
                                     hand=[_HP_TOOL]))


# REQ-GEN-0024's two `deploy-hp-tool` silence tests went with the rung (Issue #386). The DECISION it
# made — "this Tool would not save the body, so don't spend it" — has NO successor today.
