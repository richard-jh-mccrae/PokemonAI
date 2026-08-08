"""`common.fetch_closure` (ADR-0065): the tutor/recycle/search graph, Pilot-independent.

Behaviour preservation is asserted as PARITY against the Pilot delegators on the real shipped decks.
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
    """The same predicate the Pilot exposes as `_fetch_target_matches`."""
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
    """A ``trigger``-gated fetch or a ``dig`` is not the unconditional whole-deck search the closure
    model assumes, so the predicate rejects it even when the target class matches."""
    from common import fetch_closure
    ml = _shipped_pilot("mega_lucario")
    ml_ex = ml.stats.get(678)
    energy = ml.stats.get(6)
    assert fetch_closure.fetch_target_matches({"target": "mega"}, ml_ex) is True
    assert fetch_closure.fetch_target_matches({"target": "mega", "dig": 7}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "mega", "trigger": "on_bench_play"}, ml_ex) is False
    assert fetch_closure.fetch_target_matches({"target": "basic_energy", "dig": 7}, energy) is False
    # the real carriers: Meowth ex 1071 (trigger) and Pokégear 1122 (dig)
    stat_of, clauses_of = _accessors(ml)
    for cid in (1071, 1122):
        for cl in clauses_of(cid):
            if cl.get("kind") == "fetch":
                assert fetch_closure.fetch_target_matches(cl, ml.stats.get(1182)) is False


# The widened target vocabulary (Issue #301), asserted on hand-built rows: these are claims about the
# PREDICATE, and the real-deck parity walks above already pin that it and the Pilot agree.

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
    """A target that over-matches fabricates a closure out, the one direction this module forbids.
    (`any`, the eighth class, is deadness-only and has its own test below.)"""
    from common import fetch_closure
    got = {name for name, stat in _ROWS.items()
           if fetch_closure.fetch_target_matches({"target": target}, stat)}
    assert got == hits


# The same two classes against PRODUCTION rows (Issue #408): a hand-built `CardStat` can supply a
# value the provider never emits, and then the fixture is grading itself.

#: Dawn (1231) fetches all three rungs of this line. Applin is the POSITIVE CONTROL: a Basic of the
#: SAME line must match neither class, so a predicate degenerated to "any Pokémon" fails here.
APPLIN, DIPPLIN, HYDRAPPLE_EX = 149, 93, 150


@pytest.fixture(scope="module")
def real_stats():
    from common.scouting.provider import EngineCardStatProvider
    stats = EngineCardStatProvider()
    stats.warm()
    return stats


@pytest.mark.req("REQ-WORTH-0002")
def test_the_stage_classes_match_real_provider_rows(real_stats):
    """Read off the production provider; the Basic leg keeps it honest in the other direction."""
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
    """Both the clause rows and the stat rows come from shipped artefacts, so neither side of the
    match is authored by this test."""
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
    """The two classes that answer *"is anything left to find?"* and never *"can this get me X?"*.
    Gated in the PREDICATE, so the guarantee does not rest on a caller remembering to apply it."""
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
    """A board GATE makes the search conditional, exactly as `dig` and `trigger` do. Deadness admits
    it: a gate cannot put cards back in the deck."""
    from common import fetch_closure
    clause = {"target": "pokemon", "condition": "going_second_first_turn"}
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"]) is False
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"], deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_a_name_family_fetch_reaches_nothing_until_a_family_oracle_exists():
    """No build-time family index exists, so reach REFUSES the clause rather than reading it as *any*
    Basic. Deadness ignores the restriction, which can only suppress a claim, never invent one."""
    from common import fetch_closure
    clause = {"target": "basic_pokemon", "name_family": "Hop's"}
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"]) is False
    assert fetch_closure.fetch_target_matches(clause, _ROWS["basic"], deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_the_pokemon_side_predicates_apply_to_every_pokemon_class():
    """`no_rule_box`, `hp_max` and `no_ability` are properties of the TARGET BODY, not of the class
    that names it, so one predicate applies them to every Pokémon class."""
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
    """``{card id: [its fetch clauses]}`` off the COMMITTED compendium."""
    import json
    from common import snapshot_coverage
    payload = json.loads((REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    return {cid: [cl for cl in clauses if cl.get("kind") == "fetch"]
            for cid, clauses in snapshot_coverage.clause_lists(payload).items()}


@pytest.mark.req("REQ-WORTH-0002")
def test_every_fetch_target_in_the_committed_compendium_is_in_the_deadness_scope():
    """Compendium-wide, because the deck-scoped gate below cannot see a card in no deck of ours. A
    clause outside the scope is a card that can never be read as dead."""
    from common import fetch_closure
    uncovered = sorted({
        (cid, cl.get("target"))
        for cid, clauses in _compendium_fetch_clauses().items() for cl in clauses
        if cl.get("zone") == "deck"
        and cl.get("target") not in fetch_closure.FETCH_DEADNESS_TARGETS})
    assert not uncovered, f"deck-zone fetch targets outside the deadness scope: {uncovered}"


@pytest.mark.req("REQ-WORTH-0002")
def test_the_choice_convention_is_structurally_coherent_in_the_compendium():
    """`choice` marks a clause as ONE ALTERNATIVE, so the card's cap is the MAX of the amounts and
    never the sum. A card mixing `choice` legs with additive ones makes that unanswerable."""
    for cid, clauses in _compendium_fetch_clauses().items():
        marked = [cl for cl in clauses if cl.get("choice")]
        if not marked:
            continue
        assert len(clauses) > 1, f"card {cid}: a lone `choice` clause has nothing to be an alternative to"
        assert len(marked) == len(clauses), (
            f"card {cid}: mixes `choice` legs with additive ones, so its cap is neither a max nor a sum")


@pytest.mark.req("REQ-WORTH-0002")
def test_every_amount_is_a_positive_int_or_the_all_sentinel():
    """`amount` ABSENT means ONE and `"all"` is the ONE sentinel for an unbounded fetch; anything
    else reads as a silent 0 or a string comparison downstream."""
    for cid, clauses in _compendium_fetch_clauses().items():
        for cl in clauses:
            if "amount" not in cl:
                continue
            amount = cl["amount"]
            assert amount == "all" or (isinstance(amount, int) and amount > 0), (cid, amount)


@pytest.mark.req("REQ-WORTH-0002")
def test_dig_from_only_qualifies_a_dig_and_only_names_an_end_of_the_deck():
    """`dig_from` qualifies WHICH END a `dig` looks at, so it is meaningless without one and its
    vocabulary is closed at two values. The compendium is hand-authored; a typo is a silent no-op."""
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
    """A needs slot is filled by a CLASS, so its outs are the own copies plus each tutor reaching ANY
    member counted ONCE — summing per-class `reaccess_outs` double-charges a tutor spanning two."""
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
    """REACH: a ``dig``-7 may MISS a card still in the deck. DEADNESS: zero targets in deck means it
    PROVABLY whiffs. The flag is the only difference, and the default is the safe reading."""
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
    """The asymmetry is confined to two places: the trigger/dig gate and the deadness-only
    ``supporter`` branch below."""
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
    """ADR-0073 promises REACH is unchanged: reading the ``supporter`` branch for reach too would
    make a plain Supporter search a closure edge and move the out-count."""
    from common import fetch_closure
    supporter = _shipped_pilot("mega_starmie").stats.get(1225)      # Hilda, a Supporter
    assert getattr(supporter, "is_supporter", False) is True
    assert fetch_closure.fetch_target_matches({"target": "supporter"}, supporter) is False
    assert fetch_closure.fetch_target_matches({"target": "supporter"}, supporter,
                                              deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_target_classes_cover_every_deck_zone_fetch_in_every_shipped_deck():
    """A Pokémon-carried clause is exempt: the deadline gate is Trainer-only, so a playable body is
    never priced as a dead fetcher."""
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


#: Card id -> (name, its full deck-zone target list), for every Trainer whose target class sat
#: OUTSIDE the old Pokémon-only whiff scope (Issue #164).
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
    """EVERY clause is load-bearing: a fetcher is dead only when ALL its classes are exhausted, so a
    class left outside the scope does not hide deadness, it FABRICATES it."""
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
    """Fighting Gong fetches a Basic {F} Energy OR a Basic {F} Pokémon; reading one clause only would
    call it dead while it can still find the other — a fabricated deadness claim."""
    ml = _shipped_pilot("mega_lucario")
    deadness = ml._fetch_deadness_set(1142)
    reach = ml._search_deck_set(1142)
    assert reach < deadness, "the energy half of Fighting Gong's fetch is missing from deadness"
    energy_half = {cid for cid in deadness
                   if (st := ml.stats.get(cid)) is not None and st.is_basic_energy}
    assert energy_half, "no Basic Energy in the deadness set — the second clause is not being read"


@pytest.mark.req("REQ-WORTH-0002")
def test_every_shipped_copy_of_the_family_resolves_a_deadness_set():
    """An empty deadness set reads as "not a search at all" and can never be dead. The coverage set
    is asserted, not just iterated, so a card dropping out of every deck fails rather than passes."""
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
    """Widening only ever SUPPRESSES a deadness claim, but the reach-scoped `_search_deck_set` feeds
    ENDORSERS, where a wider set would FABRICATE one. So reach stays a SUBSET of deadness."""
    for agent in ("mega_starmie", "mega_lucario", "dragapult_ex"):
        pilot = _shipped_pilot(agent)
        for cid in set(pilot.deck):
            assert pilot._search_deck_set(cid) <= pilot._fetch_deadness_set(cid), (agent, cid)
    ms = _shipped_pilot("mega_starmie")
    assert ms._search_deck_set(1122) == set()           # Pokégear: no endorsement claim, as before
    assert ms._fetch_deadness_set(1122)                 # ...but it CAN now be read as dead


# ── Body COLOUR on a Pokémon target: a REACH narrowing only (ADR-0073, Issue #440's reach half) ───

#: Fighting Gong (mega_lucario) fetches a Basic **{F}** Pokémon. Meowth ex is the control: a Basic in
#: the same deck whose colour is {C} (`energyType` 0), so a colour-blind predicate keeps reaching it.
FIGHTING_GONG, MEOWTH_EX, GONG_FIGHTING_BASICS = 1142, 1071, {673, 675, 676, 677}


def _gong_pokemon_clause():
    from common.effects import CardEffects
    return next(cl for cl in CardEffects.load().clauses(FIGHTING_GONG)
                if cl.get("kind") == "fetch" and cl.get("target") == "basic_pokemon")


@pytest.mark.req("REQ-WORTH-0002")
def test_energy_type_narrows_reach_on_a_pokemon_target(real_stats):
    """Colour-blind, Gong claimed it could tutor a {C} Basic — a FABRICATED endorsement, since every
    reach consumer asks `any(reachable)`. Both sides come off shipped artefacts, not a fixture."""
    from common import fetch_closure
    clause = _gong_pokemon_clause()
    assert clause["energy_type"] == 6 and fetch_closure.fetch_is_unconditional(clause)
    meowth = real_stats.get(MEOWTH_EX)
    assert (meowth.energyType, meowth.is_pokemon, meowth.evolvesFrom) == (0, True, None)
    assert fetch_closure.fetch_target_matches(clause, meowth) is False
    for cid in sorted(GONG_FIGHTING_BASICS):
        assert fetch_closure.fetch_target_matches(clause, real_stats.get(cid)) is True, cid


@pytest.mark.req("REQ-WORTH-0002")
def test_deadness_refuses_the_colour_narrowing_so_no_whiff_is_fabricated(real_stats):
    """Deadness is `all(gone)`: dropping Meowth ex would let the whiff veto fire while Gong can still
    find it. Suppressing a claim is this module's safe direction; inventing one never is."""
    from common import fetch_closure
    assert fetch_closure.fetch_target_matches(_gong_pokemon_clause(), real_stats.get(MEOWTH_EX),
                                              deadness=True) is True
    ml = _shipped_pilot("mega_lucario")
    reach, dead = ml._search_deck_set(FIGHTING_GONG), ml._fetch_deadness_set(FIGHTING_GONG)
    assert MEOWTH_EX not in reach and MEOWTH_EX in dead
    assert GONG_FIGHTING_BASICS <= reach < dead


