"""Tool static facts whose subject is a RESTRICTED holder, and the one Tool that is a COST (#306).

Ten of the fourteen Pokémon Tools in the pool recovered no `CardStat` field at all, so attaching
them differenced to ~0 — *"this Tool is worth nothing"*, a plausible answer, which is exactly why it
went unnoticed for Hop's Choice Band, the most-played Tool in the tracked meta. Three of the ten were
real gaps rather than the fail-closed doctrine working, and this file is those three plus the
property that must survive them.

**The property most at risk here is the fail-closed doctrine itself** (`card_text`'s module
docstring: match ONLY the clean unconditional phrasing, so a conditional variant parses to 0). Every
widening below therefore ships with a NEGATIVE case proving a genuinely conditional phrasing still
yields nothing — asserted explicitly, per the issue.

Card text quoted from `tools/meta_tracker/cards.json`, the engine's own `all_card_data()` dump,
never from memory (CLAUDE.md). Note the pool mixes apostrophe characters WITHIN one owner family —
`Hop's Silicobra` (288) prints U+2019, `Hop's Phantump` (878) prints ASCII — which is why the
membership oracle normalises both sides rather than comparing raw text.

The three:
  * 1173 Cynthia's Power Weight: "The Cynthia's Pokemon this card is attached to gets +70 HP."
  * 1171 Hop's Choice Band: "Attacks used by the Hop's Pokemon this card is attached to cost {C}
    less and do 30 more damage to your opponent's Active Pokemon (before applying Weakness and
    Resistance)."  — TWO facts, and note there is NO `{ex}` gate on the damage leg.
  * 1166 Gravity Gemstone: "As long as the Pokemon this card is attached to is in the Active Spot,
    the Retreat Cost of both Active Pokemon is {C} more."  — the pool's only Tool whose static
    effect is a COST.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.card_text import (_parse_tool_attack_cost_reduction, _parse_tool_holder_family,
                                       _parse_tool_hp_bonus, _parse_tool_retreat_reduction,
                                       name_in_family, parse_card_damage_boost)
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import ACTIVE, ATTACH, HAND, MAIN, make_select, opt, poke, state

POWER_WEIGHT, CHOICE_BAND, GEMSTONE = 1173, 1171, 1166
CAPE, AIR_BALLOON, MAXIMUM_BELT = 1159, 1174, 1158
GARCHOMP_EX, ZACIAN_EX, PHANTUMP = 381, 299, 878     # real family members, real card ids

# synthetic ids for the consumer boards
FAM_BODY, PLAIN_BODY, OPP = 7100, 7101, 7102
A_HIT = 7200
END = 14


class _Skill:
    """The shape the parsers walk — an object with `.text` (the engine's skill record)."""

    def __init__(self, text):
        self.text = text


class _Card:
    def __init__(self, *texts):
        self.skills = [_Skill(t) for t in texts]


# ---- the membership oracle -----------------------------------------------------------------------

def test_the_owner_family_is_a_name_PREFIX_not_a_substring():
    """`docs/rules.md` §9: the owner prefix IS part of the printed name (`Iono's Tadbulb` !=
    `Tadbulb`), so membership is a prefix test on a name we already hold. A substring test would
    claim `Amulet of Hope` for the `Hop's` family — the exact shape of guess the retreat-grant
    parsers refuse to make."""
    assert name_in_family("Hop’s Zacian ex", "Hop’s")
    assert not name_in_family("Amulet of Hope", "Hop’s")
    assert not name_in_family("Hopeful Charm", "Hop’s")
    assert not name_in_family("Zacian ex", "Hop’s")


def test_the_oracle_normalises_the_two_apostrophes_the_pool_prints():
    """The pool prints BOTH characters inside one family — `Hop's Silicobra` (288) is U+2019 and
    `Hop's Phantump` (878) is ASCII. A raw comparison would answer "no" for half the family, which
    is a silent under-credit, so both sides are normalised."""
    assert name_in_family("Hop's Phantump", "Hop’s")        # ASCII name, typographic gate
    assert name_in_family("Hop’s Zacian ex", "Hop's")       # typographic name, ASCII gate


def test_no_family_reaches_everyone_and_an_unknown_holder_reaches_no_one():
    """The two edges. An UNGATED Tool (Hero's Cape) must behave exactly as it did before this
    machinery existed — hence None means "unconditional", not "nobody". An unreadable holder against
    a real gate is False: fail-CLOSED, never credit a body we cannot identify."""
    assert name_in_family("anything at all", None)
    assert name_in_family(None, None)
    assert not name_in_family(None, "Cynthia's")


# ---- the READ: the three widened facts, each with its negative -----------------------------------

def test_cynthias_power_weight_reads_its_hp_bonus_and_carries_its_condition():
    """The +70 was missed only because the owner qualifier breaks the subject's adjacency. It parses
    now — and the condition parses WITH it, so the fact stays conditional on the holder instead of
    silently becoming an unconditional +70 on every body."""
    card = _Card("The Cynthia’s Pokémon this card is attached to gets +70 HP.")
    assert _parse_tool_hp_bonus(card) == 70
    assert _parse_tool_holder_family(card) == "Cynthia’s"


def test_an_unrestricted_hp_tool_records_no_family_at_all():
    """Hero's Cape is the shape that already worked; it must keep reading +100 with NO gate, so
    every existing consumer of `hpBonus` is byte-identical for it."""
    card = _Card("The Pokémon this card is attached to gets +100 HP.")
    assert _parse_tool_hp_bonus(card) == 100
    assert _parse_tool_holder_family(card) is None


def test_a_RIDER_GATED_hp_bonus_still_parses_to_zero():
    """THE NEGATIVE CASE for the +HP widening. Accepting an owner qualifier must not open the door
    to a boost gated on board state the parser cannot evaluate. The whole-sentence anchor is what
    rejects it: a rider-gated boost never starts its own sentence with "The …"."""
    assert _parse_tool_hp_bonus(_Card(
        "As long as this card's holder is in the Active Spot, the Pokémon this card is attached "
        "to gets +30 HP.")) == 0
    assert _parse_tool_hp_bonus(_Card(
        "If the Pokémon this card is attached to has no damage counters on it, the Pokémon this "
        "card is attached to gets +50 HP.")) == 0


def test_hops_choice_band_reads_BOTH_legs_of_one_sentence():
    """Two different facts in one clause — a cost discount and a damage boost — so two parsers, the
    way Rescue Board's flat and conditional legs are two. The owner gate is parsed ONCE, by
    `_parse_tool_holder_family`, so the amounts and their condition cannot drift apart.

    Note the damage leg has NO `{ex}` restriction (unlike Maximum Belt's), which is why the boost is
    asserted with `vsEx` False rather than being waved through."""
    card = _Card("Attacks used by the Hop’s Pokémon this card is attached to cost {C} less and do "
                 "30 more damage to your opponent’s Active Pokémon (before applying Weakness and "
                 "Resistance).")
    assert _parse_tool_attack_cost_reduction(card) == 1
    assert parse_card_damage_boost(card) == (30, None, False)
    assert _parse_tool_holder_family(card) == "Hop’s"


def test_maximum_belts_boost_is_unchanged_by_the_widening():
    """The Tool boost that already parsed. Same amount, same `{ex}` gate, no family, and no phantom
    cost discount — the optional "cost {C} less and" branch must not fire on a card without it."""
    card = _Card("Attacks used by the Pokémon this card is attached to do 50 more damage to your "
                 "opponent’s Active Pokémon {ex} (before applying Weakness and Resistance).")
    assert parse_card_damage_boost(card) == (50, None, True)
    assert _parse_tool_attack_cost_reduction(card) == 0
    assert _parse_tool_holder_family(card) is None


def test_a_RULE_BOX_GATED_boost_still_parses_to_zero():
    """THE NEGATIVE CASE for the boost widening — Brave Bangle (1175), verbatim. Its +30 depends on
    the holder having no Rule Box, and `CardStat` models `ex`/`megaEx` but not Radiant, so a
    no-Rule-Box test would fail OPEN and over-credit. Deliberately unmodelled: it must read 0, and
    the census report names it as such rather than letting it look like an oversight."""
    card = _Card("If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 30 more damage to your opponent’s Active Pokémon {ex} (before applying "
                 "Weakness and Resistance).")
    assert parse_card_damage_boost(card) == (0, None, False)
    assert _parse_tool_attack_cost_reduction(card) == 0


def test_a_CONDITIONAL_attack_cost_discount_still_parses_to_zero():
    """THE NEGATIVE CASE for the cost-discount parser. A discount that depends on a coin, or on
    anything other than being attached, must not become a flat `attackCostReduction` — an
    over-credited discount is what manufactures a phantom affordable attack."""
    assert _parse_tool_attack_cost_reduction(_Card(
        "Flip a coin. If heads, attacks used by the Pokémon this card is attached to cost {C} "
        "less.")) == 0
    assert _parse_tool_attack_cost_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")) == 0


def test_gravity_gemstone_reads_as_a_NEGATIVE_retreat_reduction():
    """The sign is the whole point. One quantity gets one field — a second `retreatIncrease` field
    is how a sign gets dropped downstream — so a surcharge is a negative reduction."""
    card = _Card("As long as the Pokémon this card is attached to is in the Active Spot, the "
                 "Retreat Cost of both Active Pokémon is {C} more.")
    assert _parse_tool_retreat_reduction(card) == -1


def test_the_flat_discount_tools_keep_their_positive_sign():
    """The regression guard on the sign: Air Balloon and Rescue Board must stay POSITIVE, since the
    three rungs that recognise a retreat-enabler Tool key on `retreatReduction > 0`."""
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less.")) == 2
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of the Pokémon this card is attached to is {C} less. If that Pokémon’s "
        "remaining HP is 30 or less, it has no Retreat Cost.")) == 1


