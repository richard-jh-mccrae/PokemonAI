"""Search / fetch discipline + the RACE weak-chip rule (this round's blunder corrections).

Covers the infrastructure that lets the Pilot *see* a search decision (resolving a DECK option from
the select's revealed `deck` list and a DISCARD option from the player's discard pile), the deck-
agnostic search/development Hypotheses it unblocks (`fetch-the-wincon`, `fetch-energy-when-starved`,
`prefer-bench-fill-first`, `snipe-the-weakest`, the promote/retreat doctrine), "attack last"
sequencing, and the guard that the board-commit intent rules do NOT leak onto a fetch sub-selection.
See docs/tuning/methodology.md, ADR-0008.
"""
import pytest

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
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
    """A DECK candidate's id lives in the select's revealed `deck` list, a DISCARD candidate's in the
    player's discard pile; unresolved, a fetch carries no roles/tags/stat at all."""
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
def test_fetch_the_wincon_stands_down_when_the_payoff_is_already_in_play():
    # adversarial-review fix: don't pull a dead 2nd copy when the win-condition's already in play
    stats = DictCardStatProvider({MEGA: CardStat(MEGA, megaEx=True, hp=330)})
    pilot = Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}),
                  deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": MEGA}],
                      current=state(active=poke(MEGA, energy=2)))             # Mega already Active
    assert pilot._board(obs).wincon_in_play
    assert "fetch-the-wincon" not in _fired(pilot.explain(obs).options[0])


# --- fetch-energy-when-starved -------------------------------------------------------------------




@pytest.mark.req("REQ-GEN-0014")
def test_fetch_energy_when_starved_is_off_when_energy_is_already_in_hand():
    stats = DictCardStatProvider({BASIC_W: CardStat(BASIC_W, energyType=WATER)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # reusable Energy already in hand -> not starved -> rule doesn't fire
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": BASIC_W}],
                      current=state(active=poke(900, energy=0), hand=[BASIC_W]))
    assert "fetch-energy-when-starved" not in _fired(pilot.explain(obs).options[0])


# --- prefer-bench-fill-first ---------------------------------------------------------------------


@pytest.mark.req("REQ-GEN-0015")
def test_prefer_bench_fill_first_stands_down_on_a_full_bench():
    # adversarial-review fix: bench-filler places nothing on a full Bench -> don't promote it
    funcs = CardFunctions({POFFIN: ["search", "bench_fill"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    full = [poke(701), poke(702), poke(703), poke(704), poke(705)]            # 5 = full Bench
    obs = make_select([opt(PLAY, area=HAND, index=0)], current=state(bench=full, hand=[POFFIN]))
    assert pilot._board(obs).my_bench == 5
    assert "prefer-bench-fill-first" not in _fired(pilot.explain(obs).options[0])


# The six attack-last / chip-discipline sequencing tests are DELETED (Issue #386): under differencing
# sequencing is not a rule, and a hand-built two-option menu cannot ask the question.

# --- the leak guard: board-commit intent rules must not fire on a fetch sub-selection ------------
@pytest.mark.req("REQ-GEN-0017")
def test_board_intent_rules_do_not_leak_onto_search_options():
    # A fetched card's tags resolve at a ToHand search, but board-commit intent rules govern PLAYS,
    # not which card a search pulls, so they must stay silent.
    funcs = CardFunctions({222: ["search", "energy_accel"]})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, functions=funcs)
    obs = make_select([card_opt(DECK, 0)], context=TO_HAND, deck=[{"id": 222}],
                      current=state(active=poke(700, energy=1)))
    fired = _fired(pilot.explain(obs).options[0])
    assert "use-acceleration" not in fired


# --- attack-last: an attack ends the turn, so beneficial development is sequenced ahead of it ----
@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_sequences_development_before_the_turn_ending_attack():
    """A KO attack co-exists with a beneficial development (a +30 play). Attacking ends the turn,
    but the KO survives the play — so develop first and keep the attack for last (same turn)."""
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, energyType=WATER), 900: CardStat(900, synthetic=True, hp=40)},
                                 attacks={11: AttackStat(11, damage=50)})
    dev = Hypothesis(id="dev", rationale="", when=lambda c: c.option_type == PLAY, weight=30)
    pilot = Pilot(Strategy(hypotheses=[dev]), deck=[1] * 60, stats=stats)
    obs = make_select([attack_opt(11), opt(PLAY)], context=MAIN,
                      current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    d = pilot.explain(obs)
    assert d.options[0].tactical >= KO_SCORE          # attack is a KO (50 >= 40) ...
    assert pilot.decide(obs) == [1]                   # ...but the +30 development goes first
    assert d.options[0].deferred                      # KO held back, never dropped


@pytest.mark.req("REQ-GEN-0017")
def test_attack_last_protects_a_knockout_from_an_active_evolve_but_not_otherwise():
    """Evolving the Active replaces its attack, so it must NOT be sequenced ahead of an available
    knockout (that would forfeit the KO) — but with no KO on the menu it is normal development."""
    EVOLVE, ACTIVE_AREA = 9, 4
    stats = DictCardStatProvider({700: CardStat(700, synthetic=True, energyType=WATER), 900: CardStat(900, synthetic=True, hp=40),
                                  901: CardStat(901, synthetic=True, hp=200)},
                                 attacks={11: AttackStat(11, damage=50)})
    ev = Hypothesis(id="ev", rationale="", when=lambda c: c.option_type == EVOLVE, weight=40)
    pilot = Pilot(Strategy(hypotheses=[ev]), deck=[1] * 60, stats=stats)
    ko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                     current=state(active=poke(700, energy=1), opp_active=poke(900, hp=40)))
    assert pilot.decide(ko) == [0]                    # KO present -> don't evolve the Active away
    noko = make_select([attack_opt(11), opt(EVOLVE, inPlayArea=ACTIVE_AREA)], context=MAIN,
                       current=state(active=poke(700, energy=1), opp_active=poke(901, hp=200)))
    assert pilot.decide(noko) == [1]                  # no KO to forfeit -> evolve the Active first