@pytest.mark.req("REQ-WORTH-0002")
def test_the_colour_narrowing_binds_every_pokemon_class_and_reads_a_populated_field():
    """It sits with the shared per-BODY predicates, so a future clause pairing `energy_type` with
    `stage2` narrows rather than failing OPEN. The `is not None` leg retires ADR-0073's caveat."""
    from common import fetch_closure as fc
    ml = _shipped_pilot("mega_lucario")
    for target in sorted(fc.FETCH_POKEMON_TARGETS):
        for cid in sorted(set(ml.deck)):
            st = ml.stats.get(cid)
            if st is None or not fc.fetch_target_matches({"target": target}, st):
                continue
            assert st.energyType is not None, (target, cid)
            wrong = (st.energyType + 1) % 10
            assert fc.fetch_target_matches({"target": target, "energy_type": st.energyType}, st)
            assert fc.fetch_target_matches({"target": target, "energy_type": wrong}, st) is False
            assert fc.fetch_target_matches({"target": target, "energy_type": wrong}, st,
                                           deadness=True) is True


@pytest.mark.req("REQ-WORTH-0002")
def test_a_trainer_never_reaches_the_colour_predicate(real_stats):
    """Trainers report `energyType` 0 as well, so {C} and "not a Pokémon" are indistinguishable in the
    field. The narrowing is confined to the Pokémon branch structurally, not by a repeated guard."""
    from common import fetch_closure
    gear = real_stats.get(1122)
    assert (gear.energyType, gear.is_pokemon) == (0, False)
    assert fetch_closure.fetch_target_matches({"target": "pokemon", "energy_type": 0}, gear) is False
    assert fetch_closure.fetch_target_matches({"target": "supporter", "energy_type": 0},
                                              real_stats.get(1225), deadness=True) is True


