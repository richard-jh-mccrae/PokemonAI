"""The apply-seam's **expectation nodes** (`common/board_expectation.py`, POC-T4/2, Issue #383,
under the seam contract ADR-0098 froze at POC-T0).

`test_apply_transitions.py` asserts the DETERMINISTIC transitions (Issue #382): one option, one
board. This file asserts the STOCHASTIC half — a reveal has no *a* result, it has a distribution, and
the honest seam returns the distribution rather than a sampled representative.

Three properties carry the whole file:

* **The class identity is taken AFTER the reveal, never on the deck reference.** Issue #263's
  §*duplicate-cards* second property forbids giving a deck-referencing pick a partial fingerprint to
  make it collapse — the face-down deck exposes only a count, so such an option joins NO class by
  design. This module never fingerprints one: it synthesizes the post-reveal board, where the card is
  in my HAND and therefore revealed, and fingerprints THERE.
  `test_the_class_identity_is_taken_after_the_reveal_never_on_the_deck_reference` carries its own
  positive control.
* **No engine shuffle, anywhere.** Probabilities come from `common.deck_odds`' shipped closed forms;
  a clause in `snapshot_coverage.NONDETERMINISTIC_CLAUSES` refuses rather than being simulated.
* **Truncation is never silent.** `Expectation.truncated` and the missing `total_probability` mass
  both report a capped enumeration.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`), never recalled — the printed text of each is
quoted at its constant below. Same primary seam as `test_apply_transitions.py`: a dict-backed Stat
Provider and hand-built zone dicts, no Pilot and no engine boot, so this runs DLL-free on both
platforms.
"""
from __future__ import annotations

import pytest

from common import apply_option as ao
from common import board_delta as bd
from common import board_expectation as be
from common import deck_odds
from common.cards import CardFunctions
from common.effects import CardEffects
from common.fetch_closure import multiset_classes
from common.option_equivalence import AREA_DECK, AREA_HAND, option_fingerprint
from common.scouting.provider import CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath
from common.strategy.context import _ATTACH, _PLAY

MAIN = bd.CONTEXT_MAIN
HAND = AREA_HAND
FIGHTING, PSYCHIC, COLORLESS = 6, 5, 0

# ── the pool, every row quoted from `data/EN_Card_Data.csv` ───────────────────────────────────────
#
#   1125 Master Ball        Item      "Search your deck for a Pokemon, reveal it, and put it into
#                                      your hand. Then, shuffle your deck."
#   1152 Poke Pad           Item      "Search your deck for a Pokemon that doesn't have a Rule Box,
#                                      reveal it, and put it into your hand. Then, shuffle your
#                                      deck. (Pokemon {ex}, Pokemon {V}, etc. have Rule Boxes.)"
#   1121 Ultra Ball         Item      "You can use this card only if you discard 2 other cards from
#                                      your hand. // Search your deck for a Pokemon, reveal it, and
#                                      put it into your hand. Then, shuffle your deck."
#   1231 Dawn               Supporter "Search your deck for a Basic Pokemon, a Stage 1 Pokemon, and
#                                      a Stage 2 Pokemon, reveal them, and put them into your hand.
#                                      Then, shuffle your deck."   <- an AND, hence three clauses
#   1141 Premium Power Pro  Item      "During this turn, attacks used by your {F} Pokemon do 30 more
#                                      damage..."  <- NO Effect Clauses at all (`card_effects.json`
#                                      returns nothing); the whole effect is the parsed
#                                      `CardStat.damageBoost` triple. The clause-less blind spot
#                                      `apply_option.footprints_writing_unhomed` names by card.
#   1122 Pokegear 3.0       Item      a `dig` fetch — the shipped reach predicate refuses it.
#   1119 Energy Search      Item      "Search your deck for a Basic Energy card..."
#   677 Riolu / 678 Mega Lucario ex — the standing single-hop worked example (`docs/rulebook.txt`
#                                      Appendix 1: Mega Lucario ex evolves from Riolu ALONE).
MASTER_BALL, POKE_PAD, ULTRA_BALL, DAWN, POWER_PRO, GEAR, ENERGY_SEARCH = (
    1125, 1152, 1121, 1231, 1141, 1122, 1119)
