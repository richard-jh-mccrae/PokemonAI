"""Tool static facts whose subject is a RESTRICTED holder, and the one Tool that is a COST.

Four cards: 1173 Cynthia's Power Weight and 1171 Hop's Choice Band (owner-name gates), 1175 Brave
Bangle (a no-Rule-Box gate, Issue #345) and 1166 Gravity Gemstone (a surcharge, so a NEGATIVE
reduction). The property most at risk is `card_text`'s fail-closed doctrine — match only the clean
unconditional phrasing — so every widening ships with a NEGATIVE case beside it.

Card text is quoted from `tools/meta_tracker/cards.json`, never from memory (CLAUDE.md). The pool
mixes apostrophe characters WITHIN one owner family, which is why the oracle normalises both sides.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.card_text import (_BOOST_TOOL_NO_RULE_BOX_RE, _HOLDER_NO_RULE_BOX_RE,
                                       _parse_tool_attack_cost_reduction, _parse_tool_holder_family,
                                       _parse_tool_holder_no_rule_box, _parse_tool_hp_bonus,
                                       _parse_tool_retreat_reduction, name_in_family,
                                       parse_card_damage_boost)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import ACTIVE, ATTACH, HAND, MAIN, make_select, opt, poke, state

POWER_WEIGHT, CHOICE_BAND, GEMSTONE = 1173, 1171, 1166
CAPE, AIR_BALLOON, MAXIMUM_BELT = 1159, 1174, 1158
GARCHOMP_EX, ZACIAN_EX, PHANTUMP = 381, 299, 878     # real family members, real card ids
#: Four `slowking` bodies straddling Brave Bangle's gate. Mega Kangaskhan ex is `megaEx` and NOT
#: `ex` — the case a gate written as `stat.ex` alone waves through.
BRAVE_BANGLE, SLOWKING, METAGROSS, LATIAS_EX, MEGA_KANGASKHAN = 1175, 163, 276, 184, 756

# ids for the consumer boards
FAM_BODY, PLAIN_BODY, OPP = 7100, 7101, 7102
A_HIT = 7200
END = 14


class _Skill:
    """The shape the parsers walk — an object with `.text`."""

    def __init__(self, text):
        self.text = text


class _Card:
    def __init__(self, *texts):
        self.skills = [_Skill(t) for t in texts]


# ---- the membership oracle -----------------------------------------------------------------------

def test_the_owner_family_is_a_name_PREFIX_not_a_substring():
    """`docs/rules.md` §9: the owner prefix IS part of the printed name, so membership is a PREFIX
    test. A substring test would claim `Amulet of Hope` for the `Hop's` family."""
    assert name_in_family("Hop’s Zacian ex", "Hop’s")
    assert not name_in_family("Amulet of Hope", "Hop’s")
    assert not name_in_family("Hopeful Charm", "Hop’s")
    assert not name_in_family("Zacian ex", "Hop’s")


def test_the_oracle_normalises_the_two_apostrophes_the_pool_prints():
    """The pool prints BOTH characters inside one family, so a raw comparison silently under-credits
    half of it."""
    assert name_in_family("Hop's Phantump", "Hop’s")        # ASCII name, typographic gate
    assert name_in_family("Hop’s Zacian ex", "Hop's")       # typographic name, ASCII gate


def test_no_family_reaches_everyone_and_an_unknown_holder_reaches_no_one():
    """None means "unconditional", not "nobody"; an unreadable holder against a real gate is False."""
    assert name_in_family("anything at all", None)
    assert name_in_family(None, None)
    assert not name_in_family(None, "Cynthia's")


# ---- the READ: the three widened facts, each with its negative -----------------------------------

def test_cynthias_power_weight_reads_its_hp_bonus_and_carries_its_condition():
    """The condition parses WITH the amount, so the +70 cannot become unconditional on every body."""
    card = _Card("The Cynthia’s Pokémon this card is attached to gets +70 HP.")
    assert _parse_tool_hp_bonus(card) == 70
    assert _parse_tool_holder_family(card) == "Cynthia’s"


def test_an_unrestricted_hp_tool_records_no_family_at_all():
    """+100 with NO gate, so every existing consumer of `hpBonus` is byte-identical for it."""
    card = _Card("The Pokémon this card is attached to gets +100 HP.")
    assert _parse_tool_hp_bonus(card) == 100
    assert _parse_tool_holder_family(card) is None


def test_a_RIDER_GATED_hp_bonus_still_parses_to_zero():
    """The whole-sentence anchor is what rejects these: a rider-gated boost never starts its own
    sentence with "The …"."""
    assert _parse_tool_hp_bonus(_Card(
        "As long as this card's holder is in the Active Spot, the Pokémon this card is attached "
        "to gets +30 HP.")) == 0
    assert _parse_tool_hp_bonus(_Card(
        "If the Pokémon this card is attached to has no damage counters on it, the Pokémon this "
        "card is attached to gets +50 HP.")) == 0


def test_hops_choice_band_reads_BOTH_legs_of_one_sentence():
    """Two facts in one clause, so two parsers; the owner gate is parsed ONCE so amounts and
    condition cannot drift. The damage leg carries NO `{ex}` restriction, hence `vsEx` False."""
    card = _Card("Attacks used by the Hop’s Pokémon this card is attached to cost {C} less and do "
                 "30 more damage to your opponent’s Active Pokémon (before applying Weakness and "
                 "Resistance).")
    assert _parse_tool_attack_cost_reduction(card) == 1
    assert parse_card_damage_boost(card) == (30, None, False)
    assert _parse_tool_holder_family(card) == "Hop’s"


def test_maximum_belts_boost_is_unchanged_by_the_widening():
    """The optional "cost {C} less and" branch must not fire on a card without it."""
    card = _Card("Attacks used by the Pokémon this card is attached to do 50 more damage to your "
                 "opponent’s Active Pokémon {ex} (before applying Weakness and Resistance).")
    assert parse_card_damage_boost(card) == (50, None, True)
    assert _parse_tool_attack_cost_reduction(card) == 0
    assert _parse_tool_holder_family(card) is None


def test_brave_bangles_boost_reads_its_amount_and_carries_its_RULE_BOX_gate():
    """The SECOND holder gate (Issue #345). Same doctrine as the owner family: the gate is not a
    condition the parser refuses, it is one it CARRIES, read from ONE shared-prefix pattern."""
    card = _Card("If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 30 more damage to your opponent’s Active Pokémon {ex} (before applying "
                 "Weakness and Resistance). (Pokémon {ex}, Pokémon {V}, etc. have Rule Boxes.)")
    assert parse_card_damage_boost(card) == (30, None, True)
    assert _parse_tool_holder_no_rule_box(card) is True
    assert _parse_tool_holder_family(card) is None      # a Rule Box is not an owner NAME
    assert _parse_tool_attack_cost_reduction(card) == 0


def test_the_amount_and_the_RULE_BOX_gate_cannot_be_read_apart():
    """Asserted on the PATTERNS, not sampled: round-tripping texts through both parsers proves
    nothing, because every such text satisfies both legs by construction."""
    assert _BOOST_TOOL_NO_RULE_BOX_RE.pattern.startswith(_HOLDER_NO_RULE_BOX_RE.pattern), (
        "the boost pattern must BEGIN with the gate pattern, or an amount can outrun its condition")
    # …and the prefix does real work on real shapes, not merely textual ones
    for text in ("If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 30 more damage to your opponent’s Active Pokémon {ex}.",
                 "If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 60 more damage to your opponent’s Active Pokémon."):
        card = _Card(text)
        assert parse_card_damage_boost(card)[0] > 0
        assert _parse_tool_holder_no_rule_box(card) is True


def test_an_UNEVALUABLE_conditional_boost_still_parses_to_zero():
    """A coin-gated boost is deliberately NOT asserted: `_BOOST_TOOL_RE` has no coin guard and no
    card prints that shape, so asserting a zero would record a guard that does not exist."""
    assert parse_card_damage_boost(_Card(
        "If the Pokémon this card is attached to has a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) == (0, None, False)
    assert parse_card_damage_boost(_Card(
        "If your opponent’s Active Pokémon doesn’t have a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) == (0, None, False)
    # …and the gate never fires on either, nor on a card that merely MENTIONS a Rule Box, so no
    # field records a condition with no amount behind it.
    assert _parse_tool_holder_no_rule_box(_Card(
        "If the Pokémon this card is attached to has a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) is False
    assert _parse_tool_holder_no_rule_box(_Card(
        "Search your deck for a Pokémon that doesn’t have a Rule Box, reveal it, and put it into "
        "your hand.")) is False


def test_a_CONDITIONAL_attack_cost_discount_still_parses_to_zero():
    """An over-credited discount manufactures a phantom affordable attack."""
    assert _parse_tool_attack_cost_reduction(_Card(
        "Flip a coin. If heads, attacks used by the Pokémon this card is attached to cost {C} "
        "less.")) == 0
    assert _parse_tool_attack_cost_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")) == 0


def test_gravity_gemstone_reads_as_a_NEGATIVE_retreat_reduction():
    """One quantity, one field: a second `retreatIncrease` field is how a sign gets dropped."""
    card = _Card("As long as the Pokémon this card is attached to is in the Active Spot, the "
                 "Retreat Cost of both Active Pokémon is {C} more.")
    assert _parse_tool_retreat_reduction(card) == -1


def test_the_surcharge_parser_declines_a_clause_it_cannot_evaluate():
    """The fail direction INVERTS for a cost: under-crediting a bonus is safe, missing a PENALTY is
    not. So this parser deliberately over-matches, and declines only a SUBJECT it cannot resolve."""
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of your opponent's Active Pokémon is {C} more.")) == 0
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of each Pokémon that has a Tool attached is {C}{C} more.")) == 0
    assert _parse_tool_retreat_reduction(_Card(
        "Flip a coin. If heads, the Retreat Cost of both Active Pokémon is {C} more.")) == -1
    # ^ the ONE deliberate over-match: a maybe-cost is priced as a cost.


def test_the_flat_discount_tools_keep_their_positive_sign():
    """The rungs that recognise a retreat-enabler Tool key on `retreatReduction > 0`."""
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")) == 2
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C} less. If that Pokémon’s "
        "remaining HP is 30 or less, it has no Retreat Cost.")) == 1


# ---- the same parsers against the REAL engine records --------------------------------------------

def test_the_real_tool_records_parse_through_the_engine_provider():
    """A pattern that matches hand-typed prose but misses the engine's real text fails SILENTLY."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    weight, band, gem = (stats.get(POWER_WEIGHT), stats.get(CHOICE_BAND), stats.get(GEMSTONE))
    assert (weight.hpBonus, weight.holderNameFamily) == (70, "Cynthia’s")
    assert (band.damageBoost, band.damageBoostVsEx, band.attackCostReduction) == (30, False, 1)
    assert band.holderNameFamily == "Hop’s"
    assert gem.retreatReduction == -1
    # …and the Tools that already parsed are untouched, gate included.
    assert (stats.get(CAPE).hpBonus, stats.get(CAPE).holderNameFamily) == (100, None)
    assert (stats.get(AIR_BALLOON).retreatReduction, stats.get(MAXIMUM_BELT).damageBoost) == (2, 50)


def test_the_widening_moved_exactly_three_facts_across_the_whole_pool():
    """The BLAST-RADIUS guard: a widened regex is only safe if you can say which cards it newly
    matches, so the whole INVENTORY is pinned rather than spot-checked."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    cache = stats._cache

    def carriers(field):
        return {cid: getattr(st, field) for cid, st in cache.items() if getattr(st, field)}

    assert carriers("hpBonus") == {1159: 100, 1173: 70}
    assert carriers("retreatReduction") == {1157: 1, 1166: -1, 1174: 2}
    assert carriers("retreatFreeAtHp") == {1157: 30}
    # `retreatFreeGrant` is in the blast radius even with an untouched regex: folding newlines in
    # `_skill_texts` widened EVERY card-level parser's input.
    assert carriers("retreatFreeGrant") == {170: "metal_attached", 184: "basic"}
    assert carriers("attackCostReduction") == {1171: 1}
    assert carriers("damageBoost") == {1141: 30, 1158: 50, 1171: 30, 1175: 30, 1211: 40}
    # 1154 and 1172 carry a family gate with NO amount behind it: both are REACTIVE Tools nothing
    # models, so the gate is inert rather than wrong.
    assert carriers("holderNameFamily") == {1154: "Team Rocket’s", 1171: "Hop’s",
                                            1172: "Lillie’s", 1173: "Cynthia’s"}
    assert carriers("holderNoRuleBox") == {1175: True}


def test_the_rule_box_predicate_is_a_POOL_SWEEP_not_a_hand_listed_set():
    """Not "ex is the definition" but "over THESE cards the two sets coincide" — `docs/rulebook.txt`
    names Radiant, V and V-UNION too, so the day the pool gains one this fails and the gate is redecided."""
    import re
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    marker = re.compile(r"\b(?:ex|EX|V|VMAX|VSTAR|GX)\b|EX$|\bV-UNION\b|\bRadiant\b")
    bodies = {cid: st for cid, st in stats._cache.items() if st.is_pokemon}
    assert len(bodies) == 1061                       # the sweep really walked the pool
    by_name = {cid for cid, st in bodies.items() if marker.search(st.name or "")}
    by_flag = {cid for cid, st in bodies.items() if st.is_ex_body}
    assert by_flag, "positive control: the flag read must find SOMETHING"
    assert by_name == by_flag, (
        "a Rule-Box category the engine flags do not model: "
        f"{sorted(by_name ^ by_flag)}")


def test_the_rule_box_gate_refuses_every_ex_body_and_fails_closed_on_an_unknown_one():
    """Mega Kangaskhan ex is `megaEx` and NOT `ex`, so a gate written `stat.ex` waves it through;
    `is_ex_body` is `ex or megaEx` for exactly that reason (`docs/rulebook.txt` L337)."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    bangle = stats.get(BRAVE_BANGLE)
    assert bangle.applies_to_holder(stats.get(SLOWKING))          # no Rule Box — the boost lands
    assert bangle.applies_to_holder(stats.get(METAGROSS))
    assert not bangle.applies_to_holder(stats.get(LATIAS_EX))     # ex
    assert not bangle.applies_to_holder(stats.get(MEGA_KANGASKHAN))  # megaEx, not ex
    assert not bangle.applies_to_holder(None)                     # unknown holder — fail-CLOSED
    # …and the gate is the Bangle's alone: an ungated Tool still reaches an ex body unchanged.
    assert stats.get(MAXIMUM_BELT).applies_to_holder(stats.get(LATIAS_EX))


def test_the_gate_resolves_against_the_real_family_members():
    """Catches a widened parser whose gate silently matched everything."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    band = stats.get(CHOICE_BAND)
    assert band.applies_to_holder(stats.get(ZACIAN_EX))       # Hop's Zacian ex (U+2019)
    assert band.applies_to_holder(stats.get(PHANTUMP))        # Hop's Phantump  (ASCII)
    assert not band.applies_to_holder(stats.get(GARCHOMP_EX))  # Cynthia's Garchomp ex
    assert not band.applies_to_holder(None)                    # unknown holder — fail-closed
    assert stats.get(CAPE).applies_to_holder(stats.get(GARCHOMP_EX))   # ungated reaches everyone


# ---- the CONSUMERS: a gated amount must not be spent on a body it cannot reach -------------------

def _tool_pilot(tool_stat):
    """`tool_stat` in hand, one family body and one plain body on the board."""
    stats = DictCardStatProvider({
        tool_stat.cardId: tool_stat,
        FAM_BODY: CardStat(FAM_BODY, name="Cynthia's Garchomp ex", hp=100, ex=True, stage="basic"),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Garchomp", hp=100, stage="basic"),
        OPP: CardStat(OPP, name="Opponent", hp=300, maxDamage=60, maxDamageCost=1,
                      minAttackCost=1, attacks=(A_HIT,)),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=60, cost=1)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({tool_stat.cardId: ["tool"]}))


def _board(active_id, tool_id):
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0), opt(END)],
                       context=MAIN,
                       current=state(active=poke(active_id, hp=100, energy=1), hand=[tool_id],
                                     opp_active=poke(OPP, hp=300, energy=1), turn=4))


def _fired(trace):
    return {h.id for h, _ in trace.fired}


# RETIRED (Issue #386): `doctrines/doctrine_tool.py` and its rung tests. A Tool that buys a survival
# turn is now `survival` on the composed end board (`deploy_value`, ADR-0086).
def _boost_pilot():
    """Hop's Choice Band in hand; the opponent is exactly one boost short of a KO."""
    stats = DictCardStatProvider({
        CHOICE_BAND: CardStat(CHOICE_BAND, synthetic=True, name="Hop's Choice Band", cardType=2, damageBoost=30,
                              attackCostReduction=1, holderNameFamily="Hop's"),
        FAM_BODY: CardStat(FAM_BODY, name="Hop's Zacian ex", hp=230, ex=True, stage="basic",
                           maxDamage=90, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Zacian ex", hp=230, ex=True, stage="basic",
                             maxDamage=90, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        OPP: CardStat(OPP, name="Opponent", hp=110, stage="basic"),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=90, cost=1, damageMax=90)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CHOICE_BAND: ["tool"]}))


