"""WP7 — `common.fetch_closure`: the tutor/recycle/search graph + clause predicates lifted OUT of
the Pilot into one pure, Pilot-independent module (ADR-0065). The gamble gain side and the card-worth
keep-cost read ONE implementation; these tests pin the extraction as behaviour-preserving by asserting
PARITY between the pure functions and the ground-truth Pilot delegators on the real shipped decks.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _accessors(pilot):
    stat_of = lambda c: pilot.stats.get(c) if pilot.stats else None
    clauses_of = lambda c: pilot.effects.clauses(c) if pilot.effects else ()
    return stat_of, clauses_of


@pytest.mark.req("REQ-WORTH-0002")
def test_fetch_target_matches_is_the_one_clause_predicate():
    """`fetch_closure.fetch_target_matches(clause, stat)` is the SAME predicate the Pilot exposes as
    `_fetch_target_matches` — Mega Lucario ex (678) matches a `mega` clause and NOT a `basic_pokemon`
    one; a {F} Basic Energy (6) matches a {F}-locked `basic_energy` clause and not a {W}-locked one."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    ml_ex = ml.stats.get(678)
    energy = ml.stats.get(6)
    assert fetch_closure.fetch_target_matches({"target": "mega"}, ml_ex) is True
    assert fetch_closure.fetch_target_matches({"target": "basic_pokemon"}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "energy_type": 6}, energy) is True
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "energy_type": 5}, energy) is False
    assert fetch_closure.fetch_target_matches({"target": "mega"}, None) is False
    # parity with the Pilot delegator on every card of the deck, every target class
    for cid in set(ml.deck):
        st = ml.stats.get(cid)
        for target in ("basic_energy", "energy", "mega", "evolution", "pokemon", "basic_pokemon"):
            clause = {"target": target}
            assert fetch_closure.fetch_target_matches(clause, st) == ml._fetch_target_matches(clause, st)


