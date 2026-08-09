"""The apply-seam's **expectation nodes** (`common/board_expectation.py`, Issue #383) — the STOCHASTIC
half of `test_apply_transitions.py`: a reveal has a distribution, not a result.

Class identity is taken AFTER the reveal, never on the deck reference (Issue #263 forbids a partial
fingerprint over a face-down zone). No engine shuffle anywhere — probabilities come from
`common.deck_odds`' closed forms and a `NONDETERMINISTIC_CLAUSES` member refuses.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`), quoted at each constant. Dict-backed Stat
Provider and hand-built zone dicts: no Pilot, no engine boot, DLL-free on both platforms.
"""
from __future__ import annotations

import pytest

from common import apply_option as ao
from common import board_delta as bd
from common import board_expectation as be
from common import deck_odds
from common import needs
from common.state_value import state_value
from common.cards import CardFunctions
from common.effects import CardEffects
from common.fetch_closure import multiset_classes
from common.option_equivalence import AREA_ACTIVE, AREA_DECK, AREA_HAND, option_fingerprint
from common.scouting.provider import CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath
from common.strategy.context import _ABILITY, _ATTACH, _PLAY

MAIN = bd.CONTEXT_MAIN
HAND = AREA_HAND
FIGHTING, PSYCHIC, COLORLESS, WATER, DARKNESS, DRAGON = 6, 5, 0, 3, 7, 9

# The pool, quoted from `data/EN_Card_Data.csv`. 1152 Poke Pad "…doesn't have a Rule Box" | 1121
# Ultra Ball "discard 2 other cards" | 1231 Dawn: an AND | 1141 Power Pro: NO clauses | 1122: a `dig`
MASTER_BALL, POKE_PAD, ULTRA_BALL, DAWN, POWER_PRO, GEAR, ENERGY_SEARCH = (
    1125, 1152, 1121, 1231, 1141, 1122, 1119)
# 1225 Hilda "an Evolution **and** an Energy" — the CONJUNCTION fixture (neither leg reads `stage`) |
# 1142 Gong: a UNION | 1210 Brock's: EXCLUSIVE, different caps per branch | 1205 Cyrano: 3 to hand
HILDA, GONG, BROCK, CYRANO, POFFIN, TROLLEY = 1225, 1142, 1210, 1205, 1086, 1126
# 1086 Poffin, 1126 Trolley deliver ONTO THE BENCH | 1206 Larry's `discard_hand` has no fixed count |
# BOGUS_COST is synthetic: a cost value the compendium never declared
LARRY, BOGUS_COST = 1206, 1194
# 675 Lunatone: its draw is an ABILITY, so PLAYING the body reveals nothing | 1071 Meowth ex: a real
# on-bench-play trigger, but a `supporter` target `fetch_is_unconditional` rejects
LUNATONE, MEOWTH_EX = 675, 1071
DUDUNSPARCE, DRAKLOAK, FEZANDIPITI, SOLROCK = 66, 120, 140, 676
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112     # Mega Lucario ex evolves from Riolu ALONE
# 1030 Staryu: Basic, HP **70**, {W} — the only fixture body Poffin's `hp_max: 70` admits (Riolu is 80)
STARYU = 1030
E_F = 6

_ITEM, _SUPPORTER, _BASIC_ENERGY = 1, 3, 5

#: Every Pokemon row is a SOURCE claim audited field-for-field by `tests/scouting/`.
_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu"),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC),
    STARYU: CardStat(STARYU, name="Staryu", hp=70, energyType=WATER),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=_BASIC_ENERGY, energyType=FIGHTING),
    MASTER_BALL: CardStat(MASTER_BALL, name="Master Ball", cardType=_ITEM),
    POKE_PAD: CardStat(POKE_PAD, name="Poké Pad", cardType=_ITEM),
    ULTRA_BALL: CardStat(ULTRA_BALL, name="Ultra Ball", cardType=_ITEM),
    DAWN: CardStat(DAWN, name="Dawn", cardType=_SUPPORTER),
    POWER_PRO: CardStat(POWER_PRO, name="Premium Power Pro", cardType=_ITEM),
    GEAR: CardStat(GEAR, name="Pokégear 3.0", cardType=_ITEM),
    ENERGY_SEARCH: CardStat(ENERGY_SEARCH, name="Energy Search", cardType=_ITEM),
    HILDA: CardStat(HILDA, name="Hilda", cardType=_SUPPORTER),
    GONG: CardStat(GONG, name="Fighting Gong", cardType=_ITEM),
    BROCK: CardStat(BROCK, name="Brock’s Scouting", cardType=_SUPPORTER),
    CYRANO: CardStat(CYRANO, name="Cyrano", cardType=_SUPPORTER),
    POFFIN: CardStat(POFFIN, name="Buddy-Buddy Poffin", cardType=_ITEM),
    TROLLEY: CardStat(TROLLEY, name="Precious Trolley", cardType=_ITEM),
    LARRY: CardStat(LARRY, name="Larry’s Skill", cardType=_SUPPORTER),
    BOGUS_COST: CardStat(BOGUS_COST, name="Colress’s Tenacity", cardType=_SUPPORTER),
    LUNATONE: CardStat(LUNATONE, name="Lunatone", hp=110, energyType=FIGHTING),
    DUDUNSPARCE: CardStat(DUDUNSPARCE, name="Dudunsparce", hp=140, energyType=COLORLESS),
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", hp=90, energyType=DRAGON),
    FEZANDIPITI: CardStat(FEZANDIPITI, name="Fezandipiti ex", hp=210, ex=True,
                          energyType=DARKNESS),
    SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, energyType=FIGHTING),
    MEOWTH_EX: CardStat(MEOWTH_EX, name="Meowth ex", hp=170, ex=True, energyType=COLORLESS),
}