def _boost_obs(active_id):
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0), opt(END)],
                       context=MAIN,
                       current=state(active=poke(active_id, hp=230, energy=1), hand=[CHOICE_BAND],
                                     opp_active=poke(OPP, hp=110, energy=1), turn=4, prizes=6))


def test_the_boost_lethal_rung_honours_the_owner_gate():
    """90 is 20 short of a 110-HP defender and the Band's +30 crosses it — but ONLY on a `Hop's` body."""
    pilot = _boost_pilot()
    fam = pilot.explain(_boost_obs(FAM_BODY)).options[0]
    plain = pilot.explain(_boost_obs(PLAIN_BODY)).options[0]
    # asserted on the CLASS (lethal claim vs ordinary attach), since KO_SCORE 1000 is shaved by
    # the tactical's efficiency term and the surrounding weights own that total
    assert fam.score > 900, f"the Hop's body's boost must cross the KO, scored {fam.score:+.1f}"
    assert plain.score < 100, f"a plain body must claim no lethal, scored {plain.score:+.1f}"


def test_the_attached_boost_is_gated_at_the_damage_context_too():
    """The second boost supplier reads the same gate, so the two cannot disagree about a Band on a
    plain body."""
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    pilot = _boost_pilot()

    def boosts(active_id):
        body = poke(active_id, hp=230, energy=1)
        body["tools"] = [{"id": CHOICE_BAND}]
        obs = make_select([opt(END)], context=MAIN,
                          current=state(active=body, opp_active=poke(OPP, hp=110), turn=4))
        combat = CombatMath(pilot.stats, functions=None, transients=None)
        return StateModel.build(obs, combat=combat).mine.damage_boosts

    assert boosts(FAM_BODY) == ((30, None, False),)
    assert boosts(PLAIN_BODY) == ()