# `reveal_legs` is the ONE reader of the multi-leg reveal RELATION, for both `board_expectation` and
# `board_choice`, so it cannot be spelled twice and drift.

def _effects():
    from common.effects import CardEffects
    return CardEffects.load(REPO / "src" / "common" / "card_effects.json")


@pytest.mark.req("REQ-WORTH-0002")
def test_reveal_legs_reads_the_relation_off_the_SHIPPED_compendium():
    """Every multi-leg reveal card in the store, classified. Read off real data rather than a
    fixture, because the relation is a property of the compendium and a fixture cannot check it."""
    from common.fetch_closure import reveal_legs
    eff = _effects()

    def relation(cid):
        try:
            return reveal_legs(eff.clauses(cid)).relation
        except ValueError as gap:
            return f"refused: {gap}"

    # UNIONS — "or", one shared cap. 1097/1142 are the two the compendium had backwards.
    for cid in (1097, 1142, 1094, 1110, 1184, 1215, 1238):
        assert relation(cid) == "union", (cid, relation(cid))
    # CONJUNCTIONS — "and", one card per leg.
    for cid in (1225, 1231, 1194):
        assert relation(cid) == "conjunction", (cid, relation(cid))
    # SINGLE-leg cards keep their own relation rather than being special-cased by the caller.
    for cid in (1121, 1205, 1086, 1145):
        assert relation(cid) == "single", (cid, relation(cid))