# The snipe-for-the-KO rung test is DELETED with its rung (ADR-0085); the free prize is now the
# structural `_snipe_ko_dominator`, which cannot be out-summed the way a +60 rung was.

@pytest.mark.req("REQ-GEN-0018")
def test_snipe_the_threat_outranks_the_weakest():
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=DictCardStatProvider({}, attacks={11: AttackStat(11, damage=50)}))
    # idx0 carries Energy (live threat, high HP); idx1 is weakest. `snipe_relevance` orders them.
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700, energy=1),
                                    opp_bench=[poke(900, energy=2, hp=200), poke(901, hp=50)]))
    assert pilot.decide(obs) == [0]


# --- prefer-wincon-line-piece: fetch/promote the line's pre-evolution over an off-line card -------


@pytest.mark.req("REQ-GEN-0019")
def test_promote_three_way_priority_ready_wincon_then_evolvable_then_staller():
    """(1) a powered benched win-condition attacks now; (2) else promote the body that can ACT;
    (3) else the disposable opener. A bare pre-evo is NOT promoted just for being on the line."""
    # Real attack records on both attackers: ADR-0052 retired the `minCostDamage` fallback, so a
    # statline without `attacks` prices every body at zero and asserts nothing about the decider.
    stats = DictCardStatProvider(
        {STARYU: CardStat(STARYU, hp=70),
         MEGA: CardStat(MEGA, synthetic=True, megaEx=True, hp=330, minAttackCost=3, maxDamage=210,
                        maxDamageCost=3, attacks=(21,)),
         CINDERACE: CardStat(CINDERACE, hp=160, minAttackCost=1, maxDamage=50,
                             maxDamageCost=1, attacks=(22,))},
        attacks={21: AttackStat(21, damage=210, cost=3), 22: AttackStat(22, damage=50, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA)],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    promote = [card_opt(BENCH, 0, player=0), card_opt(BENCH, 1, player=0)]

    # (3) no Mega, no powered wincon -> promote the staller (Cinderace), keep Staryu safe
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(STARYU, energy=1)]))
    assert pilot.decide(obs) == [0]   # the staller pick is EMERGENT now (ADR-0100 §6a): its own
                                     # damage plus the LOW exposure that IS "disposable"

    # (2) Mega in hand but the pre-evo could not pay the evolved attack -> promote the body that acts
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(STARYU, energy=1)],
                                    hand=[MEGA]))
    assert pilot.decide(obs) == [0]

    # (1) a powered Mega is benched -> promote it to attack
    obs = make_select(promote, context=4,
                      current=state(bench=[poke(CINDERACE, energy=1), poke(MEGA, energy=3)]))
    assert pilot.decide(obs) == [1]   # EMERGENT from reachable damage (ADR-0100 §3) — the rung and
                                     # its `is_best_promote_target` tie-break are DELETED


# The Tool Doctrine rung tests are DELETED with `doctrines/doctrine_tool.py` (Issue #386); a Tool
# that buys a survival turn is now `survival` on the composed end board (ADR-0086).
@pytest.mark.req("REQ-GEN-0020")
def test_drew_the_evolution_evolve_then_retreat_the_staller_into_the_ready_wincon():
    """Once you draw the evolution, evolve the benched pre-evo THEN retreat the staller into the
    now-ready win-condition — emergent across one turn's two decisions."""
    # The payoff needs a REAL attack record: a stat-blind Mega has `payoff_damage` 0, so the evolve
    # earns nothing on any term and the test asserts the absence of a signal (ADR-0067).
    stats = DictCardStatProvider({CINDERACE: CardStat(CINDERACE, synthetic=True, hp=120), STARYU: CardStat(STARYU, synthetic=True, hp=70),
                                  MEGA: CardStat(MEGA, synthetic=True, megaEx=True, hp=330, maxDamage=210,
                                                 maxDamageCost=1, minAttackCost=1, attacks=(99,))},
                                 attacks={11: AttackStat(11, damage=30),
                                          99: AttackStat(99, damage=210, cost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, ready=Ready(energy=1))],
                     roles={MEGA: ["win_condition", "primary_attacker"]})
    funcs = CardFunctions({CINDERACE: ["opener"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # step 1: drew Mega; Active is the staller Cinderace, benched Staryu(e1) -> evolve Staryu first
    evolve = {"type": 9, "area": HAND, "index": 0, "inPlayArea": BENCH, "inPlayIndex": 0}
    obs1 = make_select([evolve, opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(STARYU, energy=1)], hand=[MEGA], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs1) == [0]                                  # evolve Staryu -> Mega
    # step 2: Staryu now a benched Mega(e1) -> retreat the staller into it
    obs2 = make_select([opt(12), attack_opt(11), opt(14)], context=MAIN,
                       current=state(active=poke(CINDERACE, energy=1, hp=120),
                                     bench=[poke(MEGA, energy=1)], opp_active=poke(999, hp=120)))
    assert pilot.decide(obs2) == [0]   # retreat -> bring up the ready Mega. EMERGENT from
                                      # destination value minus retreat cost (ADR-0100 §11)

