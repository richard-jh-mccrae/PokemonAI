"""General Strategy — the deck-agnostic seed hypotheses (see docs/general-strategy.md)."""
import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import ATTACH, HAND, MAIN, PLAY, attack_opt, card_opt, make_select, opt, poke, state


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-GEN-0001")
def test_dig_before_commit_prefers_search_in_setup_and_needs_the_tag_table():
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], current=state(hand=[111, 222]))
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
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], current=state(hand=[800, 900]))

    liability, wincon = pilot.explain(obs).options
    assert "dont-bench-multiprize" in _fired(liability)       # 800: ex, not the win-con -> penalized
    assert "dont-bench-multiprize" not in _fired(wincon)      # 900: Mega ex but the win-con -> exempt


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


@pytest.mark.req("REQ-GEN-0006")
def test_build_before_attack_penalizes_a_nonlethal_attack_in_setup():
    stats = DictCardStatProvider({900: CardStat(900, hp=200)})
    ATK = 11
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, attacks={ATK: 50})
    # SETUP (no win-con ready): a non-lethal attack (50 vs 200 HP) -> develop instead.
    nonlethal = make_select([attack_opt(ATK)], context=MAIN,
                            current=state(active=poke(700), opp_active=poke(900, hp=200)))
    assert "build-before-attack" in _fired(pilot.explain(nonlethal).options[0])
    # a lethal attack is exempt — take the knockout.
    lethal = make_select([attack_opt(ATK)], context=MAIN,
                         current=state(active=poke(700), opp_active=poke(900, hp=40)))
    assert "build-before-attack" not in _fired(pilot.explain(lethal).options[0])
