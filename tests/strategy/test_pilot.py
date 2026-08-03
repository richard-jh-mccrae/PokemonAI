"""Pilot: turn an observation into a legal selection (ADR-0008)."""
import pytest

from common.pilot import KO_SCORE, Pilot, choose_plan
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Hypothesis, Line, Plan, Ready, Strategy
from pilot_helpers import (
    BENCH, DAMAGE, HAND, MAIN, PLAY, SETUP_ACTIVE, attack_opt, card_opt, make_select, opt,
    poke, state,
)

MEGA_STARMIE, STARYU, CINDERACE = 1031, 1030, 666


@pytest.mark.req("REQ-STAT-0002")
def test_attack_facts_resolve_through_the_stat_provider_alone():
    # The Stat Provider is the ONE card-knowledge seam (ADR-0051): a Pilot wired with a
    # provider that carries the attack records — and NO attacks=/attack_stats= ctor args —
    # still sees damage/cost, so a KO scores as a KO.
    jetting = 11
    stats = DictCardStatProvider(
        {MEGA_STARMIE: CardStat(MEGA_STARMIE, name="Mega Starmie ex", hp=330, megaEx=True,
                                energyType=3, attacks=(jetting,), minAttackCost=1),
         CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, energyType=2, weakness=3)},
        attacks={jetting: AttackStat(jetting, damage=120, cost=1)})
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats)
    obs = make_select([attack_opt(jetting)], context=MAIN,
                      current=state(active=poke(MEGA_STARMIE, energy=3),
                                    opp_active=poke(CINDERACE, hp=160)))
    # 120 x2 (Cinderace weak to Water) = 240 >= 160 -> the KO band, provider-only wiring
    assert pilot.explain(obs).options[0].score >= KO_SCORE


@pytest.mark.req("REQ-STAT-0002")
def test_legacy_attack_kwargs_are_retired():
    # ADR-0051: the per-mechanic dicts and the prebuilt attack_stats table are gone from the
    # ctor — attack facts have exactly ONE entrance (stats.attack). A resurrected kwarg must
    # fail loudly, not silently feed a second fact path.
    for kwarg in ("attacks", "attack_costs", "recoil", "bench_snipe", "bench_spread",
                  "ignores_active_effects", "attack_stats"):
        with pytest.raises(TypeError):
            Pilot(Strategy(), deck=[1] * 60, **{kwarg: {}})


@pytest.mark.req("REQ-PILOT-0001")
def test_decide_returns_a_legal_selection():
    pilot = Pilot(Strategy(), deck=[1] * 60)
    obs = make_select([opt(), opt(), opt(), opt()], min_count=1, max_count=2)

    sel = pilot.decide(obs)

    options = obs["select"]["option"]
    assert 1 <= len(sel) <= 2                        # count in [minCount, maxCount]
    assert len(set(sel)) == len(sel)                 # no dupes
    assert all(0 <= i < len(options) for i in sel)   # indices in range


@pytest.mark.req("REQ-PILOT-0002")
def test_decide_returns_deck_on_initial_selection():
    deck = list(range(1, 61))
    pilot = Pilot(Strategy(), deck=deck)

    # engine hands agent select=None at initial deck-submission step
    assert pilot.decide({"select": None, "current": None, "logs": []}) == deck


@pytest.mark.req("REQ-PILOT-0003")
def test_plan_is_setup_until_wincon_is_ready():
    strat = Strategy(lines=[Line(path=[STARYU, MEGA_STARMIE], payoff=MEGA_STARMIE,
                                 ready=Ready(energy=3))])

    setup_pre = state(active=poke(STARYU))                   # payoff not in play
    setup_low = state(active=poke(MEGA_STARMIE, energy=2))   # in play, under-fueled
    racing = state(active=poke(MEGA_STARMIE, energy=3))      # in play, ready

    assert choose_plan(setup_pre, strat) == Plan.SETUP
    assert choose_plan(setup_low, strat) == Plan.SETUP
    assert choose_plan(racing, strat) == Plan.RACE


@pytest.mark.req("REQ-PILOT-0018")
def test_readiness_is_engine_derived_when_ready_is_unset():
    # Mega Starmie's cheapest attack (Jetting Blow) costs 1 energy. Leaving `ready` unset derives
    # "online" from engine: payoff in play w/ >= 1 energy -> RACE (not the 3 Nebula demands).
    stats = DictCardStatProvider({MEGA_STARMIE: CardStat(MEGA_STARMIE, minAttackCost=1)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA_STARMIE], payoff=MEGA_STARMIE)])  # ready unset

    assert choose_plan(state(active=poke(MEGA_STARMIE, energy=0)), strat, stats) == Plan.SETUP
    assert choose_plan(state(active=poke(MEGA_STARMIE, energy=1)), strat, stats) == Plan.RACE


