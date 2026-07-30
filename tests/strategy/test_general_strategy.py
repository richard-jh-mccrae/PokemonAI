"""General Strategy — the deck-agnostic seed hypotheses (see docs/general-strategy.md)."""
import pytest

from common.cards import CardFunctions
from common.strategy.baseline import SNIPE_HYPOTHESES
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Ready, Strategy
from pilot_helpers import (
    ACTIVE, ATTACH, ATTACH_FROM, BENCH, DAMAGE, HAND, MAIN, MULLIGAN, NO, PLAY, SETUP_ACTIVE, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


@pytest.mark.req("REQ-GEN-0001")
def test_dig_before_commit_prefers_search_in_setup_and_needs_the_tag_table():
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[111, 222]))
    # opt1 (card 222) is a search card; General Strategy lifts it during SETUP.
    with_tags = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                      functions=CardFunctions({222: ["search"]}))
    assert with_tags.decide(obs) == [1]
    assert "dig-before-commit" in _fired(with_tags.explain(obs).options[1])

    # Counterfactual: no card_functions.json -> no tags -> can't fire -> baseline.
    no_tags = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert no_tags.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0002")
def test_dont_bench_multiprize_penalizes_a_nonwincon_ex_but_exempts_the_wincon():
    stats = DictCardStatProvider({800: CardStat(800, ex=True), 900: CardStat(900, megaEx=True)})
    # 900 = deck's win-condition; 800 = bare 2-prize liability.
    pilot = Pilot(Strategy(roles={900: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[800, 900]))

    liability, wincon = pilot.explain(obs).options
    assert "dont-bench-multiprize" in _fired(liability)       # 800: ex, not win-con -> penalized
    assert "dont-bench-multiprize" not in _fired(wincon)      # 900: Mega ex but win-con -> exempt


@pytest.mark.req("REQ-GEN-0002")
def test_dont_bench_multiprize_also_penalizes_evolving_into_a_nonwincon_ex():
    # adversarial-review fix: evolving a Basic into a non-wincon ex also puts a multi-prizer
    # into play, so gate must cover EVOLVE (option_type 9), not only PLAY.
    _EVOLVE = 9
    stats = DictCardStatProvider({888: CardStat(888, ex=True), 900: CardStat(900, megaEx=True)})
    pilot = Pilot(Strategy(roles={900: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats)
    # EVOLVE whose result (card in hand) is a loose 2-prize ex (888), not the win-condition.
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
    """`attach-energy-last` is no longer a −5 weight (#139, ADR-0069 §7) — it is a decide()-only
    ORDERING deferral in `_finish_turn_last`'s tiers, so an attach keeps its full marginal and simply
    happens AFTER the free development that might reveal a better target. Score-invisible, which is
    what freed the desperation floor from having to out-score that −5."""
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  functions=CardFunctions({222: ["energy_accel"]}))
    obs = make_select([opt(ATTACH), opt(PLAY, area=HAND, index=0)],
                      current=state(hand=[222]))   # state() -> SETUP
    obs["select"]["maxCount"] = 2
    order = pilot.decide(obs)
    assert order == [1, 0], "the free development no longer sequences ahead of the blind attach"


@pytest.mark.req("REQ-GEN-0005")
def test_pre_position_attacker_develops_the_bench_during_race():
    stats = DictCardStatProvider({700: CardStat(700, hp=70)})
    strat = Strategy(lines=[Line(path=[700], payoff=700, ready=Ready(energy=1))])
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # active = payoff w/ 1 energy -> Plan.RACE; benching a Pokémon pre-positions next attacker.
    obs = make_select([opt(PLAY, area=HAND, index=0)],
                      current=state(active=poke(700, energy=1), bench=[poke(800)], hand=[700]))
    assert "pre-position-attacker" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0011")
def test_dont_feed_the_doomed_attaches_to_the_bench_when_the_active_will_die():
    WATER, LIGHTNING = 3, 4
    # Both of my bodies need a real attack for the decider to price: a stat-blind body earns no build
    # on either side of the gate, and the pin would then pass on a coincidence rather than on the rule.
    stats = DictCardStatProvider({
        700: CardStat(700, energyType=WATER, weakness=LIGHTNING, hp=70,    # my Active (Weak to L)
                      maxDamage=60, maxDamageCost=2, minAttackCost=1),
        900: CardStat(900, energyType=LIGHTNING, maxDamage=120),           # opp Active: 120, Lightning
        800: CardStat(800, energyType=WATER, hp=110,                       # my benched successor
                      maxDamage=60, maxDamageCost=2, minAttackCost=1),
    })
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats)
    # ATTACH_FROM (pick Pokémon to attach to): opt0 = my Active (30 HP left, doomed — 120 x2
    # Weakness >> 30), opt1 = my Bench. Don't sink Energy into the dying Active.
    obs = make_select([card_opt(ACTIVE, 0), card_opt(BENCH, 0)], context=ATTACH_FROM,
                      current=state(active=poke(700, hp=30), bench=[poke(800, hp=110)],
                                    opp_active=poke(900, hp=160)))
    # `dont-feed-the-doomed` is DELETED (#139, ADR-0069 §7): the SURVIVAL gate zeroes a doomed body's
    # forward build outright, so a dying Active simply earns nothing to bank.
    rows = {r["i"]: r for r in pilot.explain(obs).attach_working["eq"]}
    assert rows[0]["doomed"] is True and rows[0]["build"] == 0.0
    assert rows[1]["build"] > 0.0
    assert pilot.decide(obs) == [1]   # attach to Bench successor, not doomed Active


@pytest.mark.req("REQ-GEN-0010")
def test_use_acceleration_prioritizes_an_energy_accel_card():
    # Card tagged `energy_accel` multiplies your one manual attach — tempo-positive for any deck.
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

    # `opener` Function Tag in hand -> keep (No), don't redraw and hand opponent a card.
    by_tag = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                   functions=CardFunctions({OPENER: ["opener"]}))
    assert by_tag.decide(mull) == [1]
    assert "keep-a-startable-hand" in _fired(by_tag.explain(mull).options[0])

    # (The `starter` Role was a second accepted signal here until ADR-0079 retired it. It never
    #  changed an outcome: it was only ever declared on Basics, and a hand holding any Basic never
    #  reaches this prompt at all -- `docs/rulebook.txt` L224. The `opener` Tag above is the real one.)

    # neither signal -> ungoverned, defaults to redraw blunder.
    baseline = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert baseline.decide(mull) == [0]