@pytest.mark.req("REQ-WORTH-0002")
def test_reveal_legs_refuses_an_exclusive_either_or_rather_than_guessing_a_cap():
    """`choice` on both legs but DIFFERENT amounts, so there is no single shared cap to enumerate
    over. The engine spells it with its own op (`xDeckToHandEitherOr`): a real third shape."""
    from common.fetch_closure import reveal_legs
    with pytest.raises(ValueError, match="either-or"):
        reveal_legs(_effects().clauses(1210))


@pytest.mark.req("REQ-WORTH-0002")
def test_reveal_legs_refuses_a_reach_gated_leg_rather_than_skipping_it():
    """A `FETCH_DEADNESS_ONLY_TARGETS` leg matches nothing at the REACH reading every pool walk uses,
    so skipping it would enumerate three of Secret Box's four legs and report completeness."""
    from common.fetch_closure import reveal_legs
    for cid in (1092, 1206):
        with pytest.raises(ValueError, match="reach-gated|matches nothing"):
            reveal_legs(_effects().clauses(cid))
    # …and those two are the ONLY carriers, so the rule is scoped rather than a blanket.
    eff, gated = _effects(), []
    for cid in (1094, 1097, 1110, 1142, 1184, 1194, 1215, 1225, 1231, 1238):
        reveal_legs(eff.clauses(cid))          # every other multi-leg card still resolves
        gated.append(cid)
    assert len(gated) == 10