@pytest.mark.req("REQ-PILOT-0019")
def test_among_knockouts_the_cheaper_attack_is_preferred():
    # Both attacks KO the 100-HP target; prefer cheaper cost so finisher's Energy stays in
    # reserve. Pricey KO is option 0, so only an efficiency tiebreak can choose opt1.
    CHEAP, PRICEY = 11, 12
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=DictCardStatProvider({}, attacks={
        CHEAP: AttackStat(CHEAP, damage=120, cost=1),
        PRICEY: AttackStat(PRICEY, damage=210, cost=3)}))
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

    assert pilot.decide(obs) == [1]   # open-cinderace hypothesis lifts Cinderace


@pytest.mark.req("REQ-PILOT-0005")
def test_tactical_evaluator_prefers_a_ko():
    JETTING, NEBULA = 11, 12  # attack ids
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=DictCardStatProvider({}, attacks={
        JETTING: AttackStat(JETTING, damage=50), NEBULA: AttackStat(NEBULA, damage=210)}))

    # Opponent active has 200 HP: Nebula (210) KOs it, Jetting (50) doesn't. KO
    # attack is option 1, so only outcome-aware scoring can choose it.
    obs = make_select([attack_opt(JETTING), attack_opt(NEBULA)], context=MAIN,
                      current=state(active=poke(MEGA_STARMIE, energy=3),
                                    opp_active=poke(9999, hp=200, max_hp=200)))

    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-PILOT-0007")
def test_decide_never_raises_on_malformed_obs():
    # Even a hypothesis whose trigger blows up must not crash agent.
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

    # opt0 -> card 111, opt1 -> card 222; only General Strategy hyp can lift opt1
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
    # opt0 wins only if general weight is ADDED to deck weight (else 10 < 15 -> opt1)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-PILOT-0010")
def test_override_by_id_sets_the_effective_weight():
    # gs-weak loses at default (5 < rival 20); id-keyed override raises it to 99 -> it wins
    gen = Hypothesis(id="gs-weak", rationale="weak by default",
                     when=lambda c: c.card_id == 222, weight=5)
    rival = Hypothesis(id="deck-rival", rationale="deck boost on card 111",
                       when=lambda c: c.card_id == 111, weight=20)
    pilot = Pilot(Strategy(hypotheses=[rival]), deck=[1] * 60,
                  general_strategy=Strategy(hypotheses=[gen]),
                  overrides={"gs-weak": 99})

    # opt0 (card 111): rival 20.  opt1 (card 222): gs-weak overridden 5 -> 99
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

    # weight 40 would pick opt1; overridden to 0, rule can't fire its weight -> opt0 (baseline) wins
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

    assert decision.chosen == pilot.decide(obs)                 # explain agrees w/ decide
    fired_ids = {h.id for h, _ in decision.options[1].fired}    # opt1 = card 222
    assert fired_ids == {"gs", "dk"}                            # both layers visible in trace


@pytest.mark.req("REQ-PILOT-0013")
def test_explain_traces_plan_and_card_and_leaves_untriggered_options_empty():
    gen = Hypothesis(id="gs", rationale="generic", when=lambda c: c.card_id == 222, weight=10)
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=Strategy(hypotheses=[gen]))
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                      current=state(hand=[111, 222]))

    opt0, opt1 = pilot.explain(obs).options

    assert opt0.card_id == 111 and opt0.fired == []            # nothing fires on card 111
    assert opt1.card_id == 222 and opt1.plan == Plan.SETUP     # card -> Plan chain is traced
    assert {h.id for h, _ in opt1.fired} == {"gs"}


