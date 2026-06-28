"""Pilot: turn an observation into a legal selection (ADR-0008)."""
import pytest

from common.pilot import KO_SCORE, Pilot, choose_plan
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Plan, Ready, Strategy
from pilot_helpers import (
    BENCH, DAMAGE, HAND, MAIN, PLAY, SETUP_ACTIVE, attack_opt, card_opt, make_select, opt,
    poke, state,
)

MEGA_STARMIE, STARYU, CINDERACE = 1031, 1030, 666


@pytest.mark.req("REQ-PILOT-0001")
def test_decide_returns_a_legal_selection():
    pilot = Pilot(Strategy(), deck=[1] * 60)
    obs = make_select([opt(), opt(), opt(), opt()], min_count=1, max_count=2)

    sel = pilot.decide(obs)

    options = obs["select"]["option"]
    assert 1 <= len(sel) <= 2                        # count within [minCount, maxCount]
    assert len(set(sel)) == len(sel)                 # no duplicates
    assert all(0 <= i < len(options) for i in sel)   # indices in range


@pytest.mark.req("REQ-PILOT-0002")
def test_decide_returns_deck_on_initial_selection():
    deck = list(range(1, 61))
    pilot = Pilot(Strategy(), deck=deck)

    # The engine hands the agent select=None at the initial deck-submission step.
    assert pilot.decide({"select": None, "current": None, "logs": []}) == deck


@pytest.mark.req("REQ-PILOT-0003")
def test_plan_is_setup_until_wincon_is_ready():
    strat = Strategy(lines=[Line(path=[STARYU, MEGA_STARMIE], payoff=MEGA_STARMIE,
                                 ready=Ready(energy=3))])

    setup_pre = state(active=poke(STARYU))                   # payoff not in play
    setup_low = state(active=poke(MEGA_STARMIE, energy=2))   # in play, under-fuelled
    racing = state(active=poke(MEGA_STARMIE, energy=3))      # in play, ready

    assert choose_plan(setup_pre, strat) == Plan.SETUP
    assert choose_plan(setup_low, strat) == Plan.SETUP
    assert choose_plan(racing, strat) == Plan.RACE


@pytest.mark.req("REQ-PILOT-0018")
def test_readiness_is_engine_derived_when_ready_is_unset():
    # Mega Starmie's cheapest attack (Jetting Blow) costs 1 energy. Leaving `ready` unset derives
    # "online" from the engine: payoff in play with >= 1 energy -> RACE (not the 3 Nebula demands).
    stats = DictCardStatProvider({MEGA_STARMIE: CardStat(MEGA_STARMIE, minAttackCost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA_STARMIE], payoff=MEGA_STARMIE)])  # ready unset

    assert choose_plan(state(active=poke(MEGA_STARMIE, energy=0)), strat, stats) == Plan.SETUP
    assert choose_plan(state(active=poke(MEGA_STARMIE, energy=1)), strat, stats) == Plan.RACE


@pytest.mark.req("REQ-PILOT-0019")
def test_among_knockouts_the_cheaper_attack_is_preferred():
    # Both attacks KO the 100-HP target; prefer the cheaper cost so the finisher's Energy is
    # left in reserve. The pricey KO is option 0, so only an efficiency tiebreak can choose opt1.
    CHEAP, PRICEY = 11, 12
    pilot = Pilot(Strategy(), deck=[1] * 60, attacks={CHEAP: 120, PRICEY: 210},
                  attack_costs={CHEAP: 1, PRICEY: 3})
    obs = make_select([attack_opt(PRICEY), attack_opt(CHEAP)], context=MAIN,
                      current=state(active=poke(700), opp_active=poke(900, hp=100)))
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0004")
def test_hypothesis_biases_its_choice():
    open_cinderace = Hypothesis(
        id="open-cinderace",
        rationale="Explosiveness opener enables turn-1 accel",
        when=lambda c: c.plan == Plan.SETUP and "accel_source" in c.roles,
        weight=40)
    strat = Strategy(roles={CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]},
                     hypotheses=[open_cinderace])
    pilot = Pilot(strat, deck=[1] * 60)

    # Cinderace is option 1 (Staryu is 0), so only real scoring — not a "pick index 0"
    # stub — can choose it.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      context=SETUP_ACTIVE, current=state(hand=[STARYU, CINDERACE]))

    assert pilot.decide(obs) == [1]   # the open-cinderace hypothesis lifts Cinderace


@pytest.mark.req("REQ-PILOT-0005")
def test_tactical_evaluator_prefers_a_ko():
    JETTING, NEBULA = 11, 12  # attack ids
    pilot = Pilot(Strategy(), deck=[1] * 60, attacks={JETTING: 50, NEBULA: 210})

    # Opponent active has 200 HP: Nebula (210) KOs it, Jetting (50) does not. The KO
    # attack is option 1, so only outcome-aware scoring can choose it.
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA)], context=MAIN,
                      current=state(active=poke(MEGA_STARMIE, energy=3),
                                    opp_active=poke(9999, hp=200, max_hp=200)))

    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0007")
