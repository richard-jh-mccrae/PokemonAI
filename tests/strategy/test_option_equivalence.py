"""The **Option Equivalence Class** oracle (ADR-0091 decision 1, Issue #247).

Every case here is built from plain dicts — no engine, no Pilot, no corpus — because the oracle is
pure and its whole job is to be provable without any of them. The corpus-level assertions (the two
frames that move) live in `tests/train/test_gates.py`, beside the predicate they change.
"""
import pytest

from common.option_equivalence import (AREA_ACTIVE, AREA_BENCH, AREA_DECK, AREA_DISCARD, AREA_HAND,
                                       AREA_LOOKING, option_equivalence, option_fingerprint)

OPT_CARD, OPT_ATTACH = 3, 8


def _body(cid=1030, *, hp=70, serial=1, tools=(), energies=(), pre=()):
    return {"appearThisTurn": False, "energies": list(energies), "energyCards": [],
            "hp": hp, "id": cid, "maxHp": 70, "playerIndex": 0,
            "preEvolution": list(pre), "serial": serial, "tools": list(tools)}


def _frame(*, bench=(), active=(), hand=(), discard=(), looking=None, seat=0):
    me = {"active": list(active), "bench": list(bench), "hand": list(hand),
          "discard": list(discard)}
    players = [me, {"active": [], "bench": [], "hand": [], "discard": []}]
    if seat == 1:
        players.reverse()
    return {"current": {"players": players, "yourIndex": seat, "looking": looking}}


def _select(frame, options):
    return {**frame, "select": {"context": 0, "option": list(options)}}


def _pick(frame, options):
    return option_equivalence(options, frame)


# ── the class the issue is about ─────────────────────────────────────────────────────────────────

def test_two_identical_bench_bodies_are_ONE_decision():
    """`81905522|0|decision|75`'s shape, reduced: two Riolu a board cannot tell apart."""
    frame = _frame(bench=[_body(serial=1), _body(serial=2)])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {0: frozenset({0, 1}), 1: frozenset({0, 1})}