def _bangle_pilot():
    """One Rule-Box holder and one without, against an `{ex}` at 150 HP — Slowking's Super Psy Bolt
    (120) is 30 short, which is exactly the Bangle."""
    stats = DictCardStatProvider({
        BRAVE_BANGLE: CardStat(BRAVE_BANGLE, name="Brave Bangle", cardType=2, damageBoost=30,
                               damageBoostVsEx=True, holderNoRuleBox=True),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Slowking", hp=120, stage="stage1",
                             maxDamage=120, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        FAM_BODY: CardStat(FAM_BODY, name="Mega Kangaskhan ex", hp=300, megaEx=True, stage="basic",
                           maxDamage=120, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        OPP: CardStat(OPP, name="Opponent ex", hp=150, ex=True, stage="basic"),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=120, cost=1, damageMax=120)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({BRAVE_BANGLE: ["tool"]}))


def test_the_rule_box_gate_reaches_the_damage_context_consumer():
    """`_SideBase.damage_boosts` asks the Tool's own `applies_to_holder`, so the gate arrives without
    that site learning a new condition."""
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    pilot = _bangle_pilot()

    def boosts(active_id):
        body = poke(active_id, hp=300, energy=1)
        body["tools"] = [{"id": BRAVE_BANGLE}]
        obs = make_select([opt(END)], context=MAIN,
                          current=state(active=body, opp_active=poke(OPP, hp=150), turn=4))
        combat = CombatMath(pilot.stats, functions=None, transients=None)
        return StateModel.build(obs, combat=combat).mine.damage_boosts

    assert boosts(PLAIN_BODY) == ((30, None, True),)
    assert boosts(FAM_BODY) == ()


def test_the_rule_box_gate_reaches_the_boost_lethal_consumer():
    """`Pilot._boost_lethal_tactical` sizes a KO_SCORE-class claim off the same amount, so a lethal
    claimed on a boost the card does not grant is the worst error this gate prevents."""
    pilot = _bangle_pilot()

    def score(active_id):
        obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0),
                           opt(END)], context=MAIN,
                          current=state(active=poke(active_id, hp=300, energy=1),
                                        hand=[BRAVE_BANGLE], opp_active=poke(OPP, hp=150, energy=1),
                                        turn=4, prizes=6))
        return pilot.explain(obs).options[0].score

    assert score(PLAIN_BODY) > 900, "the Rule-Box-less holder's boost must cross the KO"
    assert score(FAM_BODY) < 100, "a Rule-Box holder must claim no lethal"