#   1225 Hilda            Supporter  "…an Evolution Pokemon **and** an Energy card" — a CONJUNCTION
#                                    whose two legs both match this file's pool and neither of which
#                                    reads `CardStat.stage`, which is why it is the conjunction
#                                    fixture rather than Dawn.
#   1142 Fighting Gong    Item       "…a Basic {F} Energy card **or** a Basic {F} Pokemon" — a UNION
#                                    the compendium had declared as a conjunction.
#   1210 Brock's Scouting Supporter  "up to 2 Basic Pokemon **or** 1 Evolution" — the EXCLUSIVE
#                                    either-or, which stays refused: different caps per branch.
#   1205 Cyrano           Supporter  "up to 3 Pokemon {ex}" — the multi-card delivery to HAND.
#   1086 Buddy-Buddy Poffin Item      "up to 2 Basic Pokemon with 70 HP or less" ONTO YOUR BENCH.
#   1126 Precious Trolley  Item       "any number of Basic Pokemon" onto the Bench — `amount: "all"`.
#   1206 Larry's Skill    Supporter  "Discard your hand and search your deck for..." — `discard_hand`,
#                                    a cost with no fixed count. BOGUS_COST is synthetic: a cost
#                                    value the compendium never declared, reachable no other way.
HILDA, GONG, BROCK, CYRANO, POFFIN, TROLLEY = 1225, 1142, 1210, 1205, 1086, 1126
LARRY, BOGUS_COST = 1206, 1194
#   675 Lunatone          Basic Pokemon — its draw is an ABILITY (`condition: solrock_in_play`), so
#                         PLAYING the body reveals nothing at all.
#   1071 Meowth ex        Basic Pokemon — a real on-bench-play trigger, but a `supporter` target and
#                         a `trigger` field, both of which `fetch_is_unconditional` rejects.
LUNATONE, MEOWTH_EX = 675, 1071
RIOLU, MEGA_LUC, MUNKIDORI = 677, 678, 112
E_F = 6

_ITEM, _SUPPORTER, _BASIC_ENERGY = 1, 3, 5

#: Every Pokemon row is a SOURCE claim audited field-for-field against `data/EN_Card_Data.csv` by
#: `tests/scouting/test_cardstat_fixture_facts.py`. Munkidori is HP **110** and Riolu HP **80**.
_STATS = {
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, ex=True,
                       energyType=FIGHTING, evolvesFrom="Riolu"),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=110, energyType=PSYCHIC),
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
    MEOWTH_EX: CardStat(MEOWTH_EX, name="Meowth ex", hp=170, ex=True, energyType=COLORLESS),
}

#: The committed `card_effects.json` rows for these cards, copied verbatim. `POWER_PRO` is absent on
#: purpose — that IS its row.
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
    # A cost value `COST_CARDS` has never heard of — the drift case, which no real card provides.
    BOGUS_COST: [{"kind": "fetch", "target": "pokemon", "zone": "deck", "cost": "discard_9"}],
    LUNATONE: [{"kind": "draw", "amount": 3, "condition": "solrock_in_play",
                "rider": "discard_basic_f_energy"}],
    MEOWTH_EX: [{"kind": "fetch", "target": "supporter", "zone": "deck",
                 "trigger": "on_bench_play"}],
}


def _ids_in_hand(cls, *, kept: int = 0) -> list:
    """The card ids this outcome class DELIVERED into my hand.

    `kept` is how many of my hand cards SURVIVE the play — the pre-play hand size minus the card
    being played, which has already left for the discard. These boards hold only the played card, so
    it is 0 and the whole post-reveal hand is the delivery."""
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


#: A board holding one Master Ball in hand over a deck whose UNSEEN Pokemon are 3 Riolu and 1 Mega
#: Lucario ex — two distinct card states over four copies, which is what makes "collapse by
#: Option-Equivalence identity, never by card identity" observable.
def _search_board(hand=(MASTER_BALL,), *, deck=None, prize=4):
    deck = deck if deck is not None else [RIOLU] * 3 + [MEGA_LUC] + [E_F] * 6 + list(hand)
    obs = _obs(_player(active=_body(RIOLU), hand=hand, prize=prize))
    return _model(obs, deck)


def _play_option(index=0):
    return {"type": _PLAY, "index": index}


# ── enumeration ───────────────────────────────────────────────────────────────────────────────────