@pytest.mark.req("REQ-PILOT-0014")
def test_weakness_doubles_tactical_damage_and_can_flip_the_choice():
    WATER, FIRE = 3, 2
    ATK = 11
    stats = DictCardStatProvider({
        700: CardStat(700, synthetic=True, energyType=WATER),                           # my Water attacker
        800: CardStat(800, synthetic=True, energyType=FIRE, weakness=WATER, hp=160),    # weak to Water
        900: CardStat(900, synthetic=True, energyType=FIRE, weakness=None, hp=160),     # not weak
    }, attacks={ATK: AttackStat(ATK, damage=90)})
    # positional rule lifts non-attack play to 100; attack prints 90
    prefer_play = Hypothesis(id="prefer-play", rationale="", when=lambda c: c.option_type == PLAY, weight=100)
    pilot = Pilot(Strategy(hypotheses=[prefer_play]), deck=[1] * 60, stats=stats)

    def vs(defender):   # opt0 = a play (100 via hypothesis), opt1 = the 90-damage attack
        return make_select([opt(PLAY), attack_opt(ATK)], context=MAIN,
                           current=state(active=poke(700, energy=3), opp_active=poke(defender, hp=160)))

    # Weakness doubling flips ATTACK's tactical value from a 90 chip to a 180 KO.
    assert pilot.explain(vs(800)).options[1].tactical >= KO_SCORE   # 90x2 = 180 >= 160 -> KO recognized
    assert pilot.explain(vs(900)).options[1].tactical == 90         # 90 < 160 -> just a chip
    # Final pick: +100 play is beneficial development, so "attack-last" sequences it ahead of
    # attack either way (KO taken same turn once development exhausted).
    assert pilot.decide(vs(800)) == [0] and pilot.decide(vs(900)) == [0]


@pytest.mark.req("REQ-PILOT-0015")
def test_context_exposes_cardstat_to_hypotheses():
    stats = DictCardStatProvider({222: CardStat(222, synthetic=True, ex=True, megaEx=True)})
    # A General Strategy hypothesis reading engine stats off Context (a 3-prize Mega liability).
    mega_aware = Hypothesis(id="mega-aware", rationale="reads ctx.stat",
                            when=lambda c: bool(c.stat and c.stat.megaEx), weight=50)
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats,
                  general_strategy=Strategy(hypotheses=[mega_aware]))

    # opt0 = card 111 (no stat), opt1 = card 222 (megaEx) -> stat-reading hypothesis lifts opt1
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


@pytest.mark.req("REQ-PILOT-0016")
def test_context_board_exposes_wincon_in_hand_undeployable():
    """`wincon_in_hand_undeployable`: an EVOLUTION win-condition in hand with NO base anywhere is a dead
    card (ep83966336 f44). True only when the payoff sits in hand, is not in play, its Line has a
    pre-evolution, and no pre-evolution is in play OR hand."""
    watch = Hypothesis(id="dead-wincon", rationale="",
                       when=lambda c: c.board.wincon_in_hand_undeployable, weight=5)
    stats = DictCardStatProvider({
        MEGA_STARMIE: CardStat(MEGA_STARMIE, megaEx=True, hp=330, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, synthetic=True, hp=70), 700: CardStat(700, synthetic=True, hp=90)})
    strat = Strategy(hypotheses=[watch], roles={MEGA_STARMIE: ["win_condition"]},
                     lines=[Line(path=[STARYU, MEGA_STARMIE], payoff=MEGA_STARMIE)])
    pilot = Pilot(strat, deck=[1] * 60, stats=stats)
    fired = lambda o: {h.id for h, _ in o.fired}

    # payoff in hand, NO Staryu in play or hand -> dead card
    dead = make_select([opt()], current=state(active=poke(700), hand=[MEGA_STARMIE]))
    assert "dead-wincon" in fired(pilot.explain(dead).options[0])

    # base in PLAY -> deployable, signal silent
    base_play = make_select([opt()], current=state(active=poke(700), bench=[poke(STARYU)],
                                                   hand=[MEGA_STARMIE]))
    assert "dead-wincon" not in fired(pilot.explain(base_play).options[0])

    # base in HAND -> deployable next turn, signal silent
    base_hand = make_select([opt()], current=state(active=poke(700), hand=[MEGA_STARMIE, STARYU]))
    assert "dead-wincon" not in fired(pilot.explain(base_hand).options[0])

    # payoff already IN PLAY -> not a held card, signal silent
    in_play = make_select([opt()], current=state(active=poke(MEGA_STARMIE), hand=[MEGA_STARMIE]))
    assert "dead-wincon" not in fired(pilot.explain(in_play).options[0])