def test_serial_is_the_ONLY_field_ignored():
    """Two bodies identical but for the engine's instance number ARE one decision — and that is the
    only difference that may be ignored. Every other assertion in this file is the negative half."""
    a, b = _body(serial=11), _body(serial=97)
    assert option_fingerprint({"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
                              _frame(bench=[a, b])) == \
           option_fingerprint({"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD},
                              _frame(bench=[a, b]))


# ── the negatives: anything game-visible splits the class ────────────────────────────────────────

@pytest.mark.parametrize("other, why", [
    (_body(hp=40, serial=2), "damaged"),
    (_body(serial=2, tools=[{"id": 500, "serial": 9}]), "carries a Tool"),
    (_body(serial=2, energies=[3]), "has Energy attached"),
    (_body(cid=1031, serial=2), "a different card"),
    (_body(serial=2, pre=[{"id": 1029, "serial": 8}]), "evolved from something"),
])
def test_a_game_visible_difference_splits_the_class(other, why):
    frame = _frame(bench=[_body(serial=1), other])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}, f"a body that is {why} is NOT the same decision"


def test_appear_this_turn_splits_the_class():
    """Summoning sickness is game-visible state, not bookkeeping."""
    fresh = _body(serial=2)
    fresh["appearThisTurn"] = True
    frame = _frame(bench=[_body(serial=1), fresh])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


def test_a_different_option_TYPE_splits_the_class():
    """Same body, two different things to do to it."""
    frame = _frame(bench=[_body(serial=1), _body(serial=2)])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": 9}]
    assert _pick(frame, opts) == {}


def test_the_two_seats_are_never_one_decision():
    """Identical bodies on OPPOSITE sides of the board are opposite decisions."""
    mine, theirs = _body(serial=1), _body(serial=2)
    frame = {"current": {"yourIndex": 0, "looking": None,
                         "players": [{"active": [], "bench": [mine], "hand": [], "discard": []},
                                     {"active": [], "bench": [theirs], "hand": [], "discard": []}]}}
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 0, "playerIndex": 1, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


# ── the rejected body-only design's six false equivalences ───────────────────────────────────────

def test_two_attaches_of_DIFFERENT_hand_cards_to_one_body_are_NOT_one_decision():
    """An ATTACH names TWO cards: `area`/`index` is the Energy in hand, `inPlayArea`/`inPlayIndex`
    the recipient body (ADR-0091 decision 1)."""
    frame = _frame(bench=[_body(serial=1)],
                   hand=[{"id": 3, "playerIndex": 0, "serial": 40},      # Water
                         {"id": 6, "playerIndex": 0, "serial": 41}])     # a DIFFERENT type
    opts = [{"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH},
            {"area": AREA_HAND, "index": 1, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH}]
    assert _pick(frame, opts) == {}


def test_the_SAME_hand_card_to_two_identical_bodies_IS_one_decision():
    frame = _frame(bench=[_body(serial=1), _body(serial=2)],
                   hand=[{"id": 5, "playerIndex": 0, "serial": 40}])
    opts = [{"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH},
            {"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 1,
             "playerIndex": 0, "type": OPT_ATTACH}]
    assert _pick(frame, opts) == {0: frozenset({0, 1}), 1: frozenset({0, 1})}


def test_two_identical_hand_cards_to_one_body_ARE_one_decision():
    frame = _frame(bench=[_body(serial=1)],
                   hand=[{"id": 5, "playerIndex": 0, "serial": 40},
                         {"id": 5, "playerIndex": 0, "serial": 41}])
    opts = [{"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH},
            {"area": AREA_HAND, "index": 1, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH}]
    assert _pick(frame, opts) == {0: frozenset({0, 1}), 1: frozenset({0, 1})}


# ── blind implies conservative, structurally ─────────────────────────────────────────────────────

def test_a_face_down_DECK_option_joins_no_class():
    """The snapshot exposes the deck only as a COUNT: unresolvable means unfingerprintable means no
    class, so the oracle is conservative where it is blind by construction, not by an exclusion list."""
    frame = _frame()
    opts = [{"area": AREA_DECK, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_DECK, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


def test_an_out_of_range_index_yields_no_class_rather_than_an_error():
    frame = _frame(bench=[_body(serial=1)])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 7, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


def test_an_option_naming_no_zone_at_all_joins_no_class():
    """END, YES/NO and friends carry no zone reference. Two of them are not one decision — they are
    not a *targeting* decision at all."""
    assert _pick(_frame(), [{"type": 14}, {"type": 14}]) == {}


def test_a_partially_unresolvable_option_is_dropped_WHOLE():
    """An ATTACH whose recipient resolves but whose hand index does not must not fall back to a
    body-only fingerprint — that is precisely the rejected design."""
    frame = _frame(bench=[_body(serial=1), _body(serial=2)], hand=[])
    opts = [{"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 0,
             "playerIndex": 0, "type": OPT_ATTACH},
            {"area": AREA_HAND, "index": 0, "inPlayArea": AREA_BENCH, "inPlayIndex": 1,
             "playerIndex": 0, "type": OPT_ATTACH}]
    assert _pick(frame, opts) == {}


# ── the zones the snapshot DOES reveal ───────────────────────────────────────────────────────────

def test_identical_revealed_LOOKING_cards_are_one_decision():
    """A search reveal lists real cards, so two identical ones are interchangeable."""
    frame = _frame(looking=[{"id": 5, "playerIndex": 0, "serial": 7},
                            {"id": 5, "playerIndex": 0, "serial": 9}])
    opts = [{"area": AREA_LOOKING, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_LOOKING, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {0: frozenset({0, 1}), 1: frozenset({0, 1})}


def test_differing_LOOKING_cards_are_not():
    frame = _frame(looking=[{"id": 5, "playerIndex": 0, "serial": 7},
                            {"id": 1080, "playerIndex": 0, "serial": 9}])
    opts = [{"area": AREA_LOOKING, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_LOOKING, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


def test_identical_DISCARD_cards_are_one_decision():
    frame = _frame(discard=[{"id": 5, "playerIndex": 0, "serial": 7},
                            {"id": 5, "playerIndex": 0, "serial": 9}])
    opts = [{"area": AREA_DISCARD, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_DISCARD, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {0: frozenset({0, 1}), 1: frozenset({0, 1})}


def test_the_ACTIVE_area_resolves():
    frame = _frame(active=[_body(serial=1)], bench=[_body(serial=2)])
    opts = [{"area": AREA_ACTIVE, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}, "the same card ACTIVE vs BENCHED is not the same decision"


# ── class shape ──────────────────────────────────────────────────────────────────────────────────

def test_a_three_member_class_names_all_three():
    """`81903490|0|decision|49`'s shape — three identical Riolu, the frame carrying the worst
    measured leaf asymmetry (1167.0 / 95.4 / 95.4)."""
    frame = _frame(bench=[_body(serial=1), _body(serial=2), _body(serial=3)])
    opts = [{"area": AREA_BENCH, "index": i, "playerIndex": 0, "type": OPT_CARD} for i in range(3)]
    assert _pick(frame, opts) == {i: frozenset({0, 1, 2}) for i in range(3)}


def test_two_disjoint_classes_in_one_menu_stay_disjoint():
    """`82749168|1|decision|29`'s shape: {4,12} and {5,13}, two Energies onto two identical bodies."""
    frame = _frame(bench=[_body(serial=1), _body(serial=2)],
                   hand=[{"id": 5, "playerIndex": 0, "serial": 40},
                         {"id": 6, "playerIndex": 0, "serial": 41}])
    opts = [{"area": AREA_HAND, "index": h, "inPlayArea": AREA_BENCH, "inPlayIndex": b,
             "playerIndex": 0, "type": OPT_ATTACH} for h in (0, 1) for b in (0, 1)]
    got = _pick(frame, opts)
    assert got == {0: frozenset({0, 1}), 1: frozenset({0, 1}),
                   2: frozenset({2, 3}), 3: frozenset({2, 3})}


def test_a_singleton_is_absent_rather_than_mapped_to_itself():
    """Only NON-TRIVIAL classes are reported, so a caller can test membership with a plain truthiness
    check and an empty map means 'nothing to canonicalise'."""
    frame = _frame(bench=[_body(serial=1), _body(cid=1031, serial=2)])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    assert _pick(frame, opts) == {}


def test_no_options_and_no_frame_are_both_empty_not_an_error():
    assert option_equivalence([], {}) == {}
    assert option_equivalence(None, None) == {}


# ── the engine vocabulary is SOURCED, not remembered ─────────────────────────────────────────────

def test_area_constants_match_the_engine_enums():
    """Importing `cg.api` MAPS THE NATIVE LIBRARY, and `train.gates` imports
    `common.option_equivalence` with no DLL — so the areas are written literally there and pinned here."""
    from cg.api import AreaType
    import common.option_equivalence as oe
    assert oe.AREA_DECK == int(AreaType.DECK)
    assert oe.AREA_HAND == int(AreaType.HAND)
    assert oe.AREA_DISCARD == int(AreaType.DISCARD)
    assert oe.AREA_ACTIVE == int(AreaType.ACTIVE)
    assert oe.AREA_BENCH == int(AreaType.BENCH)
    assert oe.AREA_LOOKING == int(AreaType.LOOKING)


def test_the_unresolvable_zones_are_the_ones_the_snapshot_hides():
    """`_PLAYER_ZONES` membership IS the reveal test, so its ABSENCES matter: DECK and PRIZE are
    face-down, and an equivalence over cards nobody can see is asserted from ignorance."""
    from cg.api import AreaType
    import common.option_equivalence as oe
    assert int(AreaType.DECK) not in oe._PLAYER_ZONES
    assert int(AreaType.PRIZE) not in oe._PLAYER_ZONES


# ── canonicalisation: representatives and the fan-out ────────────────────────────────────────────

def test_the_representative_is_the_LOWEST_index_in_its_class():
    """Deterministic by construction — two processes handed one menu must rank identically, or the
    develop rung's all-or-nothing reproducibility guarantee (#178) is worthless."""
    from common.option_equivalence import class_representatives
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_representatives(equiv, 5) == [0, 1, 2, 4]


def test_every_option_is_a_representative_when_there_are_no_classes():
    from common.option_equivalence import class_representatives
    assert class_representatives({}, 3) == [0, 1, 2]


def test_the_fan_out_gives_every_member_the_class_MAXIMUM():
    """The sound direction: the best continuation reachable from one member is reachable from all,
    so raising the others corrects an omission. The minimum would discard a demonstrated line."""
    from common.option_equivalence import fan_out
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert fan_out([5.0, 1167.0, None, None], equiv) == [5.0, 1167.0, None, 1167.0]


def test_the_fan_out_leaves_an_all_unscored_class_as_None():
    """A class nobody could sim stays unscored — never silently 0.0, which would rank it above a
    genuinely negative option."""
    from common.option_equivalence import fan_out
    equiv = {0: frozenset({0, 1}), 1: frozenset({0, 1})}
    assert fan_out([None, None], equiv) == [None, None]


def test_classes_is_the_ONE_walk_over_a_map():
    """Three call sites had each written this themselves; a second definition of "these are one
    decision" drifts silently, because every copy stays internally consistent."""
    from common.option_equivalence import classes
    equiv = {3: frozenset({1, 3}), 1: frozenset({1, 3}), 4: frozenset({4, 0}), 0: frozenset({4, 0})}
    assert classes(equiv) == [[0, 4], [1, 3]]
    assert classes({}) == [] and classes(None) == []


def test_class_of_defaults_to_the_index_alone():
    from common.option_equivalence import class_of
    equiv = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_of(equiv, 1) == frozenset({1, 3})
    assert class_of(equiv, 7) == frozenset({7})
    assert class_of({}, 7) == frozenset({7})


# ── canonical ordering keys (ADR-0103, Issue #254) ───────────────────────────────────────────────

def test_canonical_keys_are_the_fingerprint_per_option():
    """The key IS the class identity — two options that are one decision share a key, so no tie-break
    between them can ever be positional."""
    from common.option_equivalence import canonical_keys
    frame = _frame(bench=[_body(serial=1), _body(serial=2)])
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    keys = canonical_keys(opts, frame)
    assert keys == [option_fingerprint(opts[0], frame)] * 2


def test_canonical_keys_are_INVARIANT_under_a_menu_permutation():
    """The property the whole fix rests on: permuting the menu (and the bodies it names) permutes the
    keys with it and invents no new ones, so an ordering keyed on them cannot see menu position."""
    from common.option_equivalence import canonical_keys
    a, b = _body(cid=1030, hp=70, serial=1), _body(cid=1030, hp=40, serial=2)
    opts = [{"area": AREA_BENCH, "index": 0, "playerIndex": 0, "type": OPT_CARD},
            {"area": AREA_BENCH, "index": 1, "playerIndex": 0, "type": OPT_CARD}]
    forward = canonical_keys(opts, _frame(bench=[a, b]))
    reversed_ = canonical_keys(opts, _frame(bench=[b, a]))
    assert forward == reversed_[::-1]
    assert len(set(forward)) == 2                    # damaged vs undamaged: two decisions, two keys


def test_an_unfingerprintable_option_gets_the_EMPTY_key():
    """Blind ⇒ conservative, structurally (the module's own rule): a face-down DECK option has no
    canonical identity, so it gets no canonical key and keeps whatever menu position it had."""
    from common.option_equivalence import canonical_keys
    opts = [{"area": AREA_DECK, "index": 0, "playerIndex": 0, "type": OPT_CARD}, {"type": 0}]
    assert canonical_keys(opts, _frame()) == ["", ""]
    assert canonical_keys(None, None) == []
