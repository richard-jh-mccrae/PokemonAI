"""Search / fetch discipline + the RACE weak-chip rule (this round's blunder corrections).

Covers the infrastructure that lets the Pilot *see* a search decision (resolving a DECK option from
the select's revealed `deck` list and a DISCARD option from the player's discard pile), the four new
deck-agnostic Hypotheses it unblocks (`fetch-the-wincon`, `fetch-energy-when-starved`,
`prefer-bench-fill-first`, `dont-chip-with-a-doomed-active`), and the guard that the board-commit
intent rules do NOT leak onto a fetch sub-selection. See docs/tuning/methodology.md, ADR-0008.
"""
import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import (
    ATTACH, DECK, DISCARD, HAND, MAIN, PLAY, TO_HAND,
    attack_opt, card_opt, make_select, opt, poke, state,
)

WATER, FIRE, LIGHTNING = 3, 2, 4
STARYU, MEGA, CINDERACE, BASIC_W, IGNITION = 1030, 1031, 666, 3, 17
POFFIN, HILDA = 1086, 1225


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- infrastructure: a search option must resolve to its card id --------------------------------
@pytest.mark.req("REQ-PILOT-0023")
def test_search_options_resolve_their_card_id_from_deck_and_discard():
    """A search/ToHand option is a CARD pointing into a hidden zone: a DECK candidate's id lives in
    the select's revealed `deck` list, a DISCARD candidate's in the player's discard pile. Without
    this resolution every fetch carries no roles/tags/stat and no search Hypothesis can fire."""
    p = Pilot(Strategy(), deck=[])
    sel_deck = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                           deck=[{"id": STARYU}, {"id": MEGA}])["select"]
    assert p._option_card_id({}, sel_deck, card_opt(DECK, 1)) == MEGA
    assert p._option_card_id({}, sel_deck, card_opt(DECK, 9)) is None      # out of range -> None

    obs = make_select([], context=TO_HAND, current=state(discard=[CINDERACE, BASIC_W]))
    sel = obs["select"]
    assert p._option_card_id(obs, sel, card_opt(DISCARD, 0)) == CINDERACE
    assert p._option_card_id(obs, sel, card_opt(DISCARD, 1)) == BASIC_W


# --- fetch-the-wincon ----------------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_prefers_the_payoff_at_a_search():
    stats = DictCardStatProvider({STARYU: CardStat(STARYU, hp=70),
                                  MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # active carries Energy -> not energy-starved, so only fetch-the-wincon is in play here.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": STARYU}, {"id": MEGA}],
                      current=state(active=poke(CINDERACE, energy=1)))
    assert pilot.decide(obs) == [1]                                  # pull the Mega, not the Staryu
    assert "fetch-the-wincon" in _fired(pilot.explain(obs).options[1])
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_yields_to_energy_when_starved():
    # adversarial-review fix: a wincon you cannot power does nothing — when starved, energy wins.
    stats = DictCardStatProvider({MEGA: CardStat(MEGA, megaEx=True, hp=330),
                                  BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}),
                  deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": MEGA}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[]))     # 0 energy, none in hand
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])    # stands down
    assert pilot.decide(obs) == [1]                                           # take the Energy


@pytest.mark.req("REQ-GEN-0013")
def test_fetch_the_wincon_stands_down_when_the_payoff_is_already_in_play():
    # adversarial-review fix: don't pull a dead second copy when the win-condition is already in play.
    stats = DictCardStatProvider({MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    pilot = Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}),
                  deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": MEGA}],
                      current=state(active=poke(MEGA, energy=2)))             # Mega already Active
    assert pilot._board(obs).wincon_in_play
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])