def test_a_deck_search_enumerates_one_class_per_distinct_unseen_target():
    """Master Ball's *"Search your deck for a Pokémon"* over 3 Riolu + 1 Mega Lucario ex is **two**
    outcome classes, not four.

    That is `OutcomeClass`'s own contract — *"classes are enumerated by Option Equivalence identity
    (ADR-0091 fingerprints), not by card identity, so the branching factor is the number of decisions
    the reveal actually poses"*. Three identical Riolu pose ONE decision; `serial` is the only field
    ADR-0091 ignores, and it is the only field they differ on."""
    exp = be.expectation(_search_board(), _play_option())
    assert len(exp.classes) == 2
    assert len({c.fingerprint for c in exp.classes}) == 2


def test_the_basic_energy_in_the_deck_is_not_a_pokemon_target():
    """The pool is filtered by the SHIPPED reach predicate (`fetch_closure.fetch_target_matches`),
    not by a second matcher — ADR-0087's one-store rule. Positive control that the filter is doing
    work rather than passing everything: the same board's Energy Search DOES reach the {F} Energy
    that Master Ball cannot."""
    pokemon = be.expectation(_search_board(), _play_option())
    energy = be.expectation(_search_board(hand=(ENERGY_SEARCH,)), _play_option())
    assert len(pokemon.classes) == 2                        # Riolu, Mega Lucario ex — no Energy
    assert len(energy.classes) == 1                         # the {F} Energy alone


def test_poke_pad_cannot_reach_a_rule_box_body():
    """*"Search your deck for a Pokémon that doesn't have a Rule Box"* — Mega Lucario ex is a Mega
    Evolution Pokémon **ex**, so Poké Pad reaches Riolu alone where Master Ball reaches both. The
    `no_rule_box` leg is `fetch_closure._pokemon_body_matches`', asked through the same predicate."""
    exp = be.expectation(_search_board(hand=(POKE_PAD,)), _play_option())
    assert len(exp.classes) == 1


def test_class_probabilities_are_deck_odds_availability_weights_normalised():
    """Weighted by `deck_odds.p_contains` — the shipped ADR-0029 hypergeometric prize split — and by
    nothing else. Asserted against a recomputation of the same shipped function rather than against
    a hard-coded float, so a change to the oracle moves both sides of this test together."""
    model = _search_board()
    exp = be.expectation(model, _play_option())
    hidden, left = model.mine.prizes_hidden, model.mine.deck_count
    unseen = model.mine.unseen_counts
    want = {cid: deck_odds.p_contains(unseen[cid], hidden, left) for cid in (RIOLU, MEGA_LUC)}
    total = sum(want.values())
    got = {c.fingerprint: c.probability for c in exp.classes}
    assert abs(sum(got.values()) - 1.0) < 1e-9
    # Three Riolu against one Mega Lucario ex: the commoner class must carry the larger weight, and
    # the exact ratio must be the oracle's.
    ordered = sorted(exp.classes, key=lambda c: -c.probability)
    assert abs(ordered[0].probability - want[RIOLU] / total) < 1e-9
    assert abs(ordered[1].probability - want[MEGA_LUC] / total) < 1e-9


def test_each_class_carries_the_POST_REVEAL_model():
    """The class's ``model`` is the board *after the reveal resolves* — not after the `_PLAY` step.

    Three writes, each checked: the searched card is in my hand, the Item that found it is in my
    discard (`docs/rulebook.txt` L78 — *"Cards taken out of play go to the discard pile"*), and my
    deck is one card shorter because that copy is now visible."""
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
    """The composer holds the pre-state while it evaluates alternatives, so a transition that edited
    in place would corrupt every sibling branch (`apply_option.apply_option`'s own contract)."""
    model = _search_board()
    hand, deck = model.mine.hand_ids, model.mine.deck_count
    be.expectation(model, _play_option())
    assert model.mine.hand_ids == hand and model.mine.deck_count == deck


def test_a_supporter_search_spends_the_supporter_allowance_and_an_item_does_not():
    """`docs/rules.md` §3 — one Supporter per turn, Items uncapped. Dawn is the Supporter and it is
    ALSO the multi-clause refusal below, so the allowance is asserted through a single-clause
    Supporter shim rather than by loosening Dawn's real row."""
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


# ── the branching cap, and the truncation that is never silent ────────────────────────────────────


def test_the_branching_cap_is_a_named_structural_constant():
    """`BRANCH_CAP` is the named constant Issue #383 requires and `Expectation`'s docstring defers to
    (*"the cap value is T4's"*). Its VALUE is derived from the measured menu-width P95, not tuned —
    the module docstring carries the derivation; this asserts only that it is named, positive, and
    the default the enumerator actually uses."""
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
    # The gap IS the truncation — a capped enumeration that read as a complete one is the "no silent
    # caps" failure this project's whole telemetry discipline exists to prevent.
    assert exp.total_probability < 1.0