@pytest.mark.req("REQ-GEN-0056")
def test_open_the_declared_starter_prefers_the_decks_ranked_opener_at_setup_active():
    # Re-pointed from the deleted `open-the-accelerator` (ADR-0079). Same requirement — the deck gets
    # the body it wants in the Active Spot — through a declaration instead of an `accel_source` Role,
    # so the deck orders its WHOLE field rather than tripping one rung. Deck-keyed opt-in, and
    # card-name-free: the ids live in Strategy.starter_priority, the trigger reads only the resolved
    # board.top_starter_id. Behaviour on the shipped agents: test_setup_active_placement.py.
    ACCEL, PLAIN = 666, 700
    pilot = Pilot(Strategy(starter_priority=[ACCEL, PLAIN]), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY)
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=SETUP_ACTIVE,
                      current=state(hand=[PLAIN, ACCEL]))
    assert pilot.decide(obs) == [1]                       # rank 1 beats rank 2
    ranked, lower = pilot.explain(obs).options[1], pilot.explain(obs).options[0]
    assert "open-the-declared-starter" in _fired(ranked)
    assert "open-the-declared-starter" not in _fired(lower)   # only the top body PRESENT scores

    # Reversing the DECLARATION reverses the pick; reversing the option order does not.
    flipped = Pilot(Strategy(starter_priority=[PLAIN, ACCEL]), deck=[1] * 60,
                    general_strategy=GENERAL_STRATEGY)
    assert flipped.decide(obs) == [0]

    # An undeclared deck is untouched — nothing fires, nothing scores.
    bare = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY)
    assert all(not _fired(o) for o in bare.explain(obs).options)