# ---- the same parsers against the REAL engine records --------------------------------------------

def test_the_real_tool_records_parse_through_the_engine_provider():
    """The synthetic texts above prove the REGEXES; this proves they meet the engine's actual
    records — CLAUDE.md's standing rule applied to a parser, since a pattern that matches hand-typed
    prose but misses the real text fails silently and fail-closed, the shape of bug that hides."""
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
    """The BLAST-RADIUS guard, and the assertion that makes the three widenings reviewable.

    A widened regex is only safe if you can say which cards it newly matches. Swept over all 1267
    cards at Issue #306, exactly three field values moved — Cynthia's Power Weight's `hpBonus`, Hop's
    Choice Band's `damageBoost`/`attackCostReduction`, Gravity Gemstone's `retreatReduction` sign.
    Pinning the whole INVENTORY (not a spot check) is what keeps that true: a later widening that
    quietly picks up a fourth card fails here, where the alternative is a silent move in what the
    agent believes about a body.

    `holderNameFamily` deliberately carries two cards with no amount to gate — Lillie's Pearl and
    Team Rocket's Hypnotizer, both REACTIVE Tools whose effect nothing models. A gate with nothing
    behind it is inert, and recording it is honest about which Tools are family-scoped."""
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    cache = stats._cache

    def carriers(field):
        return {cid: getattr(st, field) for cid, st in cache.items() if getattr(st, field)}

    assert carriers("hpBonus") == {1159: 100, 1173: 70}
    assert carriers("retreatReduction") == {1157: 1, 1166: -1, 1174: 2}
    assert carriers("retreatFreeAtHp") == {1157: 30}
    assert carriers("attackCostReduction") == {1171: 1}
    assert carriers("damageBoost") == {1141: 30, 1158: 50, 1171: 30, 1211: 40}
    assert carriers("holderNameFamily") == {1154: "Team Rocket’s", 1171: "Hop’s",
                                            1172: "Lillie’s", 1173: "Cynthia’s"}