def test_the_cap_keeps_the_HIGHEST_mass_classes():
    """Truncation drops the tail, never an arbitrary slice: the surviving classes are the most
    probable ones, so a capped `expected()` is the expectation conditional on the LIKELIEST
    branches. Deterministic on ties (card id), so two processes enumerate one set — the same
    reproducibility guarantee `option_equivalence.class_representatives` keeps."""
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
    """`Expectation.expected` is the frozen 1-ply ordering number and it divides by
    `total_probability`, so a truncated enumeration reports the expectation CONDITIONAL on the
    branches that survived — never one biased toward zero by treating dropped mass as worthless."""
    exp = be.expectation(_search_board(), _play_option(), cap=1)
    assert exp.truncated == 1
    assert abs(exp.expected(lambda m: 7.0) - 7.0) < 1e-9      # renormalised, not scaled by the mass


def test_a_cap_below_one_raises_rather_than_manufacturing_a_zero_class_expectation():
    """A cap of 0 would return an Expectation with no classes — the exact shape the empty-pool
    refusal exists to prevent, and one whose `expected()` raises deep inside the ordering loop. That
    is caller error rather than a modelling gap, so it raises where a gap refuses (the same split
    `apply_option.apply_option` keeps for a TERMINAL option)."""
    with pytest.raises(ValueError, match="at least one class"):
        be.expectation(_search_board(), _play_option(), cap=0)


def test_expected_raises_on_an_un_enumerated_effect():
    """The shipped zero-mass `ValueError`. An Expectation with no classes is an UN-ENUMERATED effect,
    and 0.0 is a real answer that would read as a worthless one."""
    with pytest.raises(ValueError):
        ao.Expectation().expected(lambda m: 1.0)


def test_an_empty_pool_refuses_rather_than_returning_a_zero_class_expectation():
    """The same argument one layer up: a search whose targets are all provably outside the deck is a
    fact worth REFUSING on (always-expand), not a zero-class Expectation whose `expected()` would
    then raise deep inside the ordering loop."""
    with pytest.raises(bd.Unmodellable, match="no target"):
        be.expectation(_search_board(deck=[E_F] * 6 + [MASTER_BALL]), _play_option())


# ── the identity, and the deck-reference rule it must not break ───────────────────────────────────


def test_the_class_identity_is_taken_after_the_reveal_never_on_the_deck_reference():
    """Issue #263 §*duplicate-cards* forbids a partial fingerprint over a face-down zone: *"a
    deck-referencing pick is unfingerprintable and joins NO class"*.

    **Positive control, both directions.** The pick the engine would pose — an option naming
    `AreaType.DECK` — fingerprints to `None` on the pre-reveal board, which is the rule working. The
    same card fingerprints to a real identity once it is in my HAND, which is where this module takes
    it. So the classes are formed on revealed state and the blind rule is never bent."""
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


# ── the refusals: every one of them names a shipped reason ────────────────────────────────────────


def test_a_card_with_no_revealing_clause_is_not_an_expectation_node():
    with pytest.raises(bd.Unmodellable, match="no `draw`/`fetch`"):
        be.expectation(_search_board(hand=(POWER_PRO,)), _play_option())


def test_a_conjunction_enumerates_one_card_per_leg_and_SKIPS_an_empty_one():
    """Dawn prints *"Search your deck for a Basic Pokémon, a Stage 1 Pokémon, **and** a Stage 2
    Pokémon"* — three legs that are one CONJUNCTION.

    On this board only the Basic leg can find anything (the pool is Riolu / Mega Lucario ex / {F}
    Energy, and neither Pokémon carries a `stage`), so two legs are EMPTY. The engine skips an empty
    bucket rather than failing the card — `chain_overrides.json`'s own provenance for 1231 records
    *"empty buckets skip with a tac bump"* — so the play still resolves and delivers what it could
    find. Refusing here would refuse a card the engine resolves happily.

    Measured on the real corpus, this is not an edge case: Dawn's leg product is 0 on **all 8** of
    its steps, precisely because two of its three legs are empty on every one."""
    exp = be.expectation(_search_board(hand=(DAWN,)), _play_option())
    assert [tuple(sorted(_ids_in_hand(c))) for c in exp.classes] == [(RIOLU,)]