#: `card_effects.json` rows, verbatim. `POWER_PRO` is absent on purpose — that IS its row.
_CLAUSES = {
    MASTER_BALL: [{"kind": "fetch", "target": "pokemon", "zone": "deck"}],
    POKE_PAD: [{"kind": "fetch", "target": "pokemon", "zone": "deck", "no_rule_box": True}],
    ULTRA_BALL: [{"kind": "fetch", "target": "pokemon", "zone": "deck", "cost": "discard_2",
                  "cost_required": True}],
    DAWN: [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck"},
           {"kind": "fetch", "target": "stage1", "zone": "deck"},
           {"kind": "fetch", "target": "stage2", "zone": "deck"}],
    GEAR: [{"kind": "fetch", "target": "supporter", "zone": "deck", "dig": 7}],
    ENERGY_SEARCH: [{"kind": "fetch", "target": "basic_energy", "zone": "deck"}],
    HILDA: [{"kind": "fetch", "target": "energy", "zone": "deck"},
            {"kind": "fetch", "target": "evolution", "zone": "deck"}],
    GONG: [{"kind": "fetch", "target": "basic_energy", "zone": "deck", "energy_type": 6,
            "choice": True},
           {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "energy_type": 6,
            "choice": True}],
    BROCK: [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "amount": 2,
             "choice": True},
            {"kind": "fetch", "target": "evolution", "zone": "deck", "amount": 1, "choice": True}],
    CYRANO: [{"kind": "fetch", "target": "pokemon_ex", "zone": "deck", "amount": 3}],
    POFFIN: [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "hp_max": 70,
              "amount": 2, "dest": "bench"}],
    TROLLEY: [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "amount": "all",
               "dest": "bench"}],
    LARRY: [{"kind": "fetch", "target": "pokemon", "zone": "deck", "cost": "discard_hand"}],
    # A cost value `COST_CARDS` has never heard of — the drift case; no real card provides it.
    BOGUS_COST: [{"kind": "fetch", "target": "pokemon", "zone": "deck", "cost": "discard_9"}],
    LUNATONE: [{"kind": "draw", "amount": 3, "condition": "solrock_in_play",
                "allowance": "card", "rider": "discard_basic_f_energy"}],
    DUDUNSPARCE: [{"kind": "draw", "amount": 3, "allowance": "body",
                   "rider": "shuffle_self_in"}],
    DRAKLOAK: [{"kind": "draw", "amount": 1, "window": 2, "allowance": "body",
                "rider": "other_to_bottom"}],
    FEZANDIPITI: [{"kind": "draw", "amount": 3, "condition": "pokemon_ko_last_turn",
                   "allowance": "card"}],
    MEOWTH_EX: [{"kind": "fetch", "target": "supporter", "zone": "deck",
                 "trigger": "on_bench_play"}],
}


def _ids_in_hand(cls, *, kept: int = 0) -> list:
    """The ids DELIVERED into my hand; `kept` is how many pre-play hand cards survive the play."""
    hand = ((cls.model.source_obs.get("current") or {}).get("players") or [{}])[0].get("hand") or ()
    return [c.get("id") for c in hand[kept:]]


def _combat():
    return CombatMath(DictCardStatProvider(_STATS), functions=CardFunctions({}), transients=None,
                      effects=CardEffects(_CLAUSES))


def _body(cid, *, serial=1, seat=0):
    hp = _STATS[cid].hp
    return {"id": cid, "serial": serial, "playerIndex": seat, "hp": hp, "maxHp": hp,
            "appearThisTurn": False, "energies": [], "energyCards": [], "tools": [],
            "preEvolution": []}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, seat=0):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "hand": [{"id": c, "serial": 700 + i, "playerIndex": seat}
                     for i, c in enumerate(hand)],
            "handCount": len(hand),
            "discard": [{"id": c, "serial": 600 + i, "playerIndex": seat}
                        for i, c in enumerate(discard)],
            "prize": [None] * prize,
            **{f: False for f in bd.CONDITION_FLAGS}}


def _obs(me, *, context=MAIN, **current):
    opp = _player(active=_body(MUNKIDORI, serial=50, seat=1), seat=1)
    state = {"players": [me, opp], "yourIndex": 0, "turn": 5,
             "energyAttached": False, "supporterPlayed": False, "retreated": False,
             "stadiumPlayed": False, "stadium": []}
    state.update(current)
    return {"current": state, "logs": [], "select": {"context": context, "option": []}}


def _model(obs, deck):
    return StateModel.build(obs, combat=_combat(), deck=list(deck))


#: Unseen Pokemon are 3 Riolu and 1 Mega Lucario ex — two card states over four copies, which is what
#: makes "collapse by Option-Equivalence identity, never by card identity" observable.
def _search_board(hand=(MASTER_BALL,), *, deck=None, prize=4):
    deck = deck if deck is not None else [RIOLU] * 3 + [MEGA_LUC] + [E_F] * 6 + list(hand)
    obs = _obs(_player(active=_body(RIOLU), hand=hand, prize=prize))
    return _model(obs, deck)


def _play_option(index=0):
    return {"type": _PLAY, "index": index}


def _ability_option(area=AREA_ACTIVE, index=0):
    return {"type": _ABILITY, "area": area, "index": index}


def _ability_board(card_id, *, bench=(), hand=(), remaining=(), ko=False):
    from types import SimpleNamespace
    me = _player(active=_body(card_id), bench=bench, hand=hand, prize=0)
    obs = _obs(me)
    deck = [card_id, *[b["id"] for b in bench], *hand, *remaining]
    return StateModel.build(obs, combat=_combat(), deck=deck,
                            opponent=SimpleNamespace(my_pokemon_koed_last_turn=ko))


def test_a_deck_search_enumerates_one_class_per_distinct_unseen_target():
    """ADR-0091: the branching factor is the number of decisions the reveal actually poses, so three
    identical Riolu are ONE class. `serial` is the only field they differ on."""
    exp = be.expectation(_search_board(), _play_option())
    assert len(exp.classes) == 2
    assert len({c.fingerprint for c in exp.classes}) == 2


def test_the_basic_energy_in_the_deck_is_not_a_pokemon_target():
    """Filtered by the SHIPPED reach predicate, not a second matcher. Positive control: the same
    board's Energy Search DOES reach the {F} Energy that Master Ball cannot."""
    pokemon = be.expectation(_search_board(), _play_option())
    energy = be.expectation(_search_board(hand=(ENERGY_SEARCH,)), _play_option())
    assert len(pokemon.classes) == 2                        # Riolu, Mega Lucario ex — no Energy
    assert len(energy.classes) == 1                         # the {F} Energy alone


def test_poke_pad_cannot_reach_a_rule_box_body():
    """Mega Lucario ex is a Pokémon **ex**, so it HAS a Rule Box and only Riolu is reachable."""
    exp = be.expectation(_search_board(hand=(POKE_PAD,)), _play_option())
    assert len(exp.classes) == 1


def test_class_probabilities_are_deck_odds_availability_weights_normalised():
    """Asserted against a RECOMPUTATION of `deck_odds.p_contains` rather than a hard-coded float, so a
    change to the oracle moves both sides together."""
    model = _search_board()
    exp = be.expectation(model, _play_option())
    hidden, left = model.mine.prizes_hidden, model.mine.deck_count
    unseen = model.mine.unseen_counts
    want = {cid: deck_odds.p_contains(unseen[cid], hidden, left) for cid in (RIOLU, MEGA_LUC)}
    total = sum(want.values())
    got = {c.fingerprint: c.probability for c in exp.classes}
    assert abs(sum(got.values()) - 1.0) < 1e-9
    # Three Riolu against one Mega Lucario ex: the commoner class carries the larger weight.
    ordered = sorted(exp.classes, key=lambda c: -c.probability)
    assert abs(ordered[0].probability - want[RIOLU] / total) < 1e-9
    assert abs(ordered[1].probability - want[MEGA_LUC] / total) < 1e-9