def test_the_gate_resolves_against_the_real_family_members():
    """End-to-end on real cards: the Band reaches a real `Hop's` body (both apostrophe spellings)
    and refuses a `Cynthia's` one. This is the assertion that would catch a widened parser whose
    gate silently matched everything."""
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
    """A Pilot holding `tool_stat` in hand, with one family body and one plain body on the board."""
    stats = DictCardStatProvider({
        tool_stat.cardId: tool_stat,
        FAM_BODY: CardStat(FAM_BODY, name="Cynthia's Garchomp ex", hp=100, ex=True, stage="Basic"),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Garchomp", hp=100, stage="Basic"),
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


@pytest.mark.req("REQ-GEN-0048")
def test_the_deploy_picker_refuses_a_body_the_owner_gate_excludes():
    """The survival-turns picker chooses WHERE a +HP Tool goes. Cynthia's Power Weight grants its
    +70 only to a `Cynthia's` body, so a plain body is not a carrier at all — endorsing that attach
    would rank a no-op, which under 1-ply ordering is indistinguishable from a real gain. Read at
    the public seam (`explain(...).fired`), not off the picker's private return."""
    weight = CardStat(POWER_WEIGHT, name="Cynthia's Power Weight", cardType=2, hpBonus=70,
                      holderNameFamily="Cynthia's")
    pilot = _tool_pilot(weight)
    trace = pilot.explain(_board(PLAIN_BODY, POWER_WEIGHT)).options[0]
    assert "deploy-hp-tool" not in _fired(trace)


@pytest.mark.req("REQ-GEN-0048")
def test_the_deploy_picker_still_equips_a_body_inside_the_family():
    """The other half of the same gate: the Tool is not inert, it is TARGETED. On a `Cynthia's`
    Active the deploy rung fires — so widening the parser bought a decision rather than a field."""
    weight = CardStat(POWER_WEIGHT, name="Cynthia's Power Weight", cardType=2, hpBonus=70,
                      holderNameFamily="Cynthia's")
    pilot = _tool_pilot(weight)
    trace = pilot.explain(_board(FAM_BODY, POWER_WEIGHT)).options[0]
    assert "deploy-hp-tool" in _fired(trace)
    assert trace.score > 0


def test_an_ungated_hp_tool_is_unaffected_by_the_gate_machinery():
    """The no-regression assertion: Hero's Cape reaches the same plain body the gated Tool refuses,
    so every shipped +HP decision is untouched by this issue."""
    cape = CardStat(CAPE, name="Hero's Cape", cardType=2, aceSpec=True, hpBonus=100)
    pilot = _tool_pilot(cape)
    trace = pilot.explain(_board(PLAIN_BODY, CAPE)).options[0]
    assert "deploy-hp-tool" in _fired(trace)


def _boost_pilot():
    """A Pilot whose Active can be either family or plain, holding Hop's Choice Band, against an
    opponent exactly one boost short of a KO."""
    stats = DictCardStatProvider({
        CHOICE_BAND: CardStat(CHOICE_BAND, name="Hop's Choice Band", cardType=2, damageBoost=30,
                              attackCostReduction=1, holderNameFamily="Hop's"),
        FAM_BODY: CardStat(FAM_BODY, name="Hop's Zacian ex", hp=230, ex=True, stage="Basic",
                           maxDamage=90, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Zacian ex", hp=230, ex=True, stage="Basic",
                             maxDamage=90, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        OPP: CardStat(OPP, name="Opponent", hp=110, stage="Basic"),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=90, cost=1, damageMax=90)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CHOICE_BAND: ["tool"]}))


def _boost_obs(active_id):
    return make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0), opt(END)],
                       context=MAIN,
                       current=state(active=poke(active_id, hp=230, energy=1), hand=[CHOICE_BAND],
                                     opp_active=poke(OPP, hp=110, energy=1), turn=4, prizes=6))