@pytest.mark.req("REQ-GEN-0057")
def test_use_acceleration_is_the_one_home_for_advancing_an_accel_piece():
    """`advance-the-accel-pieces` is DELETED (#139, ADR-0069 §7). Its ATTACH half folded into the
    decider's accel-routing term; its PLAY half is `use-acceleration`'s job, and that rung keys on the
    `energy_accel` FUNCTION TAG rather than on an `accel_source` ROLE — one card fact, one home. A deck
    that wants its accelerator advanced tags it (as every shipped deck does); a ROLE alone no longer
    lifts a PLAY, which is the ruled disposition, not an oversight."""
    pilot = Pilot(Strategy(roles={17: ["accel_source"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY,
                  functions=CardFunctions({17: ["energy_accel"]}))
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                      current=state(hand=[111, 17]))
    assert pilot.decide(obs) == [1]
    assert "use-acceleration" in _fired(pilot.explain(obs).options[1])
    assert "advance-the-accel-pieces" not in _fired(pilot.explain(obs).options[0])  # role-keyed


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
    # SETUP, options = [attach Energy, do-nothing play]. Attaching must still win. Both rungs that used
    # to net this out (`power-up-attacker` +15 over `attach-energy-last` −5) are DELETED (#139,
    # ADR-0069 §7): the attach now wins on ORDERING — an unendorsed do-nothing play sequences with the
    # turn-enders while the attach holds its own tier, so a blind attach is never passed over for
    # nothing.
    obs = make_select([opt(ATTACH), opt(PLAY)], current=state())   # state() -> SETUP
    assert pilot.decide(obs) == [0]


# `test_snipe_the_threat_prefers_the_benched_attacker_carrying_energy` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_imminence_subsumes_the_energized_tier_without_a_tier_constant` (test_snipe_relevance.py) —
# an energized body is nearer to attacking, which the `imminence` leg reads off `turns_to_afford`
# as a continuous quantity rather than the retired `_ENERGIZED_SNIPE_TIER` step.

# `test_snipe_the_top_threat_hits_the_fragile_preevo_over_the_weakest_deadend` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_a_pre_evo_carrying_a_wincon_outranks_one_carrying_nothing` (test_snipe_relevance.py) — the
# `forward` leg, ADR-0085 decision 1's own worked pair (Riolu banks toward Mega Lucario ex 270;
# a Solrock's line reaches nothing).

# `test_snipe_the_top_threat_tiers_an_energized_body_above_a_bigger_latent_one` was DELETED by ADR-0085's deletion pass:
# it asserted a snipe TARGET rung that no longer exists. The requirement survives and is
# carried by `test_imminence_subsumes_the_energized_tier_without_a_tier_constant` and
# `test_no_sum_of_positional_legs_can_out_vote_a_single_stronger_one` (test_snipe_relevance.py).

@pytest.mark.req("REQ-GEN-0022")
def test_only_snipe_rules_fire_at_a_damage_select():
    # No-double-count gate is whitelist-by-omission: a future DAMAGE hypothesis could silently
    # stack. Guard it — at a DAMAGE select, only snipe rules may ever fire. Derive whitelist
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
# development ahead of turn-ending attack structurally, so a blanket chip penalty is redundant
# (and was suppressing a useful chip below End when no development was available). See
# tests/test_search_discipline.py::test_a_weak_chip_is_taken_when_no_development_is_available.


@pytest.mark.req("REQ-GEN-0023")
def test_protect_ace_spec_tool_stacks_extra_reluctance_off_the_wincon():
    """An ACE SPEC Tool is a one-of, irreplaceable card. Attaching it to a NON-wincon Pokémon draws
    the base `save-tool-for-the-attacker` reluctance PLUS an extra `protect-ace-spec-tool` bump."""
    stats = DictCardStatProvider({1159: CardStat(1159, aceSpec=True),     # ACE SPEC Tool
                                  700: CardStat(700, hp=120)})            # non-wincon target
    pilot = Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                  functions=CardFunctions({1159: ["tool"]}))
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(999), bench=[poke(700)], hand=[1159]))
    fired = _fired(pilot.explain(obs).options[0])
    assert "save-tool-for-the-attacker" in fired   # base reluctance (any tool off-wincon)
    assert "protect-ace-spec-tool" in fired         # + ACE SPEC intensifier (irreplaceable)


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