def test_each_class_carries_the_POST_REVEAL_model():
    """The board AFTER THE REVEAL RESOLVES, not after the `_PLAY` step: the found card is in my hand,
    the source card is in my discard (`docs/rulebook.txt` L78), and my deck is one shorter."""
    model = _search_board()
    before = model.mine.deck_count
    exp = be.expectation(model, _play_option())
    for cls in exp.classes:
        after = cls.model
        assert MASTER_BALL in after.mine.discard_ids
        assert MASTER_BALL not in after.mine.hand_ids
        assert after.mine.deck_count == before - 1
    assert sorted(c.model.mine.hand_ids for c in exp.classes) == [(RIOLU,), (MEGA_LUC,)]


def test_the_pre_state_is_never_mutated():
    """The composer holds the pre-state while it evaluates alternatives, so an in-place edit would
    corrupt every sibling branch."""
    model = _search_board()
    hand, deck = model.mine.hand_ids, model.mine.deck_count
    be.expectation(model, _play_option())
    assert model.mine.hand_ids == hand and model.mine.deck_count == deck


def test_a_supporter_search_spends_the_supporter_allowance_and_an_item_does_not():
    """`docs/rules.md` §3 — one Supporter per turn, Items uncapped. Asserted through a single-clause
    SHIM, because the only real Supporter here is also the multi-clause case below."""
    stats = dict(_STATS)
    stats[DAWN] = CardStat(DAWN, synthetic=True, name="One-target Supporter shim",
                           cardType=_SUPPORTER)
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({**_CLAUSES,
                                             DAWN: [{"kind": "fetch", "target": "pokemon",
                                                     "zone": "deck"}]}))
    obs = _obs(_player(active=_body(RIOLU), hand=[DAWN]))
    model = StateModel.build(obs, combat=combat, deck=[RIOLU] * 3 + [E_F] * 6 + [DAWN])
    assert all(c.model.supporter_played is True for c in be.expectation(model, _play_option()).classes)
    assert all(c.model.supporter_played is False
               for c in be.expectation(_search_board(), _play_option()).classes)


def test_the_branching_cap_is_a_named_structural_constant():
    """`BRANCH_CAP`'s VALUE is derived from the measured menu-width P95, not tuned; the module
    docstring carries the derivation, so this asserts only that it is named, positive, and default."""
    assert isinstance(be.BRANCH_CAP, int) and be.BRANCH_CAP > 0
    wide = [CardStat(9000 + i, synthetic=True, name=f"pool filler {i}", hp=60) for i in range(30)]
    stats = {**_STATS, **{s.cardId: s for s in wide}}
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects(_CLAUSES))
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]))
    model = StateModel.build(obs, combat=combat, deck=[s.cardId for s in wide] + [MASTER_BALL])
    exp = be.expectation(model, _play_option())
    assert len(exp.classes) == be.BRANCH_CAP
    assert exp.truncated == 30 - be.BRANCH_CAP
    # The gap IS the truncation: a capped enumeration reading as a complete one is a silent cap.
    assert exp.total_probability < 1.0


def test_the_cap_keeps_the_HIGHEST_mass_classes():
    """Truncation drops the TAIL, so a capped `expected()` is conditional on the likeliest branches.
    Deterministic on ties (card id), so two processes enumerate one set."""
    stats = {**_STATS, **{9000 + i: CardStat(9000 + i, synthetic=True, name=f"filler {i}", hp=60)
                          for i in range(4)}}
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects(_CLAUSES))
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]))
    # 4 copies of 9000 against 1 each of the rest: 9000 is the likeliest class by construction.
    deck = [9000] * 4 + [9001, 9002, 9003, MASTER_BALL]
    model = StateModel.build(obs, combat=combat, deck=deck)
    exp = be.expectation(model, _play_option(), cap=2)
    assert exp.truncated == 2
    kept = [c.model.mine.hand_ids[0] for c in exp.classes]
    assert kept[0] == 9000
    assert exp.classes[0].probability >= exp.classes[1].probability


def test_expected_renormalises_over_the_enumerated_mass():
    """Dividing by `total_probability` keeps a truncated enumeration from being biased toward zero by
    treating dropped mass as worthless."""
    exp = be.expectation(_search_board(), _play_option(), cap=1)
    assert exp.truncated == 1
    assert abs(exp.expected(lambda m: 7.0) - 7.0) < 1e-9      # renormalised, not scaled by the mass


def test_a_cap_below_one_raises_rather_than_manufacturing_a_zero_class_expectation():
    """Caller error rather than a modelling gap, so it RAISES where a gap refuses."""
    with pytest.raises(ValueError, match="at least one class"):
        be.expectation(_search_board(), _play_option(), cap=0)


def test_expected_raises_on_an_un_enumerated_effect():
    """An Expectation with no classes is UN-ENUMERATED, and 0.0 would read as a worthless answer."""
    with pytest.raises(ValueError):
        ao.Expectation().expected(lambda m: 1.0)


def test_an_empty_pool_returns_one_certain_whiff_transition():
    """A known whiff spends the source card. It is one certain transition, never an unpriced empty node."""
    exp = be.expectation(_search_board(deck=[E_F] * 6 + [MASTER_BALL]), _play_option())
    assert len(exp.classes) == 1 and exp.total_probability == pytest.approx(1.0)
    assert exp.classes[0].model.mine.hand_ids == ()
    assert exp.classes[0].model.mine.discard_ids == (MASTER_BALL,)


def test_the_class_identity_is_taken_after_the_reveal_never_on_the_deck_reference():
    """Issue #263: a deck-referencing pick is UNFINGERPRINTABLE and joins no class. Controlled in both
    directions — `None` pre-reveal, a real identity once the card is in my HAND."""
    model = _search_board()
    pre = model.source_obs
    deck_pick = {"type": ao._CARD if hasattr(ao, "_CARD") else 1,
                 "area": AREA_DECK, "index": 0, "playerIndex": 0}
    assert option_fingerprint(deck_pick, pre) is None        # blind => no class, as designed
    exp = be.expectation(model, _play_option())
    for cls in exp.classes:
        assert cls.fingerprint and all(f is not None for f in cls.fingerprint)
        post = cls.model.source_obs
        hand_pick = {"type": _PLAY, "area": AREA_HAND, "index": 0, "playerIndex": 0}
        assert option_fingerprint(hand_pick, post) is not None


def test_a_card_with_no_revealing_clause_is_not_an_expectation_node():
    with pytest.raises(bd.Unmodellable, match="no `draw`/`fetch`"):
        be.expectation(_search_board(hand=(POWER_PRO,)), _play_option())


def test_a_conjunction_enumerates_one_card_per_leg_and_SKIPS_an_empty_one():
    """The ENGINE skips an empty bucket rather than failing the card (`chain_overrides.json`: *"empty
    buckets skip with a tac bump"*), so refusing here would refuse a card the engine resolves."""
    exp = be.expectation(_search_board(hand=(DAWN,)), _play_option())
    assert [tuple(sorted(_ids_in_hand(c))) for c in exp.classes] == [(RIOLU,)]