def test_the_boost_lethal_rung_honours_the_owner_gate():
    """90 damage is 20 short of a 110-HP defender and the Band's +30 crosses it — but ONLY on a
    `Hop's` body. On a plain Zacian ex the same attach must not claim a KO_SCORE-class lethal, which
    is the whole reason the amount had to arrive carrying its condition."""
    pilot = _boost_pilot()
    fam = pilot.explain(_boost_obs(FAM_BODY)).options[0]
    plain = pilot.explain(_boost_obs(PLAIN_BODY)).options[0]
    # KO_SCORE is 1000; the tactical's own efficiency term and the ordinary tool rungs shave a few
    # points off it, so the assertion is on the CLASS (a lethal claim vs an ordinary attach), which
    # is the thing the gate decides — not on an exact total that the surrounding weights own.
    assert fam.score > 900, f"the Hop's body's boost must cross the KO, scored {fam.score:+.1f}"
    assert plain.score < 100, f"a plain body must claim no lethal, scored {plain.score:+.1f}"


def test_the_attached_boost_is_gated_at_the_damage_context_too():
    """The second boost supplier: a Tool ALREADY attached is visible board state, summed straight
    off the holder in `state_model`. It reads the same gate, so the two suppliers cannot disagree
    about whether a Band on a plain body is worth 30."""
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


# ---- the SIGN, on a live board -------------------------------------------------------------------

def _gem_pilot():
    stats = DictCardStatProvider({
        GEMSTONE: CardStat(GEMSTONE, name="Gravity Gemstone", cardType=2, retreatReduction=-1),
        AIR_BALLOON: CardStat(AIR_BALLOON, name="Air Balloon", cardType=2, retreatReduction=2),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Walker", hp=120, stage="Basic", retreatCost=2,
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
    """`_effective_retreat_cost` subtracts a SIGNED delta, so Gravity Gemstone raises a printed 2 to
    3 where Air Balloon drops it to 0. A consumer that assumed non-negative would have read the
    Gemstone as free retreat — the opposite of the card."""
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
    """The soundness fix the sign forced. `_retreat_shortfall` sizes a KO_SCORE-class claim — "does
    this Tool free the retreat?" — and read the PRINTED cost, ignoring what is already attached. That
    merely OVER-stated the need while every Tool was a discount (fail-closed, so it survived); a
    surcharge makes it UNDER-state, which would accept a Tool that does not in fact free the retreat
    and score the phantom at KO_SCORE. It now reads the effective cost, so the two agree."""
    p = _gem_pilot()
    bare = poke(PLAIN_BODY, energy=1, hp=120)               # printed 2, 1 attached -> short by 1
    gemmed = poke(PLAIN_BODY, energy=1, hp=120)             # effective 3, 1 attached -> short by 2
    gemmed["tools"] = [{"id": GEMSTONE}]
    assert p._retreat_shortfall(bare) == 1
    assert p._retreat_shortfall(gemmed) == 2
    assert not p._can_retreat(gemmed)                       # and the two readers agree on the body
