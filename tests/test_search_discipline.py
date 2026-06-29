"""Search / fetch discipline + the RACE weak-chip rule (this round's blunder corrections).

Covers the infrastructure that lets the Pilot *see* a search decision (resolving a DECK option from
the select's revealed `deck` list and a DISCARD option from the player's discard pile), the deck-
agnostic search/development Hypotheses it unblocks (`fetch-the-wincon`, `fetch-energy-when-starved`,
`prefer-bench-fill-first`, `snipe-the-weakest`, the promote/retreat doctrine), "attack last"
sequencing, and the guard that the board-commit intent rules do NOT leak onto a fetch sub-selection.
See docs/tuning/methodology.md, ADR-0008.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Ready, Strategy
from pilot_helpers import (
    ATTACH, BENCH, DAMAGE, DECK, DISCARD, HAND, MAIN, PLAY, TO_HAND,
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


# --- chip discipline is now structural: attack-last sequences dev first; with no dev, take the chip --
# (the old `build-before-attack` / `dont-chip-with-a-doomed-active` chip-penalty rules were removed —
#  they suppressed a useful chip below End when no development was available.)
@pytest.mark.req("REQ-GEN-0016")
def test_development_still_beats_a_weak_chip_via_attack_last():
    stats = DictCardStatProvider({700: CardStat(700, energyType=WATER, hp=30),
                                  900: CardStat(900, energyType=LIGHTNING, maxDamage=120, hp=200)})
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])  # active=payoff -> RACE
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(ATTACH)], context=MAIN,
                      current=state(active=poke(700, energy=1, hp=30), opp_active=poke(900, hp=200)))
    assert pilot.decide(obs) == [1]            # attack-last: develop (attach) ahead of the weak chip
    assert pilot.explain(obs).options[0].deferred


@pytest.mark.req("REQ-GEN-0016")
def test_a_weak_chip_is_taken_when_no_development_is_available():
    # the removal's point: with nothing better to do, chip — don't end the turn doing nothing.
    stats = DictCardStatProvider({700: CardStat(700, energyType=WATER, hp=30),
                                  900: CardStat(900, energyType=LIGHTNING, maxDamage=120, hp=200)})
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(14)], context=MAIN,      # only a weak chip and End
                      current=state(active=poke(700, energy=1, hp=30), opp_active=poke(900, hp=200)))
    assert pilot.decide(obs) == [0]            # take the chip (19.9-ish), not End


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


# --- attack-last: an attack ends the turn, so beneficial development is sequenced ahead of it ----
@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_sequences_development_before_the_turn_ending_attack():
    """A KO attack co-exists with a beneficial development (a +30 play). Attacking ends the turn,
    but the KO survives the play — so develop first and keep the attack for last (same turn)."""
    stats = DictCardStatProvider({700: CardStat(700, energyType=WATER), 900: CardStat(900, hp=40)})
    dev = Hypothesis(id="dev", rationale="", when=lambda c: c.option_type == PLAY, weight=30)
    pilot = Pilot(Strategy(hypotheses=[dev]), deck=[1] * 60, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(PLAY)], context=MAIN,
                      current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    d = pilot.explain(obs)
    assert d.options[0].tactical >= KO_SCORE          # the attack is a KO (50 >= 40) …
    assert pilot.decide(obs) == [1]                   # … but the +30 development goes first
    assert d.options[0].deferred                      # the KO is held back, never dropped


@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_takes_the_attack_once_no_beneficial_development_remains():
    stats = DictCardStatProvider({700: CardStat(700, energyType=WATER), 900: CardStat(900, hp=40)})
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(14)], context=MAIN,    # only the KO and End (score 0)
                      current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    assert pilot.decide(obs) == [0]                   # nothing beneficial pending -> take the KO


@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_protects_a_knockout_from_an_active_evolve_but_not_otherwise():
    """Evolving the Active replaces its attack, so it must NOT be sequenced ahead of an available
    knockout (that would forfeit the KO) — but with no KO on the menu it is normal development."""
    EVOLVE, ACTIVE_AREA = 9, 4
    stats = DictCardStatProvider({700: CardStat(700, energyType=WATER), 900: CardStat(900, hp=40),
                                  901: CardStat(901, hp=200)})
    ev = Hypothesis(id="ev", rationale="", when=lambda c: c.option_type == EVOLVE, weight=40)
    pilot = Pilot(Strategy(hypotheses=[ev]), deck=[1] * 60, stats=stats, attacks={11: 50})
    ko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                     current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    assert pilot.decide(ko) == [0]                    # KO present -> don't evolve the Active away
    noko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                       current=state(active=poke(700, energy=1), opp_active=poke(901, hp=200)))
    assert pilot.decide(noko) == [1]                  # no KO to forfeit -> evolve the Active first


# --- snipe-the-weakest: pick the lowest-HP bench target (closest to a knockout / prize) ----------
@pytest.mark.req("REQ-GEN-0018")
def test_snipe_the_weakest_prefers_the_lowest_hp_bench_target():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=DictCardStatProvider({}), attacks={11: 50})
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1),
                       card_opt(BENCH, 2, player=1)], context=DAMAGE,
                      current=state(active=poke(700, energy=1),
                                    opp_bench=[poke(900, hp=140), poke(901, hp=50), poke(902, hp=300)]))
    assert pilot.decide(obs) == [1]                                  # the 50-HP target (weakest)
    assert "snipe-the-weakest" in _fired(pilot.explain(obs).options[1])
    assert "snipe-the-weakest" not in _fired(pilot.explain(obs).options[2])   # the 300-HP wall


@pytest.mark.req("REQ-GEN-0018")
def test_snipe_the_threat_outranks_the_weakest():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=DictCardStatProvider({}), attacks={11: 50})
    # idx0 carries Energy (a live threat, high HP); idx1 is the weakest. threat (20) > weakest (15).
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700, energy=1),
                                    opp_bench=[poke(900, energy=2, hp=200), poke(901, hp=50)]))
    assert pilot.decide(obs) == [0]


# --- prefer-wincon-line-piece: fetch/promote the line's pre-evolution over an off-line card -------
@pytest.mark.req("REQ-GEN-0019")
def test_prefer_wincon_line_piece_fetches_the_preevolution_over_an_offline_card():
    stats = DictCardStatProvider({STARYU: CardStat(STARYU, hp=70), MEGA: CardStat(MEGA, megaEx=True, hp=330),
                                  CINDERACE: CardStat(CINDERACE, hp=160)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)], roles={MEGA: ["win_condition"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": CINDERACE}, {"id": STARYU}], current=state(active=poke(900, energy=1)))
    assert pilot.decide(obs) == [1]                                  # the line pre-evo (Staryu)
    assert "prefer-wincon-line-piece" in _fired(pilot.explain(obs).options[1])
    assert "prefer-wincon-line-piece" not in _fired(pilot.explain(obs).options[0])   # Cinderace: off-line


@pytest.mark.req("REQ-GEN-0019")
def test_promote_three_way_priority_ready_wincon_then_evolvable_then_staller():
    """Promote after a KO: (1) a powered benched win-condition attacks now; (2) else evolve a
    pre-evolution IF the payoff is in hand; (3) else promote the disposable opener to protect the
    fragile pre-evolution. The bare pre-evo is NOT promoted just because it's on the line."""
    stats = DictCardStatProvider({STARYU: CardStat(STARYU, hp=70), MEGA: CardStat(MEGA, megaEx=True, hp=330),
                                  CINDERACE: CardStat(CINDERACE, hp=160)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    promote = [card_opt(BENCH, 0, player=0), card_opt(BENCH, 1, player=0)]

    # (3) no Mega, no powered wincon -> promote the staller (Cinderace), keep Staryu safe
    obs = make_select(promote, context=4, current=state(bench=[poke(CINDERACE), poke(STARYU, energy=1)]))
    assert pilot.decide(obs) == [0]
    assert "promote-the-staller" in _fired(pilot.explain(obs).options[0])

    # (2) Mega in hand -> promote the pre-evo to evolve it this turn
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE), poke(STARYU, energy=1)], hand=[MEGA]))
    assert pilot.decide(obs) == [1]

    # (1) a powered Mega is benched -> promote it to attack
    obs = make_select(promote, context=4, current=state(bench=[poke(CINDERACE), poke(MEGA, energy=3)]))
    assert pilot.decide(obs) == [1]
    assert "promote-the-ready-wincon" in _fired(pilot.explain(obs).options[1])