# ---- the SIGN, on a live board -------------------------------------------------------------------

def _gem_pilot():
    stats = DictCardStatProvider({
        GEMSTONE: CardStat(GEMSTONE, synthetic=True, name='Gravity Gemstone', cardType=2, retreatReduction=-1),
        AIR_BALLOON: CardStat(AIR_BALLOON, synthetic=True, name='Air Balloon', cardType=2, retreatReduction=2),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Walker", hp=120, stage="basic", retreatCost=2,
                             maxDamage=60, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        OPP: CardStat(OPP, name="Opponent", hp=300),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=60, cost=1)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({}))


def _gem_obs(active):
    return make_select([opt(END)], context=MAIN,
                       current=state(active=active, bench=[poke(PLAIN_BODY, hp=120)],
                                     opp_active=poke(OPP, hp=300), turn=5))


def test_a_surcharge_tool_makes_the_retreat_DEARER_not_cheaper():
    """`_effective_retreat_cost` subtracts a SIGNED delta; assuming non-negative reads the Gemstone
    as FREE retreat, the opposite of the card."""
    p = _gem_pilot()
    bare = poke(PLAIN_BODY, energy=3, hp=120)
    gemmed = poke(PLAIN_BODY, energy=3, hp=120)
    gemmed["tools"] = [{"id": GEMSTONE}]
    ballooned = poke(PLAIN_BODY, energy=3, hp=120)
    ballooned["tools"] = [{"id": AIR_BALLOON}]
    assert p._effective_retreat_cost(_gem_obs(bare), bare) == 2
    assert p._effective_retreat_cost(_gem_obs(gemmed), gemmed) == 3
    assert p._effective_retreat_cost(_gem_obs(ballooned), ballooned) == 0


def test_the_retreat_shortfall_counts_a_surcharge_it_used_to_ignore():
    """`_retreat_shortfall` sizes a KO_SCORE-class claim, so it must read the EFFECTIVE cost: on the
    printed one a surcharge UNDER-states the need and scores a phantom free retreat."""
    p = _gem_pilot()
    bare = poke(PLAIN_BODY, energy=1, hp=120)               # printed 2, 1 attached -> short by 1
    gemmed = poke(PLAIN_BODY, energy=1, hp=120)             # effective 3, 1 attached -> short by 2
    gemmed["tools"] = [{"id": GEMSTONE}]
    assert p._retreat_shortfall(bare) == 1
    assert p._retreat_shortfall(gemmed) == 2
    assert not p._can_retreat(gemmed)                       # and the two readers agree on the body