def test_decide_never_raises_on_malformed_obs():
    # Even a hypothesis whose trigger blows up must not crash the agent.
    boom = Hypothesis("boom", "", when=lambda c: 1 / 0, weight=99)
    pilot = Pilot(Strategy(hypotheses=[boom]), deck=list(range(60)))

    assert pilot.decide({}) == list(range(60))                          # no select -> deck
    assert isinstance(pilot.decide({"select": None}), list)
    assert isinstance(pilot.decide(make_select([opt(), opt()])), list)  # boom ignored
    assert isinstance(pilot.decide(make_select([opt()], current={"players": []})), list)


@pytest.mark.req("REQ-PILOT-0008")
def test_general_strategy_biases_choice_for_any_deck():
    # A General Strategy hypothesis applies to every deck — even one whose own Strategy is empty.
    prefer = Hypothesis(id="gs-prefer", rationale="generic baseline preference",
                        when=lambda c: c.card_id == 222, weight=40)
    pilot = Pilot(Strategy(), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[prefer]))

    # opt0 -> card 111, opt1 -> card 222; only the General Strategy hyp can lift opt1.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0009")
def test_general_and_deck_hypotheses_are_additive():
    gen = Hypothesis(id="gs-a", rationale="generic boost on card 111",
                     when=lambda c: c.card_id == 111, weight=10)
    deck_a = Hypothesis(id="deck-a", rationale="deck boost on card 111",
                        when=lambda c: c.card_id == 111, weight=10)
    deck_b = Hypothesis(id="deck-b", rationale="deck boost on card 222",
                        when=lambda c: c.card_id == 222, weight=15)
    pilot = Pilot(Strategy(hypotheses=[deck_a, deck_b]), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[gen]))

    # opt0 (card 111): general 10 + deck 10 = 20.  opt1 (card 222): deck 15.
    # opt0 wins only if the general weight is ADDED to the deck weight (else 10 < 15 -> opt1).
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PILOT-0010")
def test_override_by_id_sets_the_effective_weight():
    # gs-weak loses at its default (5 < rival 20); an id-keyed override raises it to 99 -> it wins.
    gen = Hypothesis(id="gs-weak", rationale="weak by default",
                     when=lambda c: c.card_id == 222, weight=5)
    rival = Hypothesis(id="deck-rival", rationale="deck boost on card 111",
                       when=lambda c: c.card_id == 111, weight=20)
    pilot = Pilot(Strategy(hypotheses=[rival]), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[gen]),
                  overrides={"gs-weak": 99})

    # opt0 (card 111): rival 20.  opt1 (card 222): gs-weak overridden 5 -> 99.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0011")
def test_override_of_zero_disables_a_general_rule():
    gen = Hypothesis(id="gs-prefer", rationale="generic preference for card 222",
                     when=lambda c: c.card_id == 222, weight=40)
    pilot = Pilot(Strategy(), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[gen]),
                  overrides={"gs-prefer": 0})

    # weight 40 would pick opt1; overridden to 0 the rule can't fire its weight, so opt0 (baseline) wins.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PILOT-0012")
def test_explain_reports_the_firing_hypotheses_from_both_layers():
    gen = Hypothesis(id="gs", rationale="generic", when=lambda c: c.card_id == 222, weight=10)
    deck = Hypothesis(id="dk", rationale="deck", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(hypotheses=[deck]), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[gen]))
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    decision = pilot.explain(obs)

    assert decision.chosen == pilot.decide(obs)                 # explain agrees with decide
    fired_ids = {h.id for h, _ in decision.options[1].fired}    # opt1 = card 222
    assert fired_ids == {"gs", "dk"}                            # both layers visible in the trace


@pytest.mark.req("REQ-PILOT-0013")
def test_explain_traces_plan_and_card_and_leaves_untriggered_options_empty():
    gen = Hypothesis(id="gs", rationale="generic", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=Strategy(hypotheses=[gen]))
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    opt0, opt1 = pilot.explain(obs).options

    assert opt0.card_id == 111 and opt0.fired == []            # nothing fires on card 111
    assert opt1.card_id == 222 and opt1.plan == Plan.SETUP     # the card -> Plan chain is traced
    assert {h.id for h, _ in opt1.fired} == {"gs"}