# --- retreat-to-ready-attacker: bring a powered benched win-condition to the front ----------------
@pytest.mark.req("REQ-GEN-0020")
def test_retreat_to_a_ready_benched_wincon_over_a_weak_chip():
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, hp=60), MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, ready=Ready(energy=1))],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(12)], context=MAIN,        # opt(12) = RETREAT
                      current=state(active=poke(CINDERACE, energy=2, hp=60),
                                    bench=[poke(MEGA, energy=3, hp=330)], opp_active=poke(900, hp=200)))
    b = pilot._board(obs)
    assert b.bench_wincon_ready and not b.active_is_wincon
    assert pilot.decide(obs) == [1]                                  # retreat (60) beats the 50 chip


@pytest.mark.req("REQ-GEN-0020")
def test_retreat_to_ready_attacker_never_overrides_a_knockout():
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, hp=60), MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, ready=Ready(energy=1))],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, attacks={11: 50})
    obs = make_select([attack_opt(11), opt(12)], context=MAIN,
                      current=state(active=poke(CINDERACE, energy=2, hp=60),
                                    bench=[poke(MEGA, energy=3, hp=330)], opp_active=poke(900, hp=40)))
    assert pilot.decide(obs) == [0]                                  # the chip is now lethal -> take the KO


# --- save-tool-for-the-attacker: don't equip a Tool to an off-role Pokémon ------------------------
@pytest.mark.req("REQ-GEN-0021")
def test_save_tool_for_the_attacker_declines_an_offrole_target():
    HEROCAPE = 1159
    stats = DictCardStatProvider({HEROCAPE: CardStat(HEROCAPE), CINDERACE: CardStat(CINDERACE, hp=160)})
    funcs = CardFunctions({HEROCAPE: ["tool"]})
    strat = Strategy(roles={CINDERACE: ["starter"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    cape = {"type": ATTACH, "area": HAND, "index": 0, "inPlayArea": 4, "inPlayIndex": 0}
    obs = make_select([cape, opt(14)], context=MAIN,                 # opt(14) = End turn
                      current=state(active=poke(CINDERACE, energy=1, hp=160), hand=[HEROCAPE]))
    assert "save-tool-for-the-attacker" in _fired(pilot.explain(obs).options[0])
    assert pilot.decide(obs) == [1]                                  # save the Cape -> End, don't equip Cinderace


@pytest.mark.req("REQ-GEN-0020")
def test_drew_the_evolution_evolve_then_retreat_the_staller_into_the_ready_wincon():
    """The follow-up to promote-the-staller: once you draw the evolution, evolve the benched pre-evo
    THEN retreat the staller into the now-ready win-condition — emergent across one turn's two
    decisions (evolve-into-wincon + attack-last, then the SETUP->RACE flip + retreat-to-ready-attacker)."""
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, hp=120), STARYU: CardStat(STARYU, hp=70),
                                  MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, ready=Ready(energy=1))],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
                  attacks={11: 30})
    # step 1: drew Mega; Active is the staller Cinderace, benched Staryu(e1) -> evolve the Staryu first
    evolve = {"type": 9, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0}
    obs1 = make_select([evolve, opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(STARYU, energy=1)], hand=[MEGA], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs1) == [0]                                  # evolve Staryu -> Mega
    # step 2: the Staryu is now a benched Mega(e1) -> retreat the staller into it
    obs2 = make_select([opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(MEGA, energy=1)], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs2) == [0]                                  # retreat -> bring up the ready Mega
    assert "retreat-to-ready-attacker" in _fired(pilot.explain(obs2).options[0])


@pytest.mark.req("REQ-GEN-0017")
def test_dig_before_the_irreversible_energy_attach_even_with_no_attack():
    """Tier sequencing below attack-last: a draw/search (informative, tier 0) is played BEFORE the
    Energy attach (the irreversible per-turn commit, tier 1) — even at a menu with no attack yet.
    (f11: Pokégear before attaching Ignition.)"""
    DIG = 1227
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, hp=160), DIG: CardStat(DIG),
                                  BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    funcs = CardFunctions({DIG: ["search"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    attach = {"type": ATTACH, "area": HAND, "index": 1, "inPlayArea": 4, "inPlayIndex": 0}  # Basic -> Active
    dig = {"type": PLAY, "index": 0}                                  # play the search card (hand[0])
    obs = make_select([attach, dig, opt(14)], context=MAIN,
                      current=state(active=poke(CINDERACE, energy=0, hp=160), hand=[DIG, BASIC_W]))
    assert pilot.decide(obs) == [1]                                  # dig (tier 0) before the attach (tier 1)