# --- deploy-hp-tool (general Tool Doctrine deploy, ADR-0028; reads the parsed CardStat.hpBonus) ----
# PROACTIVE survival-turns deploy (no longer the reactive breakpoint): +HP Tool goes onto the
# Active win-condition whenever the boost banks a survival turn — or as the anti-shuffle default —
# and stands down only on a body doomed even at +boost (with no successor) or off the win-condition.
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
    # ATTACH +HP Tool (hand idx 0) onto my full-HP (330) Active win-condition, facing card 800.
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                       current=state(active=poke(_WINCON, hp=330), opp_active=poke(800, hp=200),
                                     hand=[_HP_TOOL]))


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_fires_when_the_boost_dodges_the_incoming_ko():
    """Active wincon is doomed (incoming 400 >= 330) but +100 (-> 430) survives → deploy the Tool now.
    Reads the per-Tool HP off CardStat.hpBonus, so it generalises beyond any one card."""
    pilot = _hp_tool_pilot(opp_dmg=400)
    assert "deploy-hp-tool" in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_when_the_boost_would_not_save():
    """Incoming 500 still KOs even at 430 → the Tool is wasted, so don't deploy it."""
    pilot = _hp_tool_pilot(opp_dmg=500)
    assert "deploy-hp-tool" not in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_fires_proactively_to_bank_a_survival_turn():
    """ADR-0028 reversal of 'hold for a breakpoint': even when the Active is not under immediate threat
    (incoming 200 < 330), +100 banks an extra survival turn (3 vs 2), so the Tool deploys PROACTIVELY
    onto the Active win-condition — holding it would risk a hand-shuffle burying the irreplaceable card."""
    pilot = _hp_tool_pilot(opp_dmg=200)
    assert "deploy-hp-tool" in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_for_a_tool_with_no_hp_bonus():
    """A Tool whose text grants no flat HP (hpBonus 0) never triggers the breakpoint rule, even on a
    doomed Active — the rule is specifically about crossing a survival HP line."""
    pilot = _hp_tool_pilot(hp_bonus=0, opp_dmg=400)
    assert "deploy-hp-tool" not in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_breakpoint_is_weakness_aware():
    """Generality across WEAKNESS: an attacker printing only 180 is harmless normally, but doubled by
    the wincon's Lightning weakness it's 360 >= 330 (doomed) — and +100 (-> 430) clears 360. The
    rule fires off the weakness-doubled incoming estimate, not the printed number."""
    pilot = _hp_tool_pilot(opp_type=_LIGHTNING, opp_dmg=180)   # 180 x2 (weakness) = 360
    assert "deploy-hp-tool" in _fired(pilot.explain(_attach_hp_tool()).options[0])


@pytest.mark.req("REQ-GEN-0024")
def test_deploy_hp_tool_silent_off_the_wincon_where_save_tool_reluctance_rules():
    """Off the win-condition with NO survival gain: a non-wincon body the boost can't help (330 HP vs
    700 incoming → dies in 1 either way, gain 0) gets no deploy, and the base
    `save-tool-for-the-attacker` reluctance governs instead (don't burn a one-shot Tool on a body that
    gains nothing). A non-wincon WALL that DOES gain a turn earns the Cape — see the Tool Doctrine wall
    tests (ADR-0028 'never say never')."""
    pilot = _hp_tool_pilot(opp_dmg=700, wincon_role=False)
    fired = _fired(pilot.explain(_attach_hp_tool()).options[0])
    assert "deploy-hp-tool" not in fired
    assert "save-tool-for-the-attacker" in fired