def test_a_conjunction_takes_the_CROSS_PRODUCT_when_several_legs_are_live():
    """Both legs find something here, so the classes are the PRODUCT: one Evolution x one Energy."""
    exp = be.expectation(_search_board(hand=(HILDA,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(E_F, MEGA_LUC)]        # the only Evolution x the only Energy class
    assert all(len(c.fingerprint) == 2 for c in exp.classes), "both delivered cards form the identity"


def test_a_union_enumerates_ONE_card_over_the_pooled_legs():
    """The engine settles a UNION with a single `anyOf`-filtered op, so the classes are ONE card over
    the pooled legs — read as a conjunction it would claim the card delivers two."""
    exp = be.expectation(_search_board(hand=(GONG,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(E_F,), (RIOLU,)]
    assert all(len(c.fingerprint) == 1 for c in exp.classes)


def test_a_union_leg_honours_the_energy_type_gate_on_its_POKEMON_target():
    """The one EXISTING enumeration ADR-0133 changed, and it is a fix. Fighting Gong is *"a Basic {F}
    Energy card or a Basic {F} Pokémon"*, and Meowth ex is {C} — so it was enumerating an impossibility."""
    deck = [RIOLU] * 2 + [MEOWTH_EX, GONG] + [E_F] * 6      # one Riolu is the Active, so unseen is 1
    exp = be.expectation(_search_board(hand=(GONG,), deck=deck), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(E_F,), (RIOLU,)], "a {C} Basic is still reachable through an {F} leg"
    assert _STATS[MEOWTH_EX].energyType == COLORLESS and _STATS[RIOLU].energyType == FIGHTING


def test_a_multi_card_delivery_to_HAND_enumerates_multisets_not_subsets():
    """The classes are MULTISETS, not subsets: a pool may hold several copies and taking two is a
    legal, distinct outcome. The delivery CLAMPS to the pool (`min(max, matches)`), never padded."""
    exp = be.expectation(_search_board(hand=(CYRANO,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(MEGA_LUC,)]
    assert all(len(c.fingerprint) == 1 for c in exp.classes)


def test_a_multi_card_delivery_takes_SEVERAL_COPIES_of_one_card_when_the_pool_holds_them():
    """A subset reading would offer only `(Riolu, Mega)` and silently claim the deck cannot produce a
    third body it plainly can."""
    pool = {RIOLU: 3, MEGA_LUC: 1}
    assert multiset_classes(pool, 3) == [(RIOLU, RIOLU, RIOLU), (RIOLU, RIOLU, MEGA_LUC)] or \
        sorted(multiset_classes(pool, 3)) == sorted([(RIOLU, RIOLU, RIOLU),
                                                        (RIOLU, RIOLU, MEGA_LUC)])
    assert len(multiset_classes(pool, 3)) == 2


def test_a_multi_card_class_weighs_each_card_at_the_multiplicity_it_needs():
    """TWO copies needs `p_contains_at_least(..., 2)`, not `p_contains` — the >=1 form would
    over-report every duplicate-bearing class."""
    model = _search_board(hand=(CYRANO,))
    hidden, left = model.mine.prizes_hidden, model.mine.deck_count
    unseen = model.mine.unseen_counts or {}
    triple = be._class_weight(model, (RIOLU, RIOLU, RIOLU))
    assert triple == pytest.approx(
        deck_odds.p_contains_at_least(unseen.get(RIOLU, 0), hidden, left, 3))
    mixed = be._class_weight(model, (RIOLU, RIOLU, MEGA_LUC))
    assert mixed == pytest.approx(
        deck_odds.p_contains_at_least(unseen.get(RIOLU, 0), hidden, left, 2)
        * deck_odds.p_contains_at_least(unseen.get(MEGA_LUC, 0), hidden, left, 1))
    # …and a one-card class stays bit-for-bit the shipped `p_contains`.
    assert be._class_weight(model, (RIOLU,)) == \
        deck_odds.p_contains(unseen.get(RIOLU, 0), hidden, left)


def test_the_multiset_enumerator_degenerates_to_todays_classes_at_one_card():
    """At m=1 the enumerator must be exactly one class per distinct pool card."""
    pool = {RIOLU: 3, MEGA_LUC: 1, E_F: 6}
    assert multiset_classes(pool, 1) == [(E_F,), (RIOLU,), (MEGA_LUC,)][::1] or \
        sorted(multiset_classes(pool, 1)) == sorted([(E_F,), (RIOLU,), (MEGA_LUC,)])
    # A copy count BOUNDS the multiplicity — one Mega Lucario ex can never arrive twice.
    assert all(k.count(MEGA_LUC) <= 1 for k in multiset_classes(pool, 3))
    # …and the delivery is clamped by what the pool actually holds, never padded.
    assert multiset_classes({MEGA_LUC: 1}, 3) == [(MEGA_LUC,)]
    assert multiset_classes({}, 3) == []


def _poffin_board(*, bench=(), copies=3):
    """Poffin plus ``copies`` Staryu unseen; only HP-70 Staryu passes its filter.
    Energy keeps cards in deck after four prizes; any other class proves filter drift."""
    deck = [STARYU] * copies + [RIOLU] + [MEGA_LUC] + [E_F] * 6 + [POFFIN]
    obs = _obs(_player(active=_body(RIOLU), bench=bench, hand=(POFFIN,), prize=4))
    return _model(obs, deck)


def _benched_ids(cls) -> list:
    seat = ((cls.model.source_obs.get("current") or {}).get("players") or [{}])[0]
    return [b.get("id") for b in (seat.get("bench") or ())]


def test_a_BENCH_delivery_lands_on_the_bench_and_never_in_hand():
    """Issue #446 S2. `dest: bench` composes the reveal with `board_delta`'s deploy primitives, so the
    found body ARRIVES rather than being priced as a hand card it never becomes."""
    exp = be.expectation(_poffin_board(), _play_option())
    # `multiset_classes` delivers the MAXIMUM the cap and the pool allow, so `amount: 2` over three
    # unseen Staryu is ONE class of two bodies — not one class per count.
    assert [_benched_ids(c) for c in exp.classes] == [[STARYU, STARYU]]
    for cls in exp.classes:
        assert _ids_in_hand(cls) == [], "a `dest: bench` card must not also reach my hand"


def test_a_BENCH_delivery_is_bounded_by_the_REAL_bench_cap():
    """The cap is the engine's own `benchMax`, so a class the board has no room for is never
    enumerated. Four occupied of five leaves ONE slot, so `amount: 2` may deliver only one."""
    full = [_body(RIOLU, serial=10 + i) for i in range(4)]
    exp = be.expectation(_poffin_board(bench=full), _play_option())
    assert [_benched_ids(c)[4:] for c in exp.classes] == [[STARYU]]


def test_a_BENCH_delivery_with_NO_room_refuses_rather_than_delivering_nothing():
    """A full Bench makes the play unreachable, not free: pricing it as a zero-body delivery would
    rank a dead Item beside a live one."""
    full = [_body(RIOLU, serial=10 + i) for i in range(5)]
    # Matched on the OPEN-SLOT wording, not on the word "Bench": the `dest` refusal this replaces
    # also said "Bench cap", so a loose match passed before the capability existed.
    with pytest.raises(bd.Unmodellable, match="no open Bench slot"):
        be.expectation(_poffin_board(bench=full), _play_option())


def test_a_provable_whiff_is_a_certain_transition_and_a_hit_still_enumerates():
    """An empty target pool still spends Poffin. It is known, never an unpriced zero-class effect."""

    board = _poffin_board(copies=0)
    whiff = be.expectation(board, _play_option())
    assert whiff.resolution == ao.CHOSEN and len(whiff.classes) == 1
    assert whiff.total_probability == pytest.approx(1.0)
    after = whiff.classes[0].model
    assert POFFIN in after.mine.discard_ids and not after.mine.hand_ids
    assert be.expectation(_poffin_board(), _play_option()).classes   # positive control: it can hit


def test_a_search_with_fewer_deck_slots_than_its_cap_still_models_the_partial_hit():
    """An up-to-two Poffin takes one reachable Staryu; it is neither an empty whiff nor a refusal."""
    obs = _obs(_player(active=_body(RIOLU), hand=(POFFIN,), prize=1))
    board = _model(obs, [STARYU, STARYU, RIOLU, POFFIN])
    assert board.mine.unseen_counts[STARYU] == 2 and board.mine.deck_count == 1
    exp = be.expectation(board, _play_option())
    assert [_benched_ids(cls) for cls in exp.classes] == [[STARYU]]


def test_a_zero_deck_conjunction_is_a_certain_empty_transition():
    """A Hilda whose Evolution and Energy are certainly prized still spends the Supporter."""
    obs = _obs(_player(active=_body(RIOLU), hand=(HILDA,), prize=2))
    board = _model(obs, [HILDA, MEGA_LUC, E_F, RIOLU])
    assert board.mine.deck_count == 0
    exp = be.expectation(board, _play_option())
    assert len(exp.classes) == 1
    assert _ids_in_hand(exp.classes[0]) == []


def test_a_provable_whiff_spends_its_hand_resource_in_the_existing_ledger():
    """A known Poffin whiff is strictly worse than END when its held resource has ledger value."""
    obs = _obs(_player(active=_body(RIOLU), hand=(POFFIN,), prize=4))
    deck = [RIOLU, MEGA_LUC] + [E_F] * 6 + [POFFIN]

    def _hand_ledger(end, seat):
        hand = (((end.get("current") or {}).get("players") or [{}])[seat].get("hand") or ())
        ids = tuple(card.get("id") for card in hand)
        return needs.Resolution(hand_ids=ids, latent_worth=float(POFFIN in ids))

    board = StateModel.build(obs, combat=_combat(), deck=deck, needs=_hand_ledger)
    whiff = be.expectation(board, _play_option()).classes[0].model
    assert state_value(whiff) < state_value(board)


def test_an_unhandled_dest_still_fails_CLOSED():
    """`in_play` puts an EVOLUTION onto a chosen body — a choice node, not a deploy. The positive
    control for the test above: the `dest` gate still refuses what it cannot place."""
    clauses = dict(_CLAUSES)
    clauses[POFFIN] = [{"kind": "fetch", "target": "basic_pokemon", "zone": "deck",
                        "hp_max": 70, "amount": 2, "dest": "in_play"}]
    combat = CombatMath(DictCardStatProvider(_STATS), functions=CardFunctions({}),
                        transients=None, effects=CardEffects(clauses))
    obs = _obs(_player(active=_body(RIOLU), hand=(POFFIN,), prize=4))
    model = StateModel.build(obs, combat=combat, deck=[STARYU] * 3 + [POFFIN])
    with pytest.raises(bd.Unmodellable, match="`dest`"):
        be.expectation(model, _play_option())


def test_an_amount_of_all_still_refuses_because_it_names_no_number():
    """`amount: "all"` names no number the enumerator can range over. Refused explicitly rather than
    falling through to a catch-all (Issue #410 owns it)."""
    with pytest.raises(bd.Unmodellable, match="`amount`"):
        be.expectation(_search_board(hand=(TROLLEY,)), _play_option())


def test_an_exclusive_either_or_still_refuses_rather_than_guessing_a_cap():
    """`choice` on both legs but DIFFERENT budgets, so there is no single shared cap to enumerate over
    and the engine gives it its own op (`xDeckToHandEitherOr`)."""
    with pytest.raises(bd.Unmodellable, match="either-or"):
        be.expectation(_search_board(hand=(BROCK,)), _play_option())


def test_a_costed_search_refuses_because_the_cost_names_no_target():
    """WHICH two cards pay is chosen at a FOLLOW-UP select, so the cost's writes cannot be placed."""
    with pytest.raises(bd.Unmodellable, match="cost"):
        be.expectation(_search_board(hand=(ULTRA_BALL,)), _play_option())


#: A Pokégear board whose window math is checkable by hand: 9 unseen cards (5 deck + 4 hidden prizes)
#: of which 1 Hilda and 2 Dawn are Supporters, and a look 5 deep because the deck is only 5.
_DIG_DECK = [RIOLU, GEAR, DAWN, DAWN, HILDA] + [E_F] * 6


def _hand_score(marker=HILDA):
    """A score that ranks ``marker`` above every other delivery, so the greedy order is the test's."""
    def score(model):
        hand = ((model.source_obs.get("current") or {}).get("players") or [{}])[0].get("hand") or ()
        return sum(10.0 if c.get("id") == marker else 1.0 for c in hand)
    return score


def test_a_dig_enumerates_its_window_and_the_whiff_is_one_of_the_classes():
    """1 − C(8,5)/C(9,5) for the best Supporter, the bracket below it for the next, and C(6,5)/C(9,5)
    left over for finding neither — the telescoping closed form, so the mass is exactly 1.0."""
    exp = be.expectation(_search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option(),
                         score=_hand_score())
    assert [_ids_in_hand(c) for c in exp.classes] == [[HILDA], [DAWN], []]
    assert [round(c.probability, 12) for c in exp.classes] == [
        round(1 - 56 / 126, 12), round(50 / 126, 12), round(6 / 126, 12)]
    assert round(exp.total_probability, 12) == 1.0 and exp.truncated == 0


def test_a_dig_resolves_DEALT_so_the_ordering_averages_rather_than_taking_the_best_branch():
    """The window DEALS. Under CHOSEN this priced Pokégear at *"I always find my best Supporter"* —
    the gamble the resolution split exists to stop — and no test would have failed."""
    exp = be.expectation(_search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option(),
                         score=_hand_score())
    assert exp.resolution == ao.DEALT
    leaf = lambda model: float(len(((model.source_obs["current"]["players"])[0].get("hand") or ())))
    assert exp.ordering(leaf) == exp.expected(leaf) < exp.best(leaf)


def test_a_dig_with_no_score_oracle_refuses_rather_than_inventing_its_own_ranking():
    """The probabilities are exact only under the take-the-best policy, so the value that ranks the
    window is the caller's to supply — `_cost_indices` makes the same demand of `shed`."""
    with pytest.raises(bd.Unmodellable, match="`score` oracle"):
        be.expectation(_search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option())


def test_the_dig_ranking_is_the_policy_priced_so_reversing_the_value_reverses_the_classes():
    """Positive control on the ranking: the same board with Dawn valued highest moves the whole
    distribution, because which card the window hands over IS what the brackets are taken over."""
    board, option = _search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option()
    hilda = be.expectation(board, option, score=_hand_score(HILDA))
    dawn = be.expectation(board, option, score=_hand_score(DAWN))
    assert [_ids_in_hand(c) for c in dawn.classes] == [[DAWN], [HILDA], []]
    assert dawn.classes[0].probability > hilda.classes[0].probability     # 2 copies beat 1
    assert round(dawn.classes[-1].probability, 12) == round(hilda.classes[-1].probability, 12)


def test_the_whiff_class_is_pinned_past_the_branching_cap():
    """A greedy ranking makes the dropped classes the WORST ones, so on a DEALT node truncation
    biases `expected()` UP. The whiff is the one class this node exists to price, so it keeps a slot."""
    exp = be.expectation(_search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option(),
                         score=_hand_score(), cap=2)
    assert [_ids_in_hand(c) for c in exp.classes] == [[HILDA], []]
    assert exp.truncated == 1 and exp.total_probability < 1.0


def test_the_whiff_never_takes_the_only_slot_and_is_counted_as_truncated_when_it_cannot_fit():
    """The pin is not unconditional: at a cap of one, pricing a live dig as a certain whiff would be
    a worse lie than dropping it, so the class is dropped and REPORTED rather than silently gone."""
    exp = be.expectation(_search_board(hand=(GEAR,), deck=_DIG_DECK), _play_option(),
                         score=_hand_score(), cap=1)
    assert [_ids_in_hand(c) for c in exp.classes] == [[HILDA]]
    assert exp.truncated == 2                          # the Dawn class AND the unpinnable whiff


def test_the_window_is_the_deck_but_the_pool_it_is_drawn_from_is_deck_plus_hidden_prizes():
    """ADR-0133's identity: deck-then-window composes to ONE uniform subset of the unseen, so the
    prize split needs no mixture. Checked against that mixture, which is what `gamble` spells out."""
    from math import comb
    unseen, deck, hidden, window = 3, 5, 4, 5
    mixture = sum(comb(deck, j) * comb(hidden, unseen - j) / comb(deck + hidden, unseen)
                  * (1.0 - (comb(deck - j, window) / comb(deck, window) if deck - j >= window else 0))
                  for j in range(max(0, unseen - hidden), min(unseen, deck) + 1))
    assert round(mixture, 12) == round(
        1.0 - deck_odds.window_miss_probability(unseen, deck + hidden, window), 12)


def test_the_hit_form_is_the_miss_form_inverted_over_the_whole_input_grid():
    """`draw_hit_probability` DELEGATES to the miss bracket, so the two cannot drift. Byte-identical
    to the retired inline form on every input, junk included — the fail directions invert together."""
    from itertools import product
    from math import comb

    def retired(copies, pool, draws):
        try:
            c, p, n = int(copies), int(pool), int(draws)
        except Exception:
            return 0.0
        if c <= 0 or p <= 0:
            return 0.0
        n = min(n, p)
        if n <= 0:
            return 0.0
        if c >= p:
            return 1.0
        return 1.0 - comb(p - c, n) / comb(p, n)

    grid = list(product(range(-3, 20), repeat=3))
    assert all(retired(*a) == deck_odds.draw_hit_probability(*a) for a in grid), "the forms drifted"
    assert all(retired(j, 40, 7) == deck_odds.draw_hit_probability(j, 40, 7)
               for j in (None, "x", 1.5, [], object()))


def test_the_dig_whiff_and_the_public_miss_bracket_are_ONE_number():
    """The bracket is promoted, not copied: `window_classes` seeds `()` from it rather than letting
    its own all-zero branch produce a second answer that could quietly disagree."""
    order, copies, pool, window = (1, 2), {1: 3, 2: 2}, 20, 6
    classes = be.window_classes(order, copies, pool, window, 1)
    assert classes[()] == deck_odds.window_miss_probability(5, pool, window)
    assert round(sum(classes.values()), 12) == 1.0


@pytest.mark.parametrize("groups, pool, window, take", [
    (((1, 2), (2, 3), (3, 1)), 10, 4, 2),          # a same-group PAIR is reachable
    (((1, 4), (2, 2), (3, 3), (4, 1)), 14, 5, 2),
    (((1, 1), (2, 1)), 6, 3, 2),
    (((1, 3), (2, 2)), 9, 4, 1),
    (((1, 2), (2, 1), (3, 2)), 8, 3, 3),           # `take` above what the window can hold
    (((1, 2),), 4, 1, 2),
    ((), 7, 3, 2),                                 # nothing matches: the whiff is the only class
])
def test_the_window_closed_form_is_exact_against_enumerating_every_subset(groups, pool, window, take):
    """The only part of this node that cannot be read off the board. Brute force is the oracle: every
    `window`-subset of `pool`, greedy-picked in rank order, tallied — no formula on either side."""
    from itertools import combinations
    order = tuple(g for g, _ in groups)
    copies = {g: n for g, n in groups}
    marked = [g for g, n in groups for _ in range(n)]
    rank = {g: i for i, g in enumerate(order)}
    seen: dict = {}
    subsets = list(combinations(range(pool), window))
    for sub in subsets:
        held = sorted((marked[i] for i in sub if i < len(marked)), key=rank.__getitem__)
        klass = tuple(sorted(held[:take]))
        seen[klass] = seen.get(klass, 0) + 1
    exact = be.window_classes(order, copies, pool, window, take)
    assert {k: round(v / len(subsets), 12) for k, v in seen.items()} == {
        k: round(v, 12) for k, v in exact.items()}
    assert round(sum(exact.values()), 12) == 1.0


def test_a_draw_refuses_rather_than_projecting_an_n_card_window_onto_one_card():
    """`deck_odds` answers *"P(at least one target in the window)"*, not the JOINT distribution over
    which n cards arrived, so single-card classes for an n-card draw would be a biased conditional."""
    stats = {**_STATS}
    stats[MASTER_BALL] = CardStat(MASTER_BALL, synthetic=True, name="Draw shim", cardType=_ITEM)
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({MASTER_BALL: [{"kind": "draw", "amount": 4}]}))
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]))
    model = StateModel.build(obs, combat=combat, deck=[RIOLU] * 3 + [MASTER_BALL])
    with pytest.raises(bd.Unmodellable, match="draw"):
        be.expectation(model, _play_option())


def test_a_shuffling_clause_is_never_simulated():
    """The engine has NO deal-seed, so a simulated shuffle is one SAMPLE rather than a distribution
    and it breaks the deterministic replay both ADR-0072 gates depend on (Issue #178)."""
    stats = {**_STATS}
    stats[MASTER_BALL] = CardStat(MASTER_BALL, synthetic=True, name="Shuffle shim", cardType=_ITEM)
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({MASTER_BALL: [{"kind": "fetch", "target": "pokemon",
                                                            "zone": "deck",
                                                            "rider": "shuffle_both_hands"}]}))
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]))
    model = StateModel.build(obs, combat=combat, deck=[RIOLU] * 3 + [MASTER_BALL])
    with pytest.raises(bd.Unmodellable, match="RNG"):
        be.expectation(model, _play_option())