@pytest.mark.req("REQ-WORTH-0002")
def test_trigger_and_dig_clauses_are_never_closure_edges():
    """A ``trigger``-gated fetch (Meowth ex's on-bench-play Supporter grab) or a ``dig`` (Pokégear's
    top-7 look) is NOT the unconditional whole-deck search the closure model assumes — the predicate
    rejects such a clause outright, even when its target class would otherwise match. Previously both
    carriers fell through only because no ``supporter`` branch existed; this pins the rejection as
    load-bearing, so a future branch (or a new trigger/dig clause on a handled target) cannot silently
    promote a conditional fetch to a deterministic out."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    ml_ex = ml.stats.get(678)
    energy = ml.stats.get(6)
    assert fetch_closure.fetch_target_matches({"target": "mega"}, ml_ex) is True
    assert fetch_closure.fetch_target_matches({"target": "mega", "dig": 7}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "mega", "trigger": "on_bench_play"}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "dig": 7}, energy) is False
    # the real carriers (card_effects.json): Meowth ex 1071 (trigger) and Pokégear 1122 (dig) — a
    # shuffled-away Supporter's re-access outs must not count either as a deck-search tutor
    stat_of, clauses_of = _accessors(ml)
    for cid in (1071, 1122):
        for cl in clauses_of(cid):
            if cl.get("kind") == "fetch":
                assert fetch_closure.fetch_target_matches(cl, ml.stats.get(1182)) is False


# ── the widened target vocabulary (Issue #301) ────────────────────────────────────────────────────
# Asserted against hand-built `CardStat` rows rather than a shipped deck, deliberately: these are
# claims about the PREDICATE, and this module's whole charter is to be Pilot-independent. The
# real-deck parity walks above already pin that the predicate and the Pilot agree.

def _stat(**kw):
    from common.scouting.provider import CardStat
    return CardStat(cardId=kw.pop("cardId", 1), **kw)


#: One row per class the new targets name. `cardType` 0 = Pokémon, 1 Item, 2 Tool, 3 Supporter,
#: 4 Stadium, 5 Basic Energy (`cg.api.CardType`).
_ROWS = {
    "basic":     _stat(cardId=10, hp=70, stage="basic", cardType=0),
    "stage1":    _stat(cardId=11, hp=120, stage="stage1", evolvesFrom="Scraggy", cardType=0),
    "stage2":    _stat(cardId=12, hp=180, stage="stage2", stage2=True, evolvesFrom="Drakloak",
                       cardType=0),
    "tera":      _stat(cardId=13, hp=230, stage="basic", tera=True, cardType=0),
    "ex":        _stat(cardId=14, hp=230, stage="basic", ex=True, cardType=0),
    "item":      _stat(cardId=15, cardType=1),
    "tool":      _stat(cardId=16, cardType=2),
    "supporter": _stat(cardId=17, cardType=3),
    "stadium":   _stat(cardId=18, cardType=4),
    "energy":    _stat(cardId=19, cardType=5, energyType=6),
}


@pytest.mark.req("REQ-WORTH-0002")
@pytest.mark.parametrize("target,hits", [
    ("stage1", {"stage1"}),
    ("stage2", {"stage2"}),
    ("tera", {"tera"}),
    ("pokemon_ex", {"ex"}),
    ("item", {"item"}),
    ("tool", {"tool"}),
    ("stadium", {"stadium"}),
])
def test_the_widened_target_classes_each_match_exactly_their_class(target, hits):
    """Issue #301's seven new REACH-eligible target classes, one row per class of the pool. Each is
    a class the compendium now names (Hyper Aroma `stage1`, Dawn `stage2`, Tera Orb `tera`, Cyrano
    `pokemon_ex`, Secret Box `item`/`tool`/`stadium`) and each must match ITS class and nothing else
    — a target that over-matches fabricates a closure out, which is the one direction this module
    forbids. The eighth, `any`, is deadness-only and has its own test below."""
    from common import fetch_closure
    got = {name for name, stat in _ROWS.items()
           if fetch_closure.fetch_target_matches({"target": target}, stat)}
    assert got == hits


# ── the same two classes, against PRODUCTION rows (Issue #408) ────────────────────────────────────
# The test above builds its own `CardStat`, which is how `stage1`/`stage2` stayed green for a year
# while matching nothing on any real board: `CardStat.stage` was never written, so the fixture was
# supplying a value the provider could not emit. A class predicate has to be asserted against a row the
# provider actually produced, or the fixture is grading itself.

#: The hydrapple deck's own line — Dawn (1231), the one card in a shipped deck naming these classes,
#: fetches all three rungs of it. Applin is the POSITIVE CONTROL: a Basic of the SAME line must match
#: neither class, so a predicate that had degenerated to "any Pokémon" fails here rather than
#: silently over-reaching. Read through the production provider, not `_shipped_pilot` — hydrapple is
#: a deck with no `strategy.py`, and these are pool facts anyway.
APPLIN, DIPPLIN, HYDRAPPLE_EX = 149, 93, 150


@pytest.fixture(scope="module")
def real_stats():
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    return stats


@pytest.mark.req("REQ-WORTH-0002")
def test_the_stage_classes_match_real_provider_rows(real_stats):
    """`stage1` reaches a real Stage 1 and `stage2` a real Stage 2, read off the production provider.

    Before `CardStat.stage` was populated both comparisons were unsatisfiable, so every assertion
    here returned False — 461 cards' worth of nothing, on every board. The Basic leg is what keeps
    the fix honest in the other direction."""
    from common import fetch_closure
    applin, dipplin, hydrapple = (real_stats.get(APPLIN), real_stats.get(DIPPLIN),
                                  real_stats.get(HYDRAPPLE_EX))
    assert (applin.stage, dipplin.stage, hydrapple.stage) == ("basic", "stage1", "stage2")
    for target, expected in (("stage1", dipplin), ("stage2", hydrapple)):
        clause = {"target": target}
        matched = [s for s in (applin, dipplin, hydrapple)
                   if fetch_closure.fetch_target_matches(clause, s)]
        assert matched == [expected], target


@pytest.mark.req("REQ-WORTH-0002")
def test_dawns_shipped_clauses_reach_the_line_they_name(real_stats):
    """End-to-end on the real carrier: Dawn (1231) declares `basic_pokemon` / `stage1` / `stage2`
    (Issue #301 got the DATA right; the reader was blind), and each leg must now reach exactly its
    rung of the Applin -> Dipplin -> Hydrapple ex line. Both the clause rows and the stat rows come
    from shipped artefacts, so neither side of the match is authored by this test."""
    from common import fetch_closure
    from common.effects import CardEffects
    clauses = [cl for cl in CardEffects.load().clauses(1231) if cl.get("kind") == "fetch"]
    by_target = {cl["target"]: cl for cl in clauses}
    assert set(by_target) == {"basic_pokemon", "stage1", "stage2"}
    for target, cid in (("basic_pokemon", APPLIN), ("stage1", DIPPLIN), ("stage2", HYDRAPPLE_EX)):
        assert fetch_closure.fetch_target_matches(by_target[target],
                                                  real_stats.get(cid)) is True, target
    # …and no leg is a blanket "any Pokémon": the Stage 2 is out of reach of the Basic clause.
    assert fetch_closure.fetch_target_matches(by_target["basic_pokemon"],
                                              real_stats.get(HYDRAPPLE_EX)) is False


@pytest.mark.req("REQ-WORTH-0002")
def test_the_deadness_only_classes_resolve_for_deadness_and_refuse_for_reach():
    """`FETCH_DEADNESS_ONLY_TARGETS` — the two classes that answer *"is anything left to find?"* and
    never *"can this get me X?"*. `supporter` is ADR-0073's gate; `any` names no class at all, and
    reach's endorsement set is made of classes. Gated in the PREDICATE, not left to the doctrine's
    target filter, so neither guarantee rests on one caller remembering to apply it.

    `any` matching EVERY row under deadness is the point: a class-less dig is dead only on an empty
    zone, which is the true (and useless-in-practice) answer rather than a fabricated one."""
    from common import fetch_closure as fc
    assert fc.FETCH_DEADNESS_ONLY_TARGETS == {"supporter", "any"}
    assert fc.FETCH_DEADNESS_ONLY_TARGETS <= fc.FETCH_DEADNESS_TARGETS
    assert not (fc.FETCH_DEADNESS_ONLY_TARGETS & fc.FETCH_POKEMON_TARGETS)
    for target in sorted(fc.FETCH_DEADNESS_ONLY_TARGETS):
        reach = {n for n, s in _ROWS.items() if fc.fetch_target_matches({"target": target}, s)}
        assert reach == set(), f"{target} resolved for REACH"
    assert {n for n, s in _ROWS.items()
            if fc.fetch_target_matches({"target": "any"}, s, deadness=True)} == set(_ROWS)
    assert {n for n, s in _ROWS.items()
            if fc.fetch_target_matches({"target": "supporter"}, s, deadness=True)} == {"supporter"}


@pytest.mark.req("REQ-WORTH-0002")
def test_a_conditioned_fetch_is_never_a_reach_edge():
    """A board GATE (Call Bell's going-second-turn-1, Hassel's post-KO) makes the search conditional,
    exactly as `dig` and `trigger` do: the closure's model is an UNCONDITIONAL whole-deck search, so
    counting a gated one as an out over-claims. Deadness asks the opposite question — *is anything
    left to find?* — and a gate cannot put cards back in the deck, so it is admissible there."""
    from common import fetch_closure
    clause = {"target": "pokemon", "condition": "going_second_first_turn"}
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"]) is False
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"], deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_a_name_family_fetch_reaches_nothing_until_a_family_oracle_exists():
    """The `name_family` ruling (Issue #301, cross-posted from Issue #306), as the fail-CLOSED guard
    it has to be. Hop's Bag searches for a Basic **Hop's** Pokémon; the compendium records that
    restriction, and no build-time family index exists for the closure to decide membership against.
    Ignoring the field would let the clause read as *any* Basic — a fabricated out on every Basic in
    the deck. So reach REFUSES the clause outright; deadness ignores the restriction, which only
    widens the "is anything left?" set and can therefore suppress a claim, never invent one."""
    from common import fetch_closure
    clause = {"target": "basic_pokemon", "name_family": "Hop's"}
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"]) is False
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"], deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_the_pokemon_side_predicates_apply_to_every_pokemon_class():
    """`no_rule_box`, `hp_max` and `no_ability` are properties of the TARGET BODY, not of the class
    that names it, so they hold for every Pokémon class rather than only for the two that happened to
    carry them first. One predicate, applied uniformly — a `mega`/`stage1`/`tera` clause that grew an
    HP ceiling would otherwise silently ignore it."""
    from common import fetch_closure as fc
    ex_stage2 = _stat(cardId=20, hp=340, stage="stage2", stage2=True, ex=True,
                      evolvesFrom="Dreepy", hasAbility=True, cardType=0)
    assert fc.fetch_target_matches({"target": "stage2"}, ex_stage2) is True
    assert fc.fetch_target_matches({"target": "stage2", "no_rule_box": True}, ex_stage2) is False
    assert fc.fetch_target_matches({"target": "stage2", "hp_max": 200}, ex_stage2) is False
    assert fc.fetch_target_matches({"target": "stage2", "no_ability": True}, ex_stage2) is False
    assert fc.fetch_target_matches({"target": "pokemon_ex", "hp_max": 200}, ex_stage2) is False
    assert fc.fetch_target_matches({"target": "evolution", "hp_max": 400}, ex_stage2) is True


def _compendium_fetch_clauses():
    """``{card id: [its fetch clauses]}`` off the COMMITTED compendium. One loader for every
    compendium-wide assertion below — a second `json.loads` walk beside it is the drift ADR-0087
    charges for, in miniature."""
    import json
    from common import snapshot_coverage
    payload = json.loads((REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    return {cid: [cl for cl in clauses if cl.get("kind") == "fetch"]
            for cid, clauses in snapshot_coverage.clause_lists(payload).items()}


@pytest.mark.req("REQ-WORTH-0002")
def test_every_fetch_target_in_the_committed_compendium_is_in_the_deadness_scope():
    """The coverage gate widened from the shipped decks to the WHOLE compendium. The deck-scoped gate
    below cannot see a card in no deck of ours — and Issue #301 authored 26 of those at once, so a
    target class typo'd or a class added without a scope entry would sail past it. A clause outside
    the scope is a card that can never be read as dead, however empty the deck is of what it hunts."""
    from common import fetch_closure
    uncovered = sorted({
        (cid, cl.get("target"))
        for cid, clauses in _compendium_fetch_clauses().items() for cl in clauses
        if cl.get("zone") == "deck"
        and cl.get("target") not in fetch_closure.FETCH_DEADNESS_TARGETS})
    assert not uncovered, f"deck-zone fetch targets outside the deadness scope: {uncovered}"


@pytest.mark.req("REQ-WORTH-0002")
def test_the_choice_convention_is_structurally_coherent_in_the_compendium():
    """`choice` (Issue #301) says a clause is ONE ALTERNATIVE of a single choice, so the card's cap
    across its `choice` clauses is the MAX of their amounts and NEVER the sum — Max Rod takes 5 cards
    total, not 5 Pokémon *and* 5 Energy. That is the whole reason the field exists: Dawn's three legs
    genuinely ADD (a Basic AND a Stage 1 AND a Stage 2), so a reader cannot tell the two shapes apart
    from the amounts alone.

    The convention is only readable if a card is consistent about it, which is what this asserts: a
    `choice` clause never sits alone, and a card never mixes `choice` legs with additive ones. A
    card that did would make "is this card's cap a max or a sum?" unanswerable."""
    for cid, clauses in _compendium_fetch_clauses().items():
        marked = [cl for cl in clauses if cl.get("choice")]
        if not marked:
            continue
        assert len(clauses) > 1, f"card {cid}: a lone `choice` clause has nothing to be an alternative to"
        assert len(marked) == len(clauses), (
            f"card {cid}: mixes `choice` legs with additive ones, so its cap is neither a max nor a sum")


@pytest.mark.req("REQ-WORTH-0002")
def test_every_amount_is_a_positive_int_or_the_all_sentinel():
    """`amount` ABSENT means ONE — that is what keeps the three missing-`amount` fixes bug-fixes
    rather than turning an absent field ambiguous — and `"all"` is the ONE sentinel for an unbounded
    *"any number of"* fetch (Precious Trolley, Roto-Stick, Energy Search Pro). Anything else is a
    typo that would read as a silent 0 or a string comparison somewhere downstream."""
    for cid, clauses in _compendium_fetch_clauses().items():
        for cl in clauses:
            if "amount" not in cl:
                continue
            amount = cl["amount"]
            assert amount == "all" or (isinstance(amount, int) and amount > 0), (cid, amount)


@pytest.mark.req("REQ-WORTH-0002")
def test_dig_from_only_qualifies_a_dig_and_only_names_an_end_of_the_deck():
    """`dig_from` (Issue #301, Dusk Ball's BOTTOM 7) qualifies WHICH END a `dig` looks at, so it is
    meaningless without one and its vocabulary is closed at two values. A `dig_from` on a whole-deck
    search, or a third spelling of an end, is a typo that would read as a silent no-op — the
    compendium is authored by hand, so the shape has to be asserted rather than trusted."""
    for cid, clauses in _compendium_fetch_clauses().items():
        for cl in clauses:
            if "dig_from" not in cl:
                continue
            assert cl["dig_from"] in ("top", "bottom"), (cid, cl["dig_from"])
            assert cl.get("dig"), f"card {cid}: `dig_from` without a `dig` qualifies nothing"


@pytest.mark.req("REQ-WORTH-0002")
def test_reaccess_outs_pure_function_matches_the_pilot():
    """`fetch_closure.reaccess_outs(cid, counts, stat_of, clauses_of)` == the Pilot's
    `_card_reaccess_outs(cid, counts)` — the closure pointed backwards, now Pilot-free."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    stat_of, clauses_of = _accessors(ml)
    counts = {678: 1, 1121: 4, 1145: 2, 1152: 4, 6: 10}
    assert (fetch_closure.reaccess_outs(678, counts, stat_of, clauses_of)
            == ml._card_reaccess_outs(678, counts) == 1 + 4 + 2)
    assert (fetch_closure.reaccess_outs(6, {6: 10, 1142: 4}, stat_of, clauses_of)
            == ml._card_reaccess_outs(6, {6: 10, 1142: 4}) == 10 + 4)
    assert fetch_closure.reaccess_outs(999999, counts, stat_of, clauses_of) == 0
    # exhaustive parity over the deck as its own sole copy
    for cid in set(ml.deck):
        c = {cid: 2, 1121: 4, 1145: 2}
        assert (fetch_closure.reaccess_outs(cid, c, stat_of, clauses_of)
                == ml._card_reaccess_outs(cid, c))


@pytest.mark.req("REQ-WORTH-0002")
def test_class_reaccess_outs_counts_each_tutor_once():
    """`class_reaccess_outs` (the slot-RESUPPLY leg): a needs slot is filled by a CLASS of cards, so
    its outs are the own copies of every member class + each deck-search tutor reaching ANY member,
    counted ONCE. Ultra Ball (1121) reaches both Mega Lucario ex (678) and Riolu (677) — summing
    per-class `reaccess_outs` would charge it twice (7 + 7); the set walk prices 10. A singleton set
    IS `reaccess_outs` (the delegation); unknown classes contribute nothing (endorser fail-closed)."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    stat_of, clauses_of = _accessors(ml)
    counts = {678: 1, 677: 3, 1121: 4, 1145: 2}
    assert fetch_closure.reaccess_outs(678, counts, stat_of, clauses_of) == 1 + 4 + 2
    assert fetch_closure.reaccess_outs(677, counts, stat_of, clauses_of) == 3 + 4
    assert (fetch_closure.class_reaccess_outs({678, 677}, counts, stat_of, clauses_of)
            == (1 + 3) + 4 + 2)                                   # own copies + Ultra Ball ONCE + Mega Signal
    assert fetch_closure.class_reaccess_outs({999999}, counts, stat_of, clauses_of) == 0
    assert (fetch_closure.class_reaccess_outs({999999, 678}, counts, stat_of, clauses_of)
            == fetch_closure.class_reaccess_outs({678}, counts, stat_of, clauses_of))
    # singleton parity with `reaccess_outs` over the whole deck (the delegation is load-bearing)
    for cid in set(ml.deck):
        c = {cid: 2, 1121: 4, 1145: 2}
        assert (fetch_closure.class_reaccess_outs({cid}, c, stat_of, clauses_of)
                == fetch_closure.reaccess_outs(cid, c, stat_of, clauses_of))


@pytest.mark.req("REQ-WORTH-0002")
def test_fetch_reaches_pokemon_pure_function_matches_the_pilot():
    """`fetch_closure.fetch_reaches_pokemon(target, cid, counts, ...)` == the Pilot's
    `_fetch_reaches_pokemon` — Poké Pad's `no_rule_box` never reaches the Rule-Box Mega ex."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    stat_of, clauses_of = _accessors(ml)
    counts = {678: 1, 1145: 2, 1152: 4}
    # Mega Signal (1145, mega tutor) reaches 678; Poké Pad (1152, no-Rule-Box) does not
    assert (fetch_closure.fetch_reaches_pokemon(678, 1145, counts, stat_of, clauses_of)
            == ml._fetch_reaches_pokemon(678, 1145, counts))
    assert (fetch_closure.fetch_reaches_pokemon(678, 1152, counts, stat_of, clauses_of)
            == ml._fetch_reaches_pokemon(678, 1152, counts) is False)
    # exhaustive parity: every (tutor, target) pair over the deck
    for tid in set(ml.deck):
        for target in set(ml.deck):
            c = {target: 1}
            assert (fetch_closure.fetch_reaches_pokemon(target, tid, c, stat_of, clauses_of)
                    == ml._fetch_reaches_pokemon(target, tid, c)), (tid, target)


# ── Fetch DEADNESS: the opposite reading of the same clause (ADR-0073, issue #164) ────────────────
@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_accepts_the_dig_and_trigger_clauses_reach_rejects():
    """The ADR-0073 asymmetry, stated directly. REACH asks "can this card get me X back?" — a
    ``dig``-7 may MISS a card still in the deck, so it is never a closure edge. DEADNESS asks "is
    anything left for this card to find?" — zero targets in deck means the dig PROVABLY whiffs, so
    the same clause is admissible. The flag is the only difference; the default is the safe reading.
    """
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    ml_ex = ml.stats.get(678)
    energy = ml.stats.get(6)
    for clause, stat in (({"target": "mega", "dig": 7}, ml_ex),
                         ({"target": "mega", "trigger": "on_bench_play"}, ml_ex),
                         ({"target": "basic_energy", "dig": 7}, energy)):
        assert fetch_closure.fetch_target_matches(clause, stat) is False           # reach (default)
        assert fetch_closure.fetch_target_matches(clause, stat, deadness=True) is True
    # the flag changes ONLY the trigger/dig gate — a non-matching target stays non-matching
    assert fetch_closure.fetch_target_matches({"target": "basic_pokemon", "dig": 7}, ml_ex,
                                              deadness=True) is False
    assert fetch_closure.fetch_target_matches({"target": "mega", "dig": 7}, None,
                                              deadness=True) is False


@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_flag_is_a_no_op_on_a_plain_clause():
    """Off a ``trigger``/``dig`` carrier the two readings are the SAME predicate — exhaustively, over
    every card of a shipped deck and every target class. The asymmetry is confined to two places: the
    trigger/dig gate, and the deadness-only ``supporter`` branch below."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    for cid in set(ml.deck):
        st = ml.stats.get(cid)
        for target in sorted(fetch_closure.FETCH_DEADNESS_TARGETS
                             - fetch_closure.FETCH_DEADNESS_ONLY_TARGETS):
            clause = {"target": target}
            assert (fetch_closure.fetch_target_matches(clause, st)
                    == fetch_closure.fetch_target_matches(clause, st, deadness=True)), (cid, target)


@pytest.mark.req("REQ-WORTH-0002")
def test_the_supporter_branch_is_deadness_only_so_reach_is_provably_unchanged():
    """ADR-0073 promises REACH is unchanged. The ``supporter`` class had no branch at all before, so
    deadness needed one — but reading it for REACH too would make a PLAIN Supporter search a closure
    edge and move the out-count.

    That used to be inert (both carriers were `dig`/`trigger` clauses) and this test existed so the
    guarantee would not rest on which cards happen to exist. **Issue #301 made it load-bearing**:
    Secret Box, Larry's Skill and Team Rocket's Transceiver all carry plain ``target: supporter``
    deck searches now, and Secret Box is 2 copies across our decks. The gate stays — un-gating it is
    the deliberate, measured change ADR-0073 names, and the omission under-counts outs, which is the
    safe direction."""
    from common import fetch_closure
    supporter = _shipped_pilot("mega_starmie").stats.get(1225)      # Hilda, a Supporter
    assert getattr(supporter, "is_supporter", False) is True
    assert fetch_closure.fetch_target_matches({"target": "supporter"}, supporter) is False
    assert fetch_closure.fetch_target_matches({"target": "supporter"}, supporter,
                                              deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_target_classes_cover_every_deck_zone_fetch_in_every_shipped_deck():
    """COVERAGE GATE. Every ``zone: deck`` FETCH clause in every shipped agent deck must fall inside
    the deadness scope — otherwise that card can never be read as dead, however empty the deck is of
    what it searches for. This is the gate that would have caught issue #164's real hole: Pokégear
    3.0 (`supporter` + `dig: 7`), Energy Search / Energy Search Pro / Fighting Gong (`basic_energy`),
    Hilda (`energy`) and Team Rocket's Petrel (`trainer`) all sat outside the Pokémon-only scope.

    A Pokémon-carried clause (Meowth ex's ``trigger``) is exempt: the deadline gate is Trainer-only,
    so a playable body is never priced as a dead fetcher."""
    from common import fetch_closure
    uncovered = []
    for agent in ("mega_starmie", "mega_lucario", "dragapult_ex"):
        pilot = _shipped_pilot(agent)
        for cid in set(pilot.deck):
            stat = pilot.stats.get(cid)
            if stat is None or stat.is_pokemon:            # Trainer-only gate (see docstring)
                continue
            for cl in (pilot.effects.clauses(cid) if pilot.effects else ()):
                if cl.get("kind") == "fetch" and cl.get("zone") == "deck":
                    if cl.get("target") not in fetch_closure.FETCH_DEADNESS_TARGETS:
                        uncovered.append((agent, cid, getattr(stat, "name", None), cl.get("target")))
    assert not uncovered, f"deck-zone fetch clauses outside the deadness scope: {uncovered}"


#: The #164 family — every Trainer carrying a ``zone: deck`` fetch clause whose target class sat
#: OUTSIDE the old Pokémon-only whiff scope. Card id -> (name, its full deck-zone target list).
#: Energy Search / Energy Search Pro are in the card set but in no shipped deck today; they are
#: asserted at the CLAUSE level, which is where their coverage actually lives.
#:
#: Note the two MULTI-clause members. Fighting Gong and Hilda each carry one target class that was
#: already in scope and one that was not — so their whiff question was not merely blind, it was
#: UNSOUND (see the false-whiff test below).
UNCOVERED_BEFORE_ADR_0073 = {
    1122: ("Pokégear 3.0", ["supporter"]),
    1119: ("Energy Search", ["basic_energy"]),
    1100: ("Energy Search Pro", ["basic_energy"]),
    1142: ("Fighting Gong", ["basic_energy", "basic_pokemon"]),
    1225: ("Hilda", ["energy", "evolution"]),
    1219: ("Team Rocket's Petrel", ["trainer"]),
}


@pytest.mark.req("REQ-WORTH-0002")
def test_the_uncovered_family_target_classes_are_all_in_the_deadness_scope():
    """The #164 family at the CLAUSE level: EVERY ``zone: deck`` fetch clause each of them carries is
    now inside the deadness scope. Read from `card_effects.json` itself, so a card belonging to no
    shipped deck is still covered — and the exact target list is asserted, so a clause silently
    re-typed or a second clause appearing is a failure rather than a pass by absence.

    "Every clause" is the load-bearing word: a fetcher is dead only when ALL its classes are
    exhausted, so a class left outside the scope does not just hide deadness, it FABRICATES it."""
    from common import fetch_closure
    effects = _shipped_pilot("mega_starmie").effects
    for cid, (name, want_targets) in UNCOVERED_BEFORE_ADR_0073.items():
        deck_clauses = [cl for cl in effects.clauses(cid)
                        if cl.get("kind") == "fetch" and cl.get("zone") == "deck"]
        assert deck_clauses, f"{name} ({cid}) has no deck-zone fetch clause — fixture drifted"
        assert sorted(cl.get("target") for cl in deck_clauses) == sorted(want_targets), name
        assert set(want_targets) <= fetch_closure.FETCH_DEADNESS_TARGETS, name


@pytest.mark.req("REQ-WORTH-0002")
def test_a_multi_clause_fetcher_is_dead_only_when_every_class_is_exhausted():
    """The FALSE-WHIFF fix, and the sharpest reason the widening is a soundness change rather than a
    coverage one. Fighting Gong fetches a Basic {F} Energy OR a Basic {F} Pokémon; before ADR-0073 the
    whiff question saw only the Pokémon clause, so once the Basic Pokémon were gone it would have
    called the Gong dead while it could still find Energy — a fabricated deadness claim, the fail
    direction `fetch_closure` forbids. The deadness set must span BOTH classes."""
    ml = _shipped_pilot("mega_lucario")
    deadness = ml._fetch_deadness_set(1142)
    reach = ml._search_deck_set(1142)
    assert reach < deadness, "the energy half of Fighting Gong's fetch is missing from deadness"
    energy_half = {cid for cid in deadness
                   if (st := ml.stats.get(cid)) is not None and st.is_basic_energy}
    assert energy_half, "no Basic Energy in the deadness set — the second clause is not being read"


@pytest.mark.req("REQ-WORTH-0002")
def test_every_shipped_copy_of_the_family_resolves_a_deadness_set():
    """The same family end to end through the doctrine's set-builder: wherever one of them is
    ACTUALLY in a deck, it resolves a NON-EMPTY set of deck ids it could find, so
    `dont-search-an-empty-deck` and the fetcher deadline gate can both ask whether that set is
    exhausted. Before ADR-0073 every one was the empty set — which reads as "not a search at all"
    and can never be dead.

    The coverage set is asserted, not just iterated: a card dropping out of every deck fails here
    rather than quietly reducing the test to nothing (which is exactly how the #164 hole survived).

    `grimmsnarl_ex` dropped off this walk when PR #436 deleted the deck (2026-08-06). The asserted
    coverage set is UNCHANGED by that: it ran 1122 Pokégear and 1219 Petrel, and both are still
    reached — Pokégear through `mega_starmie`, Petrel through `mega_lucario` — so the four-card
    expectation below still measures four decks' worth of the family, from three decks."""
    covered = set()
    for agent in ("mega_starmie", "mega_lucario", "dragapult_ex"):
        pilot = _shipped_pilot(agent)
        for cid, (name, _target) in UNCOVERED_BEFORE_ADR_0073.items():
            if cid not in set(pilot.deck):
                continue
            assert pilot._fetch_deadness_set(cid), f"{name} ({cid}) in {agent}: no deadness set"
            covered.add(cid)
    assert covered == {1122, 1142, 1225, 1219}, (
        "shipped-deck coverage of the #164 family changed; update the expectation deliberately "
        f"(got {sorted(covered)})")


@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_widening_never_leaks_into_the_endorser_set():
    """ADR-0073's soundness argument holds ONLY in the deadness direction: widening the target set
    makes ``all(target exhausted)`` harder, so it can only SUPPRESS a claim. The reach-scoped
    `_search_deck_set` feeds ENDORSERS (`fetch-when-it-fills-a-need`, the deferral read) where a
    wider set would FABRICATE endorsement — a dig-7 Pokégear would claim it fills a need it can only
    probably reach. So the two sets are distinct, and the reach set stays a SUBSET of the deadness
    set for every card of every shipped deck."""
    for agent in ("mega_starmie", "mega_lucario", "dragapult_ex"):
        pilot = _shipped_pilot(agent)
        for cid in set(pilot.deck):
            assert pilot._search_deck_set(cid) <= pilot._fetch_deadness_set(cid), (agent, cid)
    ms = _shipped_pilot("mega_starmie")
    assert ms._search_deck_set(1122) == set()           # Pokégear: no endorsement claim, as before
    assert ms._fetch_deadness_set(1122)                 # ...but it CAN now be read as dead