# --- fetch-energy-when-starved -------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_takes_a_reusable_basic():
    stats = DictCardStatProvider({700: CardStat(700, hp=70), BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # starved: Active has 0 Energy and none in hand -> take the Energy over the Pokémon.
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": 700}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[]))
    assert pilot.decide(obs) == [1]
    assert "fetch-energy-when-starved" in _fired(pilot.explain(obs).options[1])


@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_skips_a_discard_energy_for_a_reusable_one():
    stats = DictCardStatProvider({IGNITION: CardStat(IGNITION, energyType=0),       # colourless special
                                  BASIC_W: CardStat(BASIC_W, energyType=WATER)})     # reusable Basic
    funcs = CardFunctions({IGNITION: ["discard_eot"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": IGNITION}, {"id": BASIC_W}],
                      current=state(active=poke(900, energy=0)))
    assert pilot.decide(obs) == [1]                                  # the reusable Basic, not Ignition
    assert "fetch-energy-when-starved" not in _fired(pilot.explain(obs).options[0])   # Ignition: skipped
    assert "fetch-energy-when-starved" in _fired(pilot.explain(obs).options[1])       # Basic: boosted


@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_is_off_when_energy_is_already_in_hand():
    stats = DictCardStatProvider({BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # a reusable Energy already sits in hand -> not starved -> the rule does not fire.
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[BASIC_W]))
    assert "fetch-energy-when-starved" not in _fired(pilot.explain(obs).options[0])


# --- prefer-bench-fill-first ---------------------------------------------------------------------
@pytest.mark.req("REQ-GEN-0015")
def test_prefer_bench_fill_first_sequences_the_thinner_ahead_of_a_tutor():
    funcs = CardFunctions({POFFIN: ["search", "bench_fill"], HILDA: ["search"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    # SETUP, both are search plays (dig-before-commit fires on each); the bench-filler is sequenced first.
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[HILDA, POFFIN]))
    assert pilot.decide(obs) == [1]                                  # Buddy-Buddy Poffin first
    assert "prefer-bench-fill-first" in _fired(pilot.explain(obs).options[1])
    assert "prefer-bench-fill-first" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0015")
def test_prefer_bench_fill_first_stands_down_on_a_full_bench():
    # adversarial-review fix: a bench-filler can place nothing on a full Bench -> don't promote it.
    funcs = CardFunctions({POFFIN: ["search", "bench_fill"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    full = [poke(701), poke(702), poke(703), poke(704), poke(705)]            # 5 = a full Bench
    obs = make_select([opt(PLAY, area=HAND, index=0)], current=state(bench=full, hand=[POFFIN]))
    assert pilot._board(obs).my_bench == 5
    assert "prefer-bench-fill-first" not in _fired(pilot.explain(obs).options[0])


# --- dont-chip-with-a-doomed-active (the RACE analog of build-before-attack) ----------------------
def _doomed_race_pilot():
    stats = DictCardStatProvider({
        700: CardStat(700, energyType=WATER, hp=30),                        # my doomed Active (low HP)
        900: CardStat(900, energyType=LIGHTNING, maxDamage=120, hp=200),    # opp can KO me (120 >= 30)
    })
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])  # active=payoff -> RACE
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})


@pytest.mark.req("REQ-GEN-0016")
def test_dont_chip_with_a_doomed_active_prefers_development_in_race():
    pilot = _doomed_race_pilot()
    obs = make_select([attack_opt(11), opt(ATTACH)], context=MAIN,
                      current=state(active=poke(700, energy=1, hp=30), opp_active=poke(900, hp=200)))
    assert pilot._board(obs).active_doomed                           # premise: my Active dies next turn
    assert "dont-chip-with-a-doomed-active" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                                  # develop (attach), don't waste a weak chip


@pytest.mark.req("REQ-GEN-0016")
def test_dont_chip_is_off_for_a_lethal_attack_and_takes_the_ko():
    pilot = _doomed_race_pilot()
    # still doomed (120 >= 30) but the chip is now LETHAL (50 >= 40) -> is_ko -> rule off, take the KO.
    obs = make_select([attack_opt(11), opt(ATTACH)], context=MAIN,
                      current=state(active=poke(700, energy=1, hp=30), opp_active=poke(900, hp=40)))
    assert pilot._board(obs).active_doomed
    assert "dont-chip-with-a-doomed-active" not in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [0]                                  # the knockout dominates


@pytest.mark.req("REQ-GEN-0016")
def test_dont_chip_is_off_when_the_active_is_not_doomed():
    stats = DictCardStatProvider({
        700: CardStat(700, energyType=WATER, hp=80),
        901: CardStat(901, energyType=LIGHTNING, maxDamage=10, hp=200),     # can't KO me (10 < 80)
    })
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11)], context=MAIN,
                      current=state(active=poke(700, energy=1, hp=80), opp_active=poke(901, hp=200)))
    assert not pilot._board(obs).active_doomed
    assert "dont-chip-with-a-doomed-active" not in _fired(pilot.explain(obs).options[0])


# --- the leak guard: board-commit intent rules must not fire on a fetch sub-selection ------------
@pytest.mark.req("REQ-GEN-0017")
def test_board_intent_rules_do_not_leak_onto_search_options():
    # The fetched card's `search` / `energy_accel` tags now resolve at a ToHand search, but the
    # board-commit intent rules (which govern plays, not which card a search pulls) must stay silent.
    funcs = CardFunctions({222: ["search", "energy_accel"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": 222}],
                      current=state(active=poke(700, energy=1)))
    fired = _fired(pilot.explain(obs).options[0])
    assert "dig-before-commit" not in fired
    assert "use-acceleration" not in fired