def test_a_non_MAIN_context_refuses_on_the_same_boundary_as_the_transitions():
    """An option posed INSIDE a card's effect is one leg of that CARD's step, so it carries writes
    belonging to the card rather than to the option's own kind."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]), context=37)
    model = _model(obs, [RIOLU] * 3 + [MASTER_BALL])
    with pytest.raises(bd.Unmodellable, match="MAIN"):
        be.expectation(model, _play_option())


def test_a_kind_other_than_PLAY_refuses():
    """A reveal riding an `_ABILITY` or `_ATTACH` does not put the source card in my discard, so this
    module's structural floor around the reveal does not hold for it."""
    with pytest.raises(bd.Unmodellable, match="kind"):
        be.expectation(_search_board(), {"type": _ATTACH, "index": 0})


def _shed_first(n):
    """Deliberately dumb: the node's contract is only that it applies whatever set it is handed, so
    these tests must not depend on which set. The real oracle is `Pilot.cost_shed_indices`."""
    def shed(model, option, picks):
        hand = ((model.source_obs["current"]["players"])[0].get("hand") or ())
        return [i for i in range(len(hand)) if i != option.get("index")][:n]
    return shed


def test_a_costed_search_refuses_when_no_shed_oracle_is_supplied_and_NAMES_the_seam():
    """Pricing the cost UNPAID would over-value every costed search by the cards it does not charge
    for, so the refusal names the missing SEAM rather than the card — supplying it is the caller's job."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    with pytest.raises(bd.Unmodellable, match="no `shed` oracle"):
        be.expectation(board, _play_option())


def test_a_costed_search_ENUMERATES_once_the_oracle_is_supplied():
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    exp = be.expectation(board, _play_option(), shed=_shed_first(2))
    assert exp.classes and exp.total_probability == pytest.approx(1.0)


def test_the_cost_is_charged_BEFORE_the_search_so_a_found_card_cannot_pay_for_itself():
    """The engine's own order (`chain_overrides.json`: `[costHandTrash, effectDeckToHandAndShuffle]`).
    Charging afterwards would let a delivered card pay for the search that delivered it."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    exp = be.expectation(board, _play_option(), shed=_shed_first(2))
    for cls in exp.classes:
        me = (cls.model.source_obs["current"]["players"])[0]
        assert [c["id"] for c in me["discard"]].count(RIOLU) == 2      # both paid cards
        assert ULTRA_BALL in [c["id"] for c in me["discard"]]          # ...and the source card
        assert len(me["hand"]) == 1 and me["handCount"] == 1           # only the delivery remains