def test_a_conjunction_takes_the_CROSS_PRODUCT_when_several_legs_are_live():
    """Hilda prints *"Search your deck for an Evolution Pokémon **and** an Energy card"* — two legs
    that both find something here, so the classes are the product: one Evolution × one Energy.

    Hilda is the conjunction fixture on purpose (`board_expectation`'s own constraint note): both its
    legs match the pool this file already builds and **neither reads `CardStat.stage`**, so the case
    needs no new stage fixture."""
    exp = be.expectation(_search_board(hand=(HILDA,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(E_F, MEGA_LUC)]        # the only Evolution x the only Energy class
    assert all(len(c.fingerprint) == 2 for c in exp.classes), "both delivered cards form the identity"


def test_a_union_enumerates_ONE_card_over_the_pooled_legs():
    """Fighting Gong prints *"Search your deck for a Basic {F} Energy card **or** a Basic {F}
    Pokémon"* — one card from the UNION of two legs, which the engine settles with a single
    `anyOf`-filtered op rather than two picks.

    So the classes are one-card, exactly as a single-leg search's are, over a pool that is the union
    of both legs' — Riolu from the Pokémon leg and {F} Energy from the Energy leg. This is the shape
    the compendium had backwards: read as a conjunction it would have claimed the card delivers
    two."""
    exp = be.expectation(_search_board(hand=(GONG,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(E_F,), (RIOLU,)]
    assert all(len(c.fingerprint) == 1 for c in exp.classes)


def test_a_multi_card_delivery_to_HAND_enumerates_multisets_not_subsets():
    """Cyrano is *"Search your deck for up to 3 Pokémon {ex}"* — a delivery of THREE cards.

    The classes are MULTISETS, not subsets, and the difference is not academic: a pool may hold
    several copies of one card, and taking two of them is a legal, distinct outcome. Measured on the
    real corpus, Cyrano's pool is **one distinct card id on all 4 of its steps**, where a subset
    enumerator returns exactly one class and is simply wrong about what the card delivers.

    Cyrano hunts `pokemon_ex`, and this pool holds exactly one — Mega Lucario ex — so the delivery
    CLAMPS to what the pool actually contains rather than being padded to three. That clamp is the
    engine's own (`min(max, matches)`), and it is the real corpus shape rather than a contrived one:
    the same single-distinct-id pool is what all four of Cyrano's steps present."""
    exp = be.expectation(_search_board(hand=(CYRANO,)), _play_option())
    delivered = sorted(tuple(sorted(_ids_in_hand(c))) for c in exp.classes)
    assert delivered == [(MEGA_LUC,)]
    assert all(len(c.fingerprint) == 1 for c in exp.classes)


def test_a_multi_card_delivery_takes_SEVERAL_COPIES_of_one_card_when_the_pool_holds_them():
    """The case a subset enumerator gets wrong. Master Ball is a one-card search, so this asks the
    enumerator directly on the pool that board presents: 3 Riolu and 1 Mega Lucario ex.

    A 3-card delivery over it has two shapes — three Riolu, or two Riolu and the Mega — and BOTH
    take a card more than once. A subset reading would offer only `(Riolu, Mega)` and would silently
    claim the deck cannot produce a third body it plainly can."""
    pool = {RIOLU: 3, MEGA_LUC: 1}
    assert multiset_classes(pool, 3) == [(RIOLU, RIOLU, RIOLU), (RIOLU, RIOLU, MEGA_LUC)] or \
        sorted(multiset_classes(pool, 3)) == sorted([(RIOLU, RIOLU, RIOLU),
                                                        (RIOLU, RIOLU, MEGA_LUC)])
    assert len(multiset_classes(pool, 3)) == 2


def test_a_multi_card_class_weighs_each_card_at_the_multiplicity_it_needs():
    """A class that takes TWO copies of a card needs two copies still in the deck, which is
    `p_contains_at_least(..., 2)` and not `p_contains`. Reading it with the >=1 form would
    over-report every duplicate-bearing class.

    Asserted against the closed form directly rather than against a golden number, so the assertion
    survives a re-tuned prize split."""
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
    # …and a one-card class is bit-for-bit the shipped `p_contains`, which is why nothing moved.
    assert be._class_weight(model, (RIOLU,)) == \
        deck_odds.p_contains(unseen.get(RIOLU, 0), hidden, left)


def test_the_multiset_enumerator_degenerates_to_todays_classes_at_one_card():
    """The identity that stops the widening from regressing the single-card path: `multiset_classes`
    at m=1 is exactly one class per distinct pool card, which is what shipped before."""
    pool = {RIOLU: 3, MEGA_LUC: 1, E_F: 6}
    assert multiset_classes(pool, 1) == [(E_F,), (RIOLU,), (MEGA_LUC,)][::1] or \
        sorted(multiset_classes(pool, 1)) == sorted([(E_F,), (RIOLU,), (MEGA_LUC,)])
    # A copy count BOUNDS the multiplicity — one Mega Lucario ex can never arrive twice.
    assert all(k.count(MEGA_LUC) <= 1 for k in multiset_classes(pool, 3))
    # …and the delivery is clamped by what the pool actually holds, never padded.
    assert multiset_classes({MEGA_LUC: 1}, 3) == [(MEGA_LUC,)]
    assert multiset_classes({}, 3) == []


def test_a_delivery_to_the_BENCH_still_refuses_and_now_says_so_for_the_right_reason():
    """Buddy-Buddy Poffin delivers to the Bench, which is the deploy transition with its Bench cap
    and Stadium-trigger gate — Issue #410's work, not this node's. It refuses.

    What changes is WHICH gate catches it. `amount` used to fire first, filing 41 corpus steps under
    "the search delivers more than one card"; now the multi-card shape is modelled and the refusal
    lands on `dest`, which is the reason that actually describes it. A backlog is only actionable if
    each row names the work it is waiting on."""
    with pytest.raises(bd.Unmodellable, match="`dest`"):
        be.expectation(_search_board(hand=(POFFIN,)), _play_option())


def test_an_amount_of_all_still_refuses_because_it_names_no_number():
    """`amount: "all"` is not a count the enumerator can range over without a pool to resolve it
    against, and its only carriers deliver to the Bench (Precious Trolley), which refuses anyway.
    Issue #410 owns it. Refused explicitly rather than falling through to a catch-all."""
    with pytest.raises(bd.Unmodellable, match="`amount`"):
        be.expectation(_search_board(hand=(TROLLEY,)), _play_option())


def test_an_exclusive_either_or_still_refuses_rather_than_guessing_a_cap():
    """The third shape, and the one that stays refused. Brock's Scouting is *"up to 2 Basic Pokémon
    **or** 1 Evolution"* — `choice` on both legs but different budgets, so there is no single shared
    cap to enumerate over and the engine gives it its own op (`xDeckToHandEitherOr`)."""
    with pytest.raises(bd.Unmodellable, match="either-or"):
        be.expectation(_search_board(hand=(BROCK,)), _play_option())


def test_a_costed_search_refuses_because_the_cost_names_no_target():
    """Ultra Ball is *"You can use this card only if you discard 2 other cards from your hand"*. WHICH
    two is chosen at a follow-up select, exactly as `board_delta._play`'s 63 target-at-a-select
    refusals are, so the cost's `my_hand_ids` / `my_discard_contents` writes cannot be placed."""
    with pytest.raises(bd.Unmodellable, match="cost"):
        be.expectation(_search_board(hand=(ULTRA_BALL,)), _play_option())


def test_a_dig_refuses_through_the_shipped_reach_predicate():
    """Pokégear 3.0 looks at the top 7 rather than the whole deck, so it may MISS a card still in
    there. `fetch_closure.fetch_is_unconditional` is the shipped answer to *"is this the
    unconditional, decidable whole-deck search every reach consumer's model assumes?"* and this
    module asks it rather than re-spelling the four fields it checks."""
    with pytest.raises(bd.Unmodellable, match="unconditional"):
        be.expectation(_search_board(hand=(GEAR,)), _play_option())


def test_a_draw_refuses_rather_than_projecting_an_n_card_window_onto_one_card():
    """`deck_odds`' shipped closed forms answer *"P(at least one target in the window)"*, not the
    JOINT distribution over which n cards arrived. Enumerating single-card classes for an n-card draw
    would be a biased conditional — systematically the highest-count cards — which is a different
    failure from the fetch case's honest lower bound, so it refuses instead."""
    stats = {**_STATS}
    stats[MASTER_BALL] = CardStat(MASTER_BALL, synthetic=True, name="Draw shim", cardType=_ITEM)
    combat = CombatMath(DictCardStatProvider(stats), functions=CardFunctions({}), transients=None,
                        effects=CardEffects({MASTER_BALL: [{"kind": "draw", "amount": 4}]}))
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]))
    model = StateModel.build(obs, combat=combat, deck=[RIOLU] * 3 + [MASTER_BALL])
    with pytest.raises(bd.Unmodellable, match="draw"):
        be.expectation(model, _play_option())


def test_a_shuffling_clause_is_never_simulated():
    """`snapshot_coverage.NONDETERMINISTIC_CLAUSES` — the engine has no deal-seed, so a simulated
    shuffle is ONE SAMPLE rather than a distribution (Issue #178's defect) and it breaks the
    deterministic replay both ADR-0072 gates depend on."""
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
    """Issue #382 measured 14 580 of 14 581 modelled steps at `SelectContext.MAIN`. An option posed
    INSIDE a card's effect is one leg of that CARD's step, so it carries writes belonging to the card
    rather than to the option's own kind — the same boundary, asked once."""
    obs = _obs(_player(active=_body(RIOLU), hand=[MASTER_BALL]), context=37)
    model = _model(obs, [RIOLU] * 3 + [MASTER_BALL])
    with pytest.raises(bd.Unmodellable, match="MAIN"):
        be.expectation(model, _play_option())


def test_a_kind_other_than_PLAY_refuses():
    """A reveal riding an `_ABILITY` or an `_ATTACH` does not put the source card in my discard, so
    the structural floor this module writes around the reveal does not hold for it."""
    with pytest.raises(bd.Unmodellable, match="kind"):
        be.expectation(_search_board(), {"type": _ATTACH, "index": 0})


# ── the COST: applied before the search, from an oracle the caller supplies ────────────────────────


def _shed_first(n):
    """A stand-in `shed` oracle: take the first `n` hand cards that are not the one being played.

    Deliberately dumb. The REAL oracle is `Pilot.cost_shed_indices`, which asks
    `needs.cheapest_removal` — the equation that decides the live discard. This node's contract is
    only that it applies whatever set it is handed, so the tests must not depend on which set."""
    def shed(model, option, picks):
        hand = ((model.source_obs["current"]["players"])[0].get("hand") or ())
        return [i for i in range(len(hand)) if i != option.get("index")][:n]
    return shed


def test_a_costed_search_refuses_when_no_shed_oracle_is_supplied_and_NAMES_the_seam():
    """The fail-closed direction, and the one that matters. Pricing the cost UNPAID would over-value
    every Ultra Ball by the two cards it does not charge for, so the node refuses instead — and the
    refusal names the missing seam rather than the card, because supplying it is the caller's job."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    with pytest.raises(bd.Unmodellable, match="no `shed` oracle"):
        be.expectation(board, _play_option())


def test_a_costed_search_ENUMERATES_once_the_oracle_is_supplied():
    """Ultra Ball is 65 of the corpus's 69 cost-refused steps and sits in all five shipped decks."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    exp = be.expectation(board, _play_option(), shed=_shed_first(2))
    assert exp.classes and exp.total_probability == pytest.approx(1.0)


def test_the_cost_is_charged_BEFORE_the_search_so_a_found_card_cannot_pay_for_itself():
    """The engine's own order — `chain_overrides.json` gives 1121 `play: [costHandTrash,
    effectDeckToHandAndShuffle]`. Observable rather than cosmetic: charging afterwards would let a
    delivered card be discarded to pay for the search that delivered it.

    Asserted on the resulting board: the two paid cards and the played card are all in my discard,
    the delivered card is in my hand, and the hand is exactly the delivery."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    exp = be.expectation(board, _play_option(), shed=_shed_first(2))
    for cls in exp.classes:
        me = (cls.model.source_obs["current"]["players"])[0]
        assert [c["id"] for c in me["discard"]].count(RIOLU) == 2      # both paid cards
        assert ULTRA_BALL in [c["id"] for c in me["discard"]]          # ...and the source card
        assert len(me["hand"]) == 1 and me["handCount"] == 1           # only the delivery remains


def test_the_cost_never_takes_the_card_being_played():
    """The engine's gate is `handOthers` — *"discard 2 OTHER cards"*. An oracle naming the played
    card's own index has it dropped, which then makes the payment short and the play refuse rather
    than silently discarding the card mid-play."""
    board = _search_board(hand=(ULTRA_BALL, RIOLU, RIOLU))
    def names_the_played_card(model, option, picks):
        return [0, 1]                                    # index 0 IS the Ultra Ball being played
    with pytest.raises(bd.Unmodellable, match="usable hand index"):
        be.expectation(board, _play_option(), shed=names_the_played_card)


def test_an_unpayable_cost_refuses_as_an_ILLEGAL_play_not_a_free_one():
    """A one-card hand cannot pay "discard 2 other cards", so the play is not legal on this board —
    the engine would never offer it. Refusing keeps an unreal option off the menu; pricing it as
    merely cheap would put one on with a positive delta."""
    with pytest.raises(bd.Unmodellable, match="usable hand index"):
        be.expectation(_search_board(hand=(ULTRA_BALL,)), _play_option(), shed=_shed_first(2))


def test_a_cost_with_no_fixed_count_refuses_by_NAME():
    """`COST_CARDS` maps `discard_hand` and `bottom_2` to None, for two different reasons the
    refusal states: a whole-hand discard has no constant count, and `bottom_2` returns cards to the
    DECK — which moves `unseen_counts` and would invalidate the very pool being enumerated."""
    board = _search_board(hand=(LARRY,))
    with pytest.raises(bd.Unmodellable, match="no fixed card count"):
        be.expectation(board, _play_option(), shed=_shed_first(2))


def test_an_undeclared_cost_value_fails_CLOSED():
    """Vocabulary drift, in the cost dimension — the same fail-closed rule the unknown-key gate
    keeps. A cost nobody declared a count for must refuse, never charge 0."""
    board = _search_board(hand=(BOGUS_COST,))
    with pytest.raises(bd.Unmodellable, match="not in `snapshot_coverage.COST_CARDS`"):
        be.expectation(board, _play_option(), shed=_shed_first(2))


# ── the DECLINES, each landing on the gate that describes it ───────────────────────────────────────


def test_a_reveal_declared_on_a_BODY_is_an_ability_and_refuses_as_one():
    """**Modelling this would be WRONG, not under-scoped — which is why it gets its own gate.**

    Lunatone's `{"kind": "draw", "condition": "solrock_in_play"}` is an ABILITY. An Ability does not
    fire because the body was PLAYED; it is a separate `_ABILITY` option on the menu. So deploying
    Lunatone reveals nothing, and an expectation node over its draw would price a reveal that never
    happens.

    Before the gate order was fixed these landed in "only an Item or a Supporter", which is true of
    them and says nothing about the actual defect."""
    with pytest.raises(bd.Unmodellable, match="is an ABILITY"):
        be.expectation(_search_board(hand=(LUNATONE,)), _play_option())


def test_an_on_bench_play_trigger_passes_the_ability_gate_and_refuses_on_its_CLAUSE():
    """Meowth ex is the shape that DOES ride the `_PLAY` — `trigger: on_bench_play` fires when the
    body is benched. So it passes the ability gate, and then refuses on what is actually wrong with
    it: `fetch_is_unconditional` rejects both the `trigger` field and, behind it, a `supporter`
    target that resolves for deadness and never for reach.

    The two assertions together are the point: the gate discriminates rather than catching
    everything on one side of the Item/Supporter line."""
    with pytest.raises(bd.Unmodellable, match="not the unconditional"):
        be.expectation(_search_board(hand=(MEOWTH_EX,)), _play_option())


def test_the_card_type_floor_is_now_UNREACHABLE_for_the_shipped_pool():
    """The floor survives as a structural backstop and should catch nothing real.

    Its sentence — *"only an Item or a Supporter resolves to my discard on a search"* — is about
    where the SOURCE card lands, which is a fact about the play rather than about the reveal. Every
    shipped card that used to land here now refuses on its own defect first: 11 steps at the ability
    gate (Lunatone, Fezandipiti ex) and 12 at the clause gates (Meowth ex), leaving 0 at the floor.
    Asserted by construction — a body whose reveal is a legitimate on-bench-play trigger with an
    otherwise clean clause is the only thing that could reach it, and no such card ships."""
    from common.effects import CardEffects
    from common.fetch_closure import fetch_is_unconditional
    eff = CardEffects.load()
    reachable = []
    for cid in (LUNATONE, MEOWTH_EX, 140):                # the three real carriers
        for clause in eff.clauses(cid):
            if clause.get("trigger") == "on_bench_play" and fetch_is_unconditional(clause):
                reachable.append(cid)
    assert reachable == [], f"a card can now reach the card-type floor: {reachable}"