@pytest.mark.req("REQ-PILOT-0016")
def test_wincon_in_hand_undeployable_is_false_for_a_basic_payoff_wincon():
    """A Basic-payoff win-condition (no Line pre-evolution) is directly benchable, so holding it is
    still right — the signal must NOT fire and free a refresh to shuffle it away."""
    watch = Hypothesis(id="dead-wincon", rationale="",
                       when=lambda c: c.board.wincon_in_hand_undeployable, weight=5)
    stats = DictCardStatProvider({666: CardStat(666, synthetic=True, hp=110), 700: CardStat(700, synthetic=True, hp=90)})
    strat = Strategy(hypotheses=[watch], roles={666: ["win_condition"]},
                     lines=[Line(path=[666], payoff=666)])              # Basic payoff, no pre-evo
    pilot = Pilot(strat, deck=[1] * 60, stats=stats)
    fired = lambda o: {h.id for h, _ in o.fired}
    basic = make_select([opt()], current=state(active=poke(700), hand=[666]))
    assert "dead-wincon" not in fired(pilot.explain(basic).options[0])


@pytest.mark.req("REQ-PILOT-0020")
def test_context_exposes_attack_target_energy_and_threat():
    # At a Damage/snipe select, Context must expose per option the attached-energy count of
    # the benched Pokemon it targets — and derived "threat" bool (has Energy) — so a snipe
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
    # New field flips preferred target: a snipe rule lifts the energized bench option (opt1,
    # so only real scoring can choose it). Signal is defined ONLY for attack-target options —
    # at any other select it's None/False, so same rule can't fire and baseline holds.
    snipe = Hypothesis(id="snipe", rationale="prefer the energized threat",
                       when=lambda c: c.target_is_threat, weight=30)
    pilot = Pilot(Strategy(hypotheses=[snipe]), deck=[1] * 60)
    targets = [card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)]
    board = state(active=poke(700), opp_bench=[poke(800, energy=0), poke(900, energy=1)])

    snipe_select = make_select(targets, context=DAMAGE, current=board)
    assert pilot.decide(snipe_select) == [1]          # energized target wins snipe

    off_target = make_select(targets, context=MAIN, current=board)
    off = pilot.explain(off_target).options            # not a Damage select -> no signal -> baseline
    assert [o.fired for o in off] == [[], []]          # the rule cannot fire, so nothing separates
    assert off[0].score == off[1].score                # the two options; which of an exact tie is
                                                       # picked is the canonical tie-break's business
                                                       # (ADR-0103), not this rule's — asserting the
                                                       # index here pinned the old positional one


@pytest.mark.req("REQ-GEN-0022")
def test_context_exposes_target_forward_damage_and_is_fail_closed():
    # At a Damage/snipe select, Context exposes per option the damage the target's evolution
    # line eventually reaches (Evolving Threat signal, ADR-0020). A probe rule reads it.
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
        500: CardStat(500, synthetic=True, name="Sunkern", maxDamage=20),    # dead-end Basic
    })
    probe = Hypothesis(id="evo>=100", rationale="",
                       when=lambda c: (c.target_forward_damage or 0) >= 100, weight=1)
    pilot = Pilot(Strategy(hypotheses=[probe]), deck=[1] * 60, stats=stats)
    fired = lambda o: {h.id for h, _ in o.fired}

    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700), opp_bench=[poke(500), poke(333)]))
    opt0, opt1 = pilot.explain(obs).options
    assert fired(opt0) == set()            # Sunkern: dead-end -> signal None -> silent
    assert fired(opt1) == {"evo>=100"}     # Riolu: line reaches 270 -> exposed

    off = make_select([card_opt(BENCH, 0, player=1)], context=MAIN,
                      current=state(active=poke(700), opp_bench=[poke(333)]))
    assert fired(pilot.explain(off).options[0]) == set()   # not a Damage select -> no signal

    no_stats = Pilot(Strategy(hypotheses=[probe]), deck=[1] * 60)   # fail-closed: no provider
    assert fired(no_stats.explain(obs).options[0]) == set()         # signal None, never crashes


@pytest.mark.req("REQ-PILOT-0017")
def test_tactical_values_a_ko_by_the_defenders_prize_count():
    ATK = 11
    stats = DictCardStatProvider({800: CardStat(800, synthetic=True, megaEx=True), 900: CardStat(900, synthetic=True)},
                                 attacks={ATK: AttackStat(ATK, damage=150)})   # 150 KOs 100 hp
    pilot = Pilot(Strategy(), deck=[1] * 60, stats=stats)

    def ko_score(defender):
        obs = make_select([attack_opt(ATK)], context=MAIN,
                          current=state(active=poke(700), opp_active=poke(defender, hp=100)))
        return pilot.explain(obs).options[0].score

    # both are knockouts, but KOing a 3-prize Mega ex is worth more than a 1-prize Basic
    assert ko_score(800) > ko_score(900)
