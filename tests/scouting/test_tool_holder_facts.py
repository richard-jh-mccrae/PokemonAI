"""Tool static facts whose subject is a RESTRICTED holder, and the one Tool that is a COST.

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

**Issue #345 adds a fourth, and it was previously this file's NEGATIVE case**, refused with a
reason that has not survived re-measurement:

  * 1175 Brave Bangle: "If the Pokemon this card is attached to doesn't have a Rule Box, the attacks
    it uses do 30 more damage to your opponent's Active Pokemon {ex} (before applying Weakness and
    Resistance)."  — a SECOND holder gate, on a property of the holder's own rules text rather than
    of its name, so it cannot ride `holderNameFamily`.

The old refusal read *"`CardStat` models `ex`/`megaEx` but not Radiant, so a no-Rule-Box test would
fail OPEN and over-credit."* Swept over the pool that is simply not true here: there is no Radiant,
V, VSTAR or V-UNION body among the 1061 — `test_the_rule_box_predicate_is_a_POOL_SWEEP…` below is
that sweep, and it is written to FAIL the day one arrives. Two shipped call sites already read the
predicate this way (`fetch_closure._pokemon_body_matches` for Poké Pad's `no_rule_box`, and
`cgpy.chain._card_matches` for `noRuleBox` — the engine twin's own answer), so the refusal was also
inconsistent with the rest of the tree.
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
#: Issue #345's cast, all real ids — Brave Bangle and four `slowking` bodies that straddle its gate:
#: Slowking (Stage 1, no Rule Box), Metagross (Stage 2, no Rule Box), Latias ex (`ex`) and Mega
#: Kangaskhan ex (`megaEx`, and NOT `ex` — the case a gate written as `stat.ex` alone waves through).
BRAVE_BANGLE, SLOWKING, METAGROSS, LATIAS_EX, MEGA_KANGASKHAN = 1175, 163, 276, 184, 756

# ids for the consumer boards
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


def test_brave_bangles_boost_reads_its_amount_and_carries_its_RULE_BOX_gate():
    """Brave Bangle (1175), verbatim — the SECOND holder gate (Issue #345).

    Until now this card was the file's negative case, refused on the stated ground that *"`CardStat`
    models `ex`/`megaEx` but not Radiant, so a no-Rule-Box test would fail OPEN"*. That ground does
    not survive the pool sweep below (`test_the_rule_box_predicate_is_a_POOL_SWEEP…`): over these
    1061 bodies there is no Radiant, V, VSTAR or V-UNION card at all, so the predicate is EXACT, not
    fail-open — and the repo already ships it twice under that reading, at
    `fetch_closure._pokemon_body_matches` (Poké Pad's `no_rule_box`) and `cgpy.chain._card_matches`
    (`noRuleBox`), which is the engine twin's own answer.

    Same doctrine as the owner family: the gate is not a condition the parser must refuse, it is one
    it CARRIES. The amount and its gate are read from ONE pattern built on one shared prefix, so a
    match cannot produce an ungated +30 — the failure that would credit the boost on the five `ex`
    bodies `slowking` also runs."""
    card = _Card("If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 30 more damage to your opponent’s Active Pokémon {ex} (before applying "
                 "Weakness and Resistance). (Pokémon {ex}, Pokémon {V}, etc. have Rule Boxes.)")
    assert parse_card_damage_boost(card) == (30, None, True)
    assert _parse_tool_holder_no_rule_box(card) is True
    assert _parse_tool_holder_family(card) is None      # a Rule Box is not an owner NAME
    assert _parse_tool_attack_cost_reduction(card) == 0


def test_the_amount_and_the_RULE_BOX_gate_cannot_be_read_apart():
    """The structural guarantee, asserted **on the patterns themselves** rather than sampled.

    `_BOOST_TOOL_NO_RULE_BOX_RE` is built by concatenating the very string `_HOLDER_NO_RULE_BOX_RE`
    compiles, so no text can match the amount without also matching the gate. Round-tripping a
    handful of texts through both parsers does NOT prove that — every such text satisfies both legs
    by construction, so the assertion survives a build in which the two patterns have been allowed
    to diverge. The prefix identity is the property, so the prefix identity is what is asserted.

    Two parsers for one fact is how a gate and its amount drift apart (Issue #213), and here the
    drift would be catastrophic rather than merely wrong: an ungated +30 manufactures phantom
    lethals on the deck's biggest attackers."""
    assert _BOOST_TOOL_NO_RULE_BOX_RE.pattern.startswith(_HOLDER_NO_RULE_BOX_RE.pattern), (
        "the boost pattern must BEGIN with the gate pattern, or an amount can outrun its condition")
    # …and the property is live, not merely textual: both amounts below are recovered, and the gate
    # answers True for each, so the shared prefix is doing real work on real shapes.
    for text in ("If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 30 more damage to your opponent’s Active Pokémon {ex}.",
                 "If the Pokémon this card is attached to doesn’t have a Rule Box, the attacks it "
                 "uses do 60 more damage to your opponent’s Active Pokémon."):
        card = _Card(text)
        assert parse_card_damage_boost(card)[0] > 0
        assert _parse_tool_holder_no_rule_box(card) is True


def test_an_UNEVALUABLE_conditional_boost_still_parses_to_zero():
    """THE NEGATIVE CASE the widening must not cost: accepting ONE decidable leading condition must
    not admit conditions the parser cannot evaluate. Both cases below are ones the NEW alternative
    could plausibly have swallowed and does not — the gate inverted, and the gate aimed at the wrong
    body. Each is a benefit, so the fail direction is under-credit: 0.

    A coin-gated Tool boost is deliberately NOT asserted here, and the omission is the honest one.
    `_BOOST_TOOL_RE` — the incumbent, shipped byte-compatible at Issue #306 — carries no coin guard
    at all; "Flip a coin. If heads, Attacks used by the Pokémon this card is attached to do 30 more
    damage …" parses to 30 today, and only the lower-case "attacks" of a hand-typed variant makes it
    read 0. Asserting that zero would have recorded a guard that does not exist. It is latent rather
    than live — no card in the pool prints that shape — so it is named here rather than fixed under
    an issue about a different sentence form."""
    assert parse_card_damage_boost(_Card(
        "If the Pokémon this card is attached to has a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) == (0, None, False)
    assert parse_card_damage_boost(_Card(
        "If your opponent’s Active Pokémon doesn’t have a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) == (0, None, False)
    # …and the gate itself never fires on either, nor on a card that merely MENTIONS a Rule Box
    # without gating its holder on one, so no field records a condition with no amount behind it
    # that a later consumer could mistake for a live one.
    assert _parse_tool_holder_no_rule_box(_Card(
        "If the Pokémon this card is attached to has a Rule Box, the attacks it uses do 30 more "
        "damage to your opponent’s Active Pokémon.")) is False
    assert _parse_tool_holder_no_rule_box(_Card(
        "Search your deck for a Pokémon that doesn’t have a Rule Box, reveal it, and put it into "
        "your hand.")) is False


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


def test_the_surcharge_parser_declines_a_clause_it_cannot_evaluate():
    """THE NEGATIVE CASE for the surcharge widening — and it needs its deviation stated, because the
    fail direction INVERTS for a cost.

    The battery's doctrine (match only the clean unconditional phrasing) is written for BENEFITS:
    under-crediting a bonus is safe. Missing a PENALTY is not — it makes a retreat look cheaper than
    it is, which is the retreat-happy pathology `_effective_retreat_cost` exists to avoid. So this
    parser deliberately matches Gravity Gemstone's core clause WITHOUT requiring its "As long as …
    in the Active Spot" rider, and over-charging is the safe miss.

    What it must still decline is a clause whose SUBJECT it cannot resolve — an increase aimed at
    somebody else's body, or at a set this Tool's holder may not be in. Charging my Active for those
    would be a fabricated cost, not a conservative one."""
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of your opponent's Active Pokémon is {C} more.")) == 0
    assert _parse_tool_retreat_reduction(_Card(
        "The Retreat Cost of each Pokémon that has a Tool attached is {C}{C} more.")) == 0
    assert _parse_tool_retreat_reduction(_Card(
        "Flip a coin. If heads, the Retreat Cost of both Active Pokémon is {C} more.")) == -1
    # ^ the ONE deliberate over-match: a coin-gated surcharge is charged in full. Under-charging a
    #   penalty is the unsafe direction, so a maybe-cost is priced as a cost.


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
    """The texts above prove the REGEXES; this proves they meet the engine's actual
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
    # `retreatFreeGrant` is pinned too even though this issue never touched its parser: folding
    # newlines in `_skill_texts` widened EVERY card-level parser's input, so its inventory is part
    # of the blast radius whether or not its regex changed.
    assert carriers("retreatFreeGrant") == {170: "metal_attached", 184: "basic"}
    assert carriers("attackCostReduction") == {1171: 1}
    assert carriers("damageBoost") == {1141: 30, 1158: 50, 1171: 30, 1175: 30, 1211: 40}
    assert carriers("holderNameFamily") == {1154: "Team Rocket’s", 1171: "Hop’s",
                                            1172: "Lillie’s", 1173: "Cynthia’s"}
    # Issue #345's widening moved exactly ONE card: 1175 joined `damageBoost` (30) and is the sole
    # carrier of the new gate. Swept over the same 1267 cards — six cards print "Rule Box" and the
    # five that are not 1175 (37 Iron Thorns ex, 343 Shaymin, 1152 Poké Pad, 1184 Lana's Aid, 1247
    # Neutralization Zone) are Abilities / fetch clauses, not attached-Tool boosts, so none matches.
    assert carriers("holderNoRuleBox") == {1175: True}


def test_the_rule_box_predicate_is_a_POOL_SWEEP_not_a_hand_listed_set():
    """WHY `is_ex_body` is allowed to answer *"does this holder have a Rule Box?"* over THIS pool.

    `docs/rulebook.txt` names three Rule-Box categories beyond Pokémon ex — Radiant Pokémon (L364),
    Pokémon V and V-UNION (L391-392) — and if any of them were here, `ex or megaEx` would answer
    "no Rule Box" for a body that has one and the boost would be credited where the card refuses it.
    So the claim is not *"ex is the definition"*; it is *"over these cards the two sets coincide"*,
    and that is a sweep, not a belief.

    The instrument is the printed NAME, which the rulebook itself makes load-bearing: *"The ex is
    part of a Pokémon ex's name"* (L351), and V / VMAX / VSTAR / V-UNION / Radiant are name markers
    the same way. **Its positive control is inside the assertion**: the marker set must equal the
    engine-flag set, so an instrument that found nothing would fail here rather than pass quietly —
    and it earned that guard, because a first pass anchored on `\\bex\\b` missed three real
    multi-prize bodies printed WITHOUT a space (`PalossandEX`, `XerneasEX`, `LugiaEX`, the XY-era
    Pokémon-EX the rulebook distinguishes at L353). A card id is never listed: the day the pool
    gains a Radiant Pokémon, this test fails and the gate is re-decided."""
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
    """The gate on real records, in all three directions. `slowking` runs Brave Bangle alongside
    five Rule-Box bodies, so "credit it anyway" is not a theoretical error on this deck — it would
    put a phantom +30 on Mega Kangaskhan ex, the biggest attacker in the list.

    Mega Kangaskhan ex is the case worth naming: it is `megaEx`, NOT `ex`, so a gate written as
    `stat.ex` alone would wave it through. `is_ex_body` is `ex or megaEx` for exactly this reason
    (`docs/rulebook.txt` L337)."""
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
    weight = CardStat(POWER_WEIGHT, synthetic=True, name="Cynthia's Power Weight", cardType=2, hpBonus=70,
                      holderNameFamily="Cynthia's")
    pilot = _tool_pilot(weight)
    trace = pilot.explain(_board(PLAIN_BODY, POWER_WEIGHT)).options[0]
    assert "deploy-hp-tool" not in _fired(trace)


@pytest.mark.req("REQ-GEN-0048")
def test_the_deploy_picker_still_equips_a_body_inside_the_family():
    """The other half of the same gate: the Tool is not inert, it is TARGETED. On a `Cynthia's`
    Active the deploy rung fires — so widening the parser bought a decision rather than a field."""
    weight = CardStat(POWER_WEIGHT, synthetic=True, name="Cynthia's Power Weight", cardType=2, hpBonus=70,
                      holderNameFamily="Cynthia's")
    pilot = _tool_pilot(weight)
    trace = pilot.explain(_board(FAM_BODY, POWER_WEIGHT)).options[0]
    assert "deploy-hp-tool" in _fired(trace)
    assert trace.score > 0


def test_an_ungated_hp_tool_is_unaffected_by_the_gate_machinery():
    """The no-regression assertion: Hero's Cape reaches the same plain body the gated Tool refuses,
    so every shipped +HP decision is untouched by this issue."""
    cape = CardStat(CAPE, synthetic=True, name="Hero's Cape", cardType=2, aceSpec=True, hpBonus=100)
    pilot = _tool_pilot(cape)
    trace = pilot.explain(_board(PLAIN_BODY, CAPE)).options[0]
    assert "deploy-hp-tool" in _fired(trace)


def _boost_pilot():
    """A Pilot whose Active can be either family or plain, holding Hop's Choice Band, against an
    opponent exactly one boost short of a KO."""
    stats = DictCardStatProvider({
        CHOICE_BAND: CardStat(CHOICE_BAND, synthetic=True, name="Hop's Choice Band", cardType=2, damageBoost=30,
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


def _bangle_pilot():
    """A Pilot holding Brave Bangle, with one Rule-Box holder and one without — the SAME two
    consumers the owner family is tested against, so the second gate cannot be honoured by one
    consumer and ignored by the other. The opponent is an `{ex}` at 150 HP: Slowking's real Super
    Psy Bolt (120) is 30 short, which is exactly the Bangle."""
    stats = DictCardStatProvider({
        BRAVE_BANGLE: CardStat(BRAVE_BANGLE, name="Brave Bangle", cardType=2, damageBoost=30,
                               damageBoostVsEx=True, holderNoRuleBox=True),
        PLAIN_BODY: CardStat(PLAIN_BODY, name="Slowking", hp=120, stage="Stage 1",
                             maxDamage=120, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        FAM_BODY: CardStat(FAM_BODY, name="Mega Kangaskhan ex", hp=300, megaEx=True, stage="Basic",
                           maxDamage=120, maxDamageCost=1, minAttackCost=1, attacks=(A_HIT,)),
        OPP: CardStat(OPP, name="Opponent ex", hp=150, ex=True, stage="Basic"),
    }, attacks={A_HIT: AttackStat(A_HIT, damage=120, cost=1, damageMax=120)})
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({BRAVE_BANGLE: ["tool"]}))


def test_the_rule_box_gate_reaches_the_damage_context_consumer():
    """`_SideBase.damage_boosts` sums the Tools attached to this side's Active, and it asks the
    Tool's own `applies_to_holder` — so the second gate arrives there without that site learning a
    new condition. The `megaEx` holder contributes NOTHING: an ungated read here is what would put a
    phantom +30 on the biggest attacker in the deck that ships this card."""
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
    """The other consumer, `Pilot._boost_lethal_tactical`, which sizes a KO_SCORE-class claim off
    the same amount. 120 is 30 short of a 150-HP `{ex}` and the Bangle crosses it — but only when
    attached to a body with no Rule Box. On the `megaEx` holder the identical attach must claim
    nothing, because a lethal claimed on a boost the card does not grant is the single worst error
    this gate exists to prevent."""
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