@pytest.mark.req("REQ-WORTH-0002")
def test_a_SINGLE_reach_gated_leg_is_not_refused_here():
    """With one leg there is no OTHER leg to enumerate, so no partial answer can be manufactured and
    the hazard the multi-leg refusal exists for cannot arise."""
    from common.fetch_closure import reveal_legs
    eff = _effects()
    for cid in (1122, 1071, 1077, 1109, 1101, 1134):   # single-leg `supporter` targets
        assert reveal_legs(eff.clauses(cid)).relation == "single", cid
    for cid in (1185, 1193):                           # single-leg `any` targets
        assert reveal_legs(eff.clauses(cid)).relation == "single", cid


@pytest.mark.req("REQ-WORTH-0002")
def test_reveal_legs_refuses_a_half_declared_relation():
    """`choice` on some legs and not others: neither reading is available. No carrier in the shipped
    store, so a synthetic is the only way to reach it."""
    from common.fetch_closure import reveal_legs
    half = [{"kind": "fetch", "target": "pokemon", "zone": "deck", "choice": True},
            {"kind": "fetch", "target": "energy", "zone": "deck"}]
    with pytest.raises(ValueError, match="half-declared"):
        reveal_legs(half)


@pytest.mark.req("REQ-WORTH-0002")
def test_reveal_legs_carries_the_shared_cap_and_ignores_non_revealing_companions():
    """A union's cap is the shared `amount` (absent ⇒ 1); a conjunction's is 1 per leg by
    construction. The cap is what the enumerator ranges over, so it comes back with the legs."""
    from common.fetch_closure import reveal_legs
    eff = _effects()
    assert reveal_legs(eff.clauses(1097)).cap == 1        # "a Pokemon or a Basic Energy card"
    assert reveal_legs(eff.clauses(1142)).cap == 1        # "a Basic {F} Energy or a Basic {F} Pokemon"
    assert reveal_legs(eff.clauses(1184)).cap == 3        # Lana's Aid, "up to 3 in any combination"
    assert reveal_legs(eff.clauses(1110)).cap == 5        # Max Rod, "up to 5 in any combination"
    assert reveal_legs(eff.clauses(1205)).cap == 3        # Cyrano, "up to 3 Pokemon ex"
    assert len(reveal_legs(eff.clauses(1231)).legs) == 3  # Dawn: Basic + Stage 1 + Stage 2
    assert reveal_legs(eff.clauses(1231)).cap == 1        # one card per leg
    with pytest.raises(ValueError, match="no `draw`/`fetch`"):
        reveal_legs([{"kind": "heal", "amount": 30}])