@pytest.mark.req("REQ-PILOT-0014")
def test_weakness_doubles_tactical_damage_and_can_flip_the_choice():
    WATER, FIRE = 3, 2
    ATK = 11
    stats = DictCardStatProvider({
        700: CardStat(700, energyType=WATER),                           # my Water attacker
        800: CardStat(800, energyType=FIRE, weakness=WATER, hp=160),    # weak to Water
        900: CardStat(900, energyType=FIRE, weakness=None, hp=160),     # not weak
    })
    # A positional rule lifts the non-attack play to 100; the attack prints 90.
    prefer_play = Hypothesis(id="prefer-play", rationale="", when=lambda c: c.option_type == PLAY, weight=100)
    pilot = Pilot(Strategy(hypotheses=[prefer_play]), deck=[1] * 60, stats=stats, attacks={ATK: 90})

    def vs(defender):   # opt0 = a play (100 via hypothesis), opt1 = the 90-damage attack
        return make_select([opt(PLAY), attack_opt(ATK)], context=MAIN,
                           current=state(active=poke(700, energy=3), opp_active=poke(defender, hp=160)))

    # Weakness doubling flips the ATTACK's tactical value from a 90 chip to a 180 KO.
    assert pilot.explain(vs(800)).options[1].tactical >= KO_SCORE   # 90x2 = 180 >= 160 -> KO recognised
    assert pilot.explain(vs(900)).options[1].tactical == 90         # 90 < 160 -> just a chip
    # Final pick: the +100 play is beneficial development, so "attack-last" sequences it ahead of the
    # attack either way (the KO is taken on the same turn once development is exhausted).
    assert pilot.decide(vs(800)) == [0] and pilot.decide(vs(900)) == [0]


@pytest.mark.req("REQ-PILOT-0015")
def test_context_exposes_cardstat_to_hypotheses():
    stats = DictCardStatProvider({222: CardStat(222, ex=True, megaEx=True)})
    # A General Strategy hypothesis that reads engine stats off the Context (a 3-prize Mega liability).
    mega_aware = Hypothesis(id="mega-aware", rationale="reads ctx.stat",
                            when=lambda c: bool(c.stat and c.stat.megaEx), weight=50)
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats,
                  general_strategy=Strategy(hypotheses=[mega_aware]))

    # opt0 = card 111 (no stat), opt1 = card 222 (megaEx) -> the stat-reading hypothesis lifts opt1.
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0016")
def test_context_board_exposes_my_bench_count():
    watch = Hypothesis(id="empty-bench", rationale="", when=lambda c: c.board.my_bench == 0, weight=5)
    pilot = Pilot(Strategy(hypotheses=[watch]), deck=[1] * 60)
    fired = lambda o: {h.id for h, _ in o.fired}

    no_bench = make_select([opt()], current=state(active=poke(700)))
    assert "empty-bench" in fired(pilot.explain(no_bench).options[0])

    with_bench = make_select([opt()], current=state(active=poke(700), bench=[poke(701)]))
    assert "empty-bench" not in fired(pilot.explain(with_bench).options[0])


@pytest.mark.req("REQ-PILOT-0020")
def test_context_exposes_attack_target_energy_and_threat():
    # At a Damage/snipe select the Context must expose, per option, the attached-energy count of
    # the benched Pokémon it targets — and the derived "threat" boolean (has Energy) — so a snipe
    # trigger can prefer the energized (closest-to-attacking) target.
    counts = Hypothesis(id="energy-2", rationale="", when=lambda c: c.target_energy == 2, weight=1)
    threat = Hypothesis(id="threat", rationale="", when=lambda c: c.target_is_threat, weight=1)
    pilot = Pilot(Strategy(hypotheses=[counts, threat]), deck=[1] * 60)
    fired = lambda o: {h.id for h, _ in o.fired}

    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(800, energy=0), poke(900, energy=2)]))
    opt0, opt1 = pilot.explain(obs).options
    assert fired(opt0) == set()                       # bare target: no energy -> not a threat
    assert fired(opt1) == {"energy-2", "threat"}      # energized target: count + threat exposed


@pytest.mark.req("REQ-PILOT-0021")
def test_target_energy_flips_the_snipe_and_is_none_off_a_damage_select():
    # The new field flips the preferred target: a snipe rule lifts the energized bench option (opt1,
    # so only real scoring can choose it). The signal is defined ONLY for attack-target options —
    # at any other select it is None/False, so the same rule cannot fire and the baseline holds.
    snipe = Hypothesis(id="snipe", rationale="prefer the energized threat",
                       when=lambda c: c.target_is_threat, weight=30)
    pilot = Pilot(Strategy(hypotheses=[snipe]), deck=[1] * 60)
    targets = [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)]
    board = state(active=poke(700), opp_bench=[poke(800, energy=0), poke(900, energy=1)])

    snipe_select = make_select(targets, context=DAMAGE, current=board)
    assert pilot.decide(snipe_select) == [1]          # energized target wins the snipe

    off_target = make_select(targets, context=MAIN, current=board)
    assert pilot.decide(off_target) == [0]            # not a Damage select -> no signal -> baseline


@pytest.mark.req("REQ-PILOT-0017")
def test_tactical_values_a_ko_by_the_defenders_prize_count():
    stats = DictCardStatProvider({800: CardStat(800, megaEx=True), 900: CardStat(900)})
    ATK = 11
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats, attacks={ATK: 150})  # 150 KOs 100 HP

    def ko_score(defender):
        obs = make_select([attack_opt(ATK)], context=MAIN,
                          current=state(active=poke(700), opp_active=poke(defender, hp=100)))
        return pilot.explain(obs).options[0].score

    # both are knockouts, but KOing a 3-prize Mega ex is worth more than a 1-prize basic
    assert ko_score(800) > ko_score(900)
