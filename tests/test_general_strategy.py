"""General Strategy — the deck-agnostic seed hypotheses (see docs/general-strategy.md)."""
import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import (
    ACTIVE, ATTACH, ATTACH_FROM, BENCH, DAMAGE, HAND, MAIN, MULLIGAN, NO, PLAY, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-GEN-0001")
def test_dig_before_commit_prefers_search_in_setup_and_needs_the_tag_table():
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[111, 222]))
    # opt1 (card 222) is a search card; the General Strategy lifts it during SETUP.
    with_tags = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                      functions=CardFunctions({222: ["search"]}))
    assert with_tags.decide(obs) == [1]
    assert "dig-before-commit" in _fired(with_tags.explain(obs).options[1])

    # Counterfactual: without card_functions.json there are no tags, so it can't fire -> baseline.
    no_tags = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert no_tags.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0002")
def test_dont_bench_multiprize_penalizes_a_nonwincon_ex_but_exempts_the_wincon():
    stats = DictCardStatProvider({800: CardStat(800, ex=True), 900: CardStat(900, megaEx=True)})
    # 900 is the deck's win-condition; 800 is a bare 2-prize liability.
    pilot = Pilot(Strategy(roles={900: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[800, 900]))

    liability, wincon = pilot.explain(obs).options
    assert "dont-bench-multiprize" in _fired(liability)       # 800: ex, not the win-con -> penalized
    assert "dont-bench-multiprize" not in _fired(wincon)      # 900: Mega ex but the win-con -> exempt


@pytest.mark.req("REQ-GEN-0002")
def test_dont_bench_multiprize_also_penalizes_evolving_into_a_nonwincon_ex():
    # adversarial-review fix: evolving a Basic into a non-wincon ex also puts a multi-prizer into
    # play, so the gate must cover EVOLVE (option_type 9), not only PLAY.
    _EVOLVE = 9
    stats = DictCardStatProvider({888: CardStat(888, ex=True), 900: CardStat(900, megaEx=True)})
    pilot = Pilot(Strategy(roles={900: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    # an EVOLVE whose result (the card in hand) is a loose 2-prize ex (888), not the win-condition.
    obs = make_select([opt(_EVOLVE, area=HAND, index=0)], current=state(hand=[888]))
    assert "dont-bench-multiprize" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0003")
def test_keep_a_bench_fires_only_when_the_bench_is_empty():
    stats = DictCardStatProvider({700: CardStat(700, hp=70)})   # a Pokémon (hp > 0)
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    play_basic = opt(PLAY, area=HAND, index=0)

    empty = make_select([play_basic], current=state(active=poke(999), hand=[700]))
    assert "keep-a-bench" in _fired(pilot.explain(empty).options[0])

    has_bench = make_select([play_basic], current=state(active=poke(999), bench=[poke(701)], hand=[700]))
    assert "keep-a-bench" not in _fired(pilot.explain(has_bench).options[0])


@pytest.mark.req("REQ-GEN-0004")
def test_attach_energy_last_defers_attachments_during_setup():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    obs = make_select([opt(ATTACH)], current=state())   # state() -> SETUP
    assert "attach-energy-last" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0005")
def test_pre_position_attacker_develops_the_bench_during_race():
    stats = DictCardStatProvider({700: CardStat(700, hp=70)})
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # active is the payoff with 1 energy -> Plan.RACE; benching a Pokémon pre-positions the next attacker.
    obs = make_select([opt(PLAY, area=HAND, index=0)],
                      current=state(active=poke(700, energy=1), bench=[poke(800)], hand=[700]))
    assert "pre-position-attacker" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0011")
def test_dont_feed_the_doomed_attaches_to_the_bench_when_the_active_will_die():
    WATER, LIGHTNING = 3, 4
    stats = DictCardStatProvider({
        700: CardStat(700, energyType=WATER, weakness=LIGHTNING, hp=70),   # my Active (Weak to L)
        900: CardStat(900, energyType=LIGHTNING, maxDamage=120),           # opp Active: 120, Lightning
        800: CardStat(800, energyType=WATER, hp=110),                      # my benched successor
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # ATTACH_FROM (pick the Pokémon to attach to): opt0 = my Active (30 HP left, doomed — 120 x2
    # Weakness >> 30), opt1 = my Bench. Don't sink the Energy into the dying Active.
    obs = make_select([card_opt(ACTIVE, 0), card_opt(BENCH, 0)], context=ATTACH_FROM,
                      current=state(active=poke(700, hp=30), bench=[poke(800, hp=110)],
                                    opp_active=poke(900, hp=160)))
    assert pilot.decide(obs) == [1]   # attach to the Bench successor, not the doomed Active
    assert "dont-feed-the-doomed" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0010")
def test_use_acceleration_prioritizes_an_energy_accel_card():
    # A card tagged `energy_accel` multiplies your one manual attach — tempo-positive for any deck.
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  functions=CardFunctions({222: ["energy_accel"]}))
    # opt0 -> card 111 (untagged), opt1 -> card 222 (energy_accel): use-acceleration lifts opt1.
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[111, 222]))
    assert pilot.decide(obs) == [1]
    assert "use-acceleration" in _fired(pilot.explain(obs).options[1])


@pytest.mark.req("REQ-GEN-0008")
def test_keep_a_startable_hand_declines_to_mulligan_a_startable_opener():
    OPENER = 666
    mull = make_select([opt(YES), opt(NO)], context=MULLIGAN, current=state(hand=[OPENER]))

    # an `opener` Function Tag in hand -> keep (No), don't redraw and hand the opponent a card.
    by_tag = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                   functions=CardFunctions({OPENER: ["opener"]}))
    assert by_tag.decide(mull) == [1]
    assert "keep-a-startable-hand" in _fired(by_tag.explain(mull).options[0])

    # the `starter` Role alone (no card_functions.json) -> still keeps: survives the A/B toggle.
    by_role = Pilot(Strategy(roles={OPENER: ["starter"]}), deck=[1] * 60,
                    general_strategy=GENERAL_STRATEGY)
    assert by_role.decide(mull) == [1]

    # neither signal -> ungoverned, defaults to the redraw blunder.
    baseline = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert baseline.decide(mull) == [0]


@pytest.mark.req("REQ-GEN-0007")
def test_power_up_attacker_attaches_energy_rather_than_passing():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    # SETUP, options = [attach an Energy, a do-nothing play]. Attaching must win: power-up-attacker
    # (+15) overcomes attach-energy-last (-5) so a plain attachment nets positive (the blunder fix).
    obs = make_select([opt(ATTACH), opt(PLAY)], current=state())   # state() -> SETUP
    assert pilot.decide(obs) == [0]
    assert "power-up-attacker" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0012")
def test_snipe_the_threat_prefers_the_benched_attacker_carrying_energy():
    # A Damage/snipe select over the opponent's Bench: a bare Pokémon (opt0) vs one already
    # carrying Energy (opt1, closest to attacking). snipe-the-threat lifts the energized target.
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(800, energy=0), poke(900, energy=1)]))
    assert pilot.decide(obs) == [1]
    assert "snipe-the-threat" in _fired(pilot.explain(obs).options[1])
    assert "snipe-the-threat" not in _fired(pilot.explain(obs).options[0])

    # All-bare Bench (no energized threat anywhere): the rule fires on nothing -> baseline holds.
    no_threat = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                            context=DAMAGE,
                            current=state(active=poke(700),
                                          opp_bench=[poke(800, energy=0), poke(900, energy=0)]))
    assert "snipe-the-threat" not in _fired(pilot.explain(no_threat).options[1])


# NOTE: `build-before-attack` was removed — `_finish_turn_last` ("attack last") now sequences
# development ahead of the turn-ending attack structurally, so a blanket chip penalty is redundant
# (and was suppressing a useful chip below End when no development was available). See
# tests/test_search_discipline.py::test_a_weak_chip_is_taken_when_no_development_is_available.
