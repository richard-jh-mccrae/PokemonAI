"""General Strategy — the deck-agnostic seed hypotheses (see docs/general-strategy.md)."""
import pytest

from common.cards import CardFunctions
from common.strategy.baseline import SNIPE_HYPOTHESES
from common.strategy.general_strategy import GENERAL_STRATEGY
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


@pytest.mark.req("REQ-GEN-0022")
def test_snipe_the_top_threat_hits_the_fragile_preevo_over_the_weakest_deadend():
    # No bench target carries Energy. A fragile pre-evo whose line becomes an attacker (Riolu -> Mega
    # Lucario ex, 270) is the better snipe than a low-HP dead-end basic — even though the dead-end is
    # the weakest. The unified threat RANK ranks Riolu's line top. (The ep81905522 f75 shape.)
    stats = DictCardStatProvider({
        500: CardStat(500, name="Sunkern", maxDamage=20),                 # dead-end basic
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(500, hp=60), poke(333, hp=80)]))
    deadend, evolving = pilot.explain(obs).options
    assert "snipe-the-top-threat" in _fired(evolving)              # Riolu: line reaches 270 (top rank)
    assert "snipe-the-top-threat" not in _fired(deadend)          # Sunkern: dead end, not the top
    assert pilot.decide(obs) == [1]                                # the evolving line is the top threat


@pytest.mark.req("REQ-GEN-0022")
def test_snipe_the_top_threat_tiers_an_energized_body_above_a_bigger_latent_one():
    # Energized = imminent (a strictly higher snipe tier, ADR-0020): an energized 30-damage attacker is
    # sniped before a BIGGER but not-yet-powered latent line (Riolu -> Mega Lucario ex 270). The rank
    # tiers the energized body to the top; snipe-the-threat co-fires as the legible imminence signal.
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
        900: CardStat(900, name="Zubat", maxDamage=30),               # energized, non-evolving
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # opt0: Riolu, no energy (latent threat). opt1: an energized attacker (the imminent, higher tier).
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(333, hp=90), poke(900, energy=1, hp=80)]))
    latent, energized = pilot.explain(obs).options
    assert "snipe-the-top-threat" in _fired(energized)            # energized body is the top tier
    assert "snipe-the-top-threat" not in _fired(latent)
    assert "snipe-the-threat" in _fired(energized)
    assert pilot.decide(obs) == [1]                                # energized (imminent) is sniped first


@pytest.mark.req("REQ-GEN-0022")
def test_only_snipe_rules_fire_at_a_damage_select():
    # The no-double-count gate is whitelist-by-omission: a future DAMAGE hypothesis could silently
    # stack. Guard it — at a DAMAGE select, only the snipe rules may ever fire. Derive the whitelist
    # from the snipe cluster itself so adding a 5th snipe rule can't silently drift this guard.
    allowed = {h.id for h in SNIPE_HYPOTHESES}
    stats = DictCardStatProvider({
        333: CardStat(333, name="Riolu", maxDamage=10),
        678: CardStat(678, name="Mega Lucario ex", maxDamage=270, evolvesFrom="Riolu"),
        900: CardStat(900, name="Zubat", maxDamage=30),
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=DAMAGE,
                      current=state(active=poke(700),
                                    opp_bench=[poke(333, hp=80), poke(900, energy=1, hp=60)]))
    for o in pilot.explain(obs).options:
        assert _fired(o) <= allowed


# NOTE: `build-before-attack` was removed — `_finish_turn_last` ("attack last") now sequences
# development ahead of the turn-ending attack structurally, so a blanket chip penalty is redundant
# (and was suppressing a useful chip below End when no development was available). See
# tests/test_search_discipline.py::test_a_weak_chip_is_taken_when_no_development_is_available.


@pytest.mark.req("REQ-GEN-0023")
def test_protect_ace_spec_tool_stacks_extra_reluctance_off_the_wincon():
    """An ACE SPEC Tool is a one-of, irreplaceable card. Attaching it to a NON-wincon Pokémon draws
    the base `save-tool-for-the-attacker` reluctance PLUS an extra `protect-ace-spec-tool` bump."""
    stats = DictCardStatProvider({1159: CardStat(1159, aceSpec=True),     # an ACE SPEC Tool
                                  700: CardStat(700, hp=120)})            # a non-wincon target
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=CardFunctions({1159: ["tool"]}))
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(999), bench=[poke(700)], hand=[1159]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "save-tool-for-the-attacker" in fired   # the base reluctance (any tool off-wincon)
    assert "protect-ace-spec-tool" in fired         # + the ACE SPEC intensifier (irreplaceable)