def test_the_cost_never_takes_the_card_being_played():
    """The engine's gate is `handOthers` — *"discard 2 OTHER cards"* — so an oracle naming the played
    card's own index has it DROPPED, and the short payment refuses."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    def names_the_played_card(model, option, picks):
        return [0, 1]                                    # index 0 IS the Ultra Ball being played
    with pytest.raises(bd.Unmodellable, match="usable hand index"):
        be.expectation(board, _play_option(), shed=names_the_played_card)


def test_an_unpayable_cost_refuses_as_an_ILLEGAL_play_not_a_free_one():
    """The engine would never OFFER this play, so pricing it as merely cheap would put an unreal
    option on the menu with a positive delta."""
    with pytest.raises(bd.Unmodellable, match="usable hand index"):
        be.expectation(_search_board(hand=(ULTRA_BALL,)), _play_option(), shed=_shed_first(2))


def test_a_cost_with_no_fixed_count_refuses_by_NAME():
    """Two reasons, both in `COST_CARDS`: a whole-hand discard has no constant count, and `bottom_2`
    returns cards to the DECK, moving `unseen_counts` and invalidating the pool being enumerated."""
    board = _search_board(hand=(LARRY,))
    with pytest.raises(bd.Unmodellable, match="no fixed card count"):
        be.expectation(board, _play_option(), shed=_shed_first(2))


def test_an_undeclared_cost_value_fails_CLOSED():
    """A cost nobody declared a count for must refuse, never charge 0."""
    board = _search_board(hand=(BOGUS_COST,))
    with pytest.raises(bd.Unmodellable, match="not in `snapshot_coverage.COST_CARDS`"):
        be.expectation(board, _play_option(), shed=_shed_first(2))


def test_a_reveal_declared_on_a_BODY_is_an_ability_and_refuses_as_one():
    """Modelling this would be WRONG, not under-scoped: an Ability does not fire because the body was
    PLAYED, so an expectation node over its draw prices a reveal that never happens."""
    with pytest.raises(bd.Unmodellable, match="is an ABILITY"):
        be.expectation(_search_board(hand=(LUNATONE,)), _play_option())


def test_an_on_bench_play_trigger_passes_the_ability_gate_and_refuses_on_its_CLAUSE():
    """`trigger: on_bench_play` DOES ride the `_PLAY`, so it passes the ability gate and refuses on
    what is actually wrong with it — the gate discriminates rather than catching a whole side."""
    with pytest.raises(bd.Unmodellable, match=r"cannot decide `trigger`"):
        be.expectation(_search_board(hand=(MEOWTH_EX,)), _play_option(), score=state_value)


def test_MAIN_ability_source_resolves_body_without_touching_hand():
    model = _ability_board(FEZANDIPITI, ko=True, remaining=(RIOLU,) * 4)
    result = be.closed_form_transition(model, _ability_option(), score=state_value,
                                       clauses_cover=True)
    assert isinstance(result, ao.ScalarTransition)
    assert result.model.mine.hand_size == 3
    assert result.model.ability_used_cards == {FEZANDIPITI}
    assert result.model.mine.active.card_id == FEZANDIPITI


@pytest.mark.parametrize("option", [
    {"type": _ABILITY, "area": AREA_HAND, "index": 0},
    {"type": _ABILITY, "area": AREA_ACTIVE, "index": 9},
])
def test_malformed_MAIN_ability_source_refuses_as_an_in_play_reference(option):
    model = _ability_board(FEZANDIPITI, ko=True, hand=(RIOLU,), remaining=(RIOLU,) * 4)
    with pytest.raises(bd.Unmodellable, match="_ABILITY.*source area/index"):
        be.closed_form_transition(model, option, score=state_value, clauses_cover=True)


def test_Fezandipiti_requires_the_KO_condition_before_spending_global_allowance():
    model = _ability_board(FEZANDIPITI, remaining=(RIOLU,) * 4)
    with pytest.raises(bd.Unmodellable, match="pokemon_ko_last_turn.*does not hold"):
        be.closed_form_transition(model, _ability_option(), score=state_value,
                                  clauses_cover=True)
    assert model.ability_used_cards == frozenset()


def test_Lunatone_discards_only_legal_basic_F_fuel_using_the_shed_order():
    solrock = _body(SOLROCK, serial=22)
    model = _ability_board(LUNATONE, bench=(solrock,), hand=(E_F, RIOLU, E_F),
                           remaining=(RIOLU,) * 5)
    seen = {}

    def shed(_model, option, picks, eligible):
        seen.update(option=option, picks=picks, eligible=tuple(eligible))
        return (eligible[-1],)

    result = be.closed_form_transition(model, _ability_option(), score=state_value,
                                       clauses_cover=True, shed=shed)
    assert seen == {"option": _ability_option(), "picks": 1, "eligible": (0, 2)}
    assert isinstance(result, ao.ScalarTransition)
    assert result.model.mine.hand_ids == (E_F, RIOLU)
    assert result.model.mine.discard_ids == (E_F,)
    assert result.model.ability_used_cards == {LUNATONE}


@pytest.mark.parametrize("bench,hand,reason", [
    ((), (E_F,), "solrock_in_play"),
    ((_body(SOLROCK, serial=22),), (RIOLU,), "Basic.*Energy"),
])
def test_Lunatone_refuses_when_partner_or_fuel_is_missing(bench, hand, reason):
    model = _ability_board(LUNATONE, bench=bench, hand=hand, remaining=(RIOLU,) * 5)
    with pytest.raises(bd.Unmodellable, match=reason):
        be.closed_form_transition(model, _ability_option(), score=state_value,
                                  clauses_cover=True, shed=lambda *_args: ())


def _drak_score(model):
    return 10.0 if MEGA_LUC in model.mine.hand_ids else 1.0 if RIOLU in model.mine.hand_ids else 0.0


def test_Drakloak_look_two_takes_the_best_card_with_exact_probabilities():
    model = _ability_board(DRAKLOAK, remaining=(RIOLU, RIOLU, RIOLU, MEGA_LUC))
    result = be.closed_form_transition(model, _ability_option(), score=_drak_score,
                                       clauses_cover=True)
    assert isinstance(result, ao.Expectation) and result.resolution == ao.DEALT
    by_card = {cls.model.mine.hand_ids[-1]: cls for cls in result.classes}
    assert by_card[MEGA_LUC].probability == pytest.approx(0.5)
    assert by_card[RIOLU].probability == pytest.approx(0.5)
    assert all(cls.model.mine.deck_count == 3 for cls in result.classes)
    assert all(cls.model.ability_used_bodies == {1} for cls in result.classes)


@pytest.mark.parametrize("remaining,expected", [
    ((), {()}),
    ((RIOLU,), {(RIOLU,)}),
    ((RIOLU, RIOLU), {(RIOLU,)}),
    ((RIOLU, MEGA_LUC), {(MEGA_LUC,)}),
])
def test_Drakloak_handles_deck_sizes_and_duplicates(remaining, expected):
    model = _ability_board(DRAKLOAK, remaining=remaining)
    result = be.closed_form_transition(model, _ability_option(), score=_drak_score,
                                       clauses_cover=True)
    delivered = {tuple(cls.model.mine.hand_ids) for cls in result.classes}
    assert delivered == expected
    assert result.total_probability == pytest.approx(1.0)
    assert {cls.model.mine.deck_count for cls in result.classes} == {max(0, len(remaining) - 1)}


def test_Dudunsparce_refuses_the_unmodelled_body_shuffle_by_name():
    model = _ability_board(DUDUNSPARCE, remaining=(RIOLU,) * 4)
    with pytest.raises(bd.Unmodellable, match="shuffle_self_in.*body"):
        be.closed_form_transition(model, _ability_option(), score=state_value,
                                  clauses_cover=True)


#: Every dig-family card OUTSIDE Issue #440's two-deck scope, with the field that must still refuse it.
#: Rows are `card_effects.json` verbatim; the point is that admitting `dig` admitted nothing else.
_OUT_OF_SCOPE_DIGS = [
    (1077, "Roto-Stick", "amount"), (1102, "Dusk Ball", "dig_from"),
    (1185, "Explorer’s Guidance", "rider"), (1193, "Hassel", "condition"),
    (1115, "Hop’s Bag", "name_family"),
    # Issue #469's card. Its `window` rides a `draw`, but the RNG gate is MORE specific and runs
    # first: `other_to_bottom` returns cards to a deck this node has already enumerated over.
    (120, "Drakloak", "other_to_bottom"),
]


@pytest.mark.parametrize("card_id, name, field", _OUT_OF_SCOPE_DIGS)
def test_admitting_the_dig_field_admitted_nothing_else_in_the_family(card_id, name, field):
    """The regression an over-broad gate would cause. Each row still refuses, and the refusal names
    ONLY the field that fired — a message listing all of them passes every row without grading one."""
    from common.effects import CardEffects
    clauses = list(CardEffects.load().clauses(card_id))
    assert clauses, f"{card_id} {name}: no compendium row, so this test is grading nothing"
    refusals = []
    for clause in clauses:
        with pytest.raises(bd.Unmodellable) as caught:
            be._check_clause(clause, card_id, name)
        refusals.append(str(caught.value))
    assert any(field in message for message in refusals), refusals
    others = {f for _cid, _name, f in _OUT_OF_SCOPE_DIGS if f != field} | {"dig`"}
    assert not [f for f in others if any(f in m for m in refusals)], (
        f"the refusal names a field that did not fire, so every row would pass: {refusals}")


def test_the_card_type_floor_is_now_UNREACHABLE_for_the_shipped_pool():
    """The card-type floor survives as a structural backstop that should catch nothing real: every
    shipped card refuses on its own defect first. Only an otherwise-clean on-bench-play trigger reaches it."""
    from common.effects import CardEffects
    from common.fetch_closure import fetch_is_unconditional
    eff = CardEffects.load()
    reachable = []
    for cid in (LUNATONE, MEOWTH_EX, 140):                # the three real carriers
        for clause in eff.clauses(cid):
            if clause.get("trigger") == "on_bench_play" and fetch_is_unconditional(clause):
                reachable.append(cid)
    assert reachable == [], f"a card can now reach the card-type floor: {reachable}"