@pytest.mark.req("REQ-GEN-0023")
def test_protect_ace_spec_tool_silent_on_a_plain_tool():
    """A non-ACE-SPEC Tool draws only the base reluctance — the intensifier stays off."""
    stats = DictCardStatProvider({1160: CardStat(1160, aceSpec=False), 700: CardStat(700, hp=120)})
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=CardFunctions({1160: ["tool"]}))
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(999), bench=[poke(700)], hand=[1160]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "save-tool-for-the-attacker" in fired
    assert "protect-ace-spec-tool" not in fired     # not ACE SPEC -> no extra bump


# --- deploy-hp-tool-on-breakpoint (general +HP Tool deploy; reads the parsed CardStat.hpBonus) ----
_WATER, _LIGHTNING, _FIRE = 3, 4, 2
_HP_TOOL, _WINCON = 1159, 900


def _hp_tool_pilot(*, hp_bonus=100, opp_type=_FIRE, opp_dmg=400, wincon_role=True):
    """A Pilot whose Active win-condition (HP 330, Weak to Lightning) faces an attacker dealing
    `opp_dmg`, with a +`hp_bonus` Tool in hand. `opp_type` == the wincon's weakness doubles the
    incoming hit (the weakness-aware breakpoint)."""
    stats = DictCardStatProvider({
        _WINCON: CardStat(_WINCON, hp=330, energyType=_WATER, weakness=_LIGHTNING),
        _HP_TOOL: CardStat(_HP_TOOL, hp=0, hpBonus=hp_bonus),
        800: CardStat(800, energyType=opp_type, maxDamage=opp_dmg),
    })
    roles = {_WINCON: ["win_condition"]} if wincon_role else {}
    return Pilot(Strategy(roles=roles), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({_HP_TOOL: ["tool"]}))


def _attach_hp_tool():
    # ATTACH the +HP Tool (hand idx 0) onto my full-HP (330) Active win-condition, facing card 800.
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(_WINCON, hp=330), opp_active=poke(800, hp=200),
                                     hand=[_HP_TOOL]))


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_fires_when_the_boost_dodges_the_incoming_ko():
    """Active wincon is doomed (incoming 400 >= 330) but +100 (-> 430) survives → deploy the Tool now.
    Reads the per-Tool HP off CardStat.hpBonus, so it generalises beyond any one card."""
    pilot = _hp_tool_pilot(opp_dmg=400)
    assert "deploy-hp-tool-on-breakpoint" in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_when_the_boost_would_not_save():
    """Incoming 500 still KOs even at 430 → the Tool is wasted, so don't deploy it."""
    pilot = _hp_tool_pilot(opp_dmg=500)
    assert "deploy-hp-tool-on-breakpoint" not in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_when_not_doomed():
    """Incoming 200 < 330 → not under threat → hold the Tool, don't equip early into removal."""
    pilot = _hp_tool_pilot(opp_dmg=200)
    assert "deploy-hp-tool-on-breakpoint" not in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_for_a_tool_with_no_hp_bonus():
    """A Tool whose text grants no flat HP (hpBonus 0) never triggers the breakpoint rule, even on a
    doomed Active — the rule is specifically about crossing a survival HP line."""
    pilot = _hp_tool_pilot(hp_bonus=0, opp_dmg=400)
    assert "deploy-hp-tool-on-breakpoint" not in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_breakpoint_is_weakness_aware():
    """Generality across WEAKNESS: an attacker printing only 180 is harmless normally, but doubled by
    the wincon's Lightning weakness it's 360 >= 330 (doomed) — and +100 (-> 430) clears 360. The
    rule fires off the weakness-doubled incoming estimate, not the printed number."""
    pilot = _hp_tool_pilot(opp_type=_LIGHTNING, opp_dmg=180)   # 180 x2 (weakness) = 360
    assert "deploy-hp-tool-on-breakpoint" in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_off_the_wincon_where_save_tool_reluctance_rules():
    """Gated to the win-condition Active: with no wincon Role on the target, the deploy rule stays
    silent and the base `save-tool-for-the-attacker` reluctance governs instead (don't burn a
    one-shot Tool on a disposable body)."""
    pilot = _hp_tool_pilot(opp_dmg=400, wincon_role=False)
    fired = _fired(pilot.explain(_attach_hp_tool()).options[0])
    assert "deploy-hp-tool-on-breakpoint" not in fired
    assert "save-tool-for-the-attacker" in fired
