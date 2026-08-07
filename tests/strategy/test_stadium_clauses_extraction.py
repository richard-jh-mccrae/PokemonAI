"""`stadium_clauses_for` before and after Issue #424's extraction, executed side by side.

The vendored pre-change copy runs against the CURRENT module's collaborators, so this is a
differential on `stadium_clauses_for` ALONE, holding everything it calls fixed. Both halves of each
outcome are compared — a refusal that became a return shows up as a kind mismatch — and the refusal
MESSAGE lost four words on purpose, so message-only differences are counted separately.

The `"static"` event is NEW and therefore outside the differential by construction; Issue #433's
`basic` resolver is likewise invisible to it (`_admits` is a fixed collaborator) and shows up instead
in the coverage half, cell by cell in `_RESOLVED_AWAY`.
"""
from __future__ import annotations

import itertools
import types

import pytest

from common import board_delta as bd

#: `stadium_clauses_for`'s CODE at `55017df0` — the last commit before Issue #424. Verbatim.
_PRE_424_SOURCE = '''
def stadium_clauses_for_pre424(current: dict, combat, *, event: str, stat=None) -> tuple:
    """(docstring omitted — the vendored copy carries CODE only)"""
    if event not in STADIUM_EVENTS:
        raise Unmodellable(f"stadium_clauses_for: {event!r} is not one of {sorted(STADIUM_EVENTS)}")
    card = (current.get("stadium") or [None])[0]
    if not card:
        return ()
    card_id = card.get("id")
    stats = tuple(stat) if isinstance(stat, (tuple, list)) else (stat,)
    out = []
    try:
        for clause in card_clauses(combat, card_id):
            if not _one_clause_writes(combat, card_id, clause):
                continue
            if event == "displace":
                out.append(clause)
                continue
            kind = clause.get("kind")
            if kind == "stadium_trigger":
                on = clause.get("on")
                if on not in _TRIGGER_EVENTS:
                    out.append(clause)              # unknown `on` -- fail closed
                    continue
                if on != event:
                    continue
            elif kind != "stadium_static":
                out.append(clause)                  # unknown clause kind -- fail closed
                continue
            if _admits(clause, stats) is not False:
                out.append(clause)                  # True, or unknown -- fail closed
    except Unmodellable as gap:
        raise Unmodellable(f"a Stadium is in play whose effect the seam cannot model -- {gap}")
    return tuple(out)
'''

#: `STADIUM_EVENTS` as it stood at `55017df0`. The ONE collaborator Issue #424 changed.
_PRE_424_EVENTS = frozenset({"bench_play", "stage_change", "displace"})

#: The three events that existed before Issue #424 — the whole comparable space.
_COMPARABLE_EVENTS = ("bench_play", "stage_change", "displace")


def _pre424(mutation: tuple[str, str] | None = None):
    """`mutation` is `(old, new)` applied to the vendored source — the positive control's lever, and
    asserted to change the text so a typo cannot masquerade as a passing control."""
    source = _PRE_424_SOURCE
    if mutation is not None:
        assert mutation[0] in source, f"mutation target {mutation[0]!r} is not in the vendored source"
        source = source.replace(*mutation, 1)
        assert source != _PRE_424_SOURCE
    module = types.ModuleType("board_delta_pre424")
    module.__dict__.update(bd.__dict__)
    module.__dict__["STADIUM_EVENTS"] = _PRE_424_EVENTS          # the pre-change vocabulary
    exec(compile(source, "<board_delta @ 55017df0>", "exec"), module.__dict__)
    return module.__dict__["stadium_clauses_for_pre424"]


def _outcome(fn, current, combat, *, event, stat):
    """``("return", value)`` or ``("raise", type name, message)`` — both halves of what a call does."""
    try:
        return ("return", fn(current, combat, event=event, stat=stat))
    except Exception as exc:                                     # noqa: BLE001 — the comparison IS the point
        return ("raise", type(exc).__name__, str(exc))


@pytest.fixture(scope="module")
def combat():
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot.combat


@pytest.fixture(scope="module")
def bodies(combat):
    """`None` is the no-body-class case (`_admits` resolves it to *unknown*); the tuples are the
    `stage_change` form, where an old and a new body are asked together."""
    riolu, zorua = bd._stat(combat, 677), bd._stat(combat, 136)
    hariyama, dragapult = bd._stat(combat, 674), bd._stat(combat, 121)
    assert riolu and zorua and hariyama and dragapult, "the stat provider did not return a body"
    # The classes are the whole point of the spread — assert them rather than trusting the ids.
    # Zorua is the one class `_admits_basic_non_dark` answers False for.
    assert riolu.stage == "basic" and zorua.stage == "basic"
    assert zorua.energyType == 7 and riolu.energyType != 7        # EnergyType.DARKNESS
    assert hariyama.stage == "stage1" and dragapult.stage == "stage2"
    return {
        "basic_non_dark": riolu,
        "basic_dark": zorua,
        "stage1": hariyama,
        "stage2": dragapult,
        "none": None,
        "tuple_stage1_stage2": (hariyama, dragapult),
        "tuple_basic_stage1": (riolu, hariyama),
    }


@pytest.fixture(scope="module")
def stadium_states():
    """Card ids 1242–1267 are every Stadium in the pool; the EMPTY zone is the early-return path the
    extraction moved, so it is the one state most worth including."""
    return [("none", {})] + [(str(cid), {"stadium": [{"id": cid}]}) for cid in range(1242, 1268)]


def _sweep(new_fn, old_fn, combat, bodies, stadium_states):
    """Every (stadium × event × body-class) cell, both versions. Returns the three difference lists."""
    same, message_only, real = [], [], []
    for (sname, current), event, bname in itertools.product(
            stadium_states, _COMPARABLE_EVENTS, sorted(bodies)):
        cell = f"stadium={sname} event={event} body={bname}"
        got = _outcome(new_fn, current, combat, event=event, stat=bodies[bname])
        want = _outcome(old_fn, current, combat, event=event, stat=bodies[bname])
        if got == want:
            same.append(cell)
        elif got[:2] == want[:2] and got[0] == "raise":
            message_only.append((cell, want[2], got[2]))
        else:
            real.append((cell, want, got))
    return same, message_only, real


#: The cells Issue #433's `basic` resolver moved from NON-EMPTY to empty: Lively Stadium (1251)
#: against a body its clause does not reach, on the two body-scoped events only.
_RESOLVED_AWAY = frozenset({("1251", event, body)
                            for event in ("bench_play", "stage_change")
                            for body in ("stage1", "stage2", "tuple_stage1_stage2")})


def _assert_the_only_movement_is_the_1251_resolver(non_empty: set) -> None:
    """A bare count would be satisfied by any six cells going quiet. Naming which six, and which 1251
    cells must still be non-empty, catches a resolver that reached too far."""
    assert not (_RESOLVED_AWAY & non_empty), (
        f"{sorted(_RESOLVED_AWAY & non_empty)} should have been resolved AWAY by `_admits_basic` — "
        f"Lively Stadium does not reach an evolved body")

    lively = {(event, body) for stadium, event, body in non_empty if stadium == "1251"}
    by_event = {e: sorted(b for ev, b in lively if ev == e)
                for e in ("bench_play", "stage_change", "displace")}
    reached = ["basic_dark", "basic_non_dark", "none", "tuple_basic_stage1"]
    assert by_event["bench_play"] == reached, "the Basic classes must still be REACHED, not filtered"
    assert by_event["stage_change"] == reached, "same, on the other body-scoped event"
    assert len(by_event["displace"]) == 7, \
        "`displace` returns every writing clause regardless of `applies_to` — it must NOT have moved"


def test_the_extraction_changed_no_outcome_on_any_input(combat, bodies, stadium_states):
    """27 stadium states × 3 pre-existing events × 7 body classes, both versions. Message-only
    differences are permitted; outcome KIND and RETURN VALUE differences are not."""
    new_fn, old_fn = bd.stadium_clauses_for, _pre424()
    same, message_only, real = _sweep(new_fn, old_fn, combat, bodies, stadium_states)

    assert len(same) + len(message_only) + len(real) == 567
    assert not real, f"{len(real)} cell(s) changed outcome: {real[:3]}"
    for cell, old_msg, new_msg in message_only:                  # permitted, but assert the shape
        assert new_msg == old_msg.replace("a Stadium is in play whose", "a Stadium whose", 1), cell

    # A provider returning no clauses at all would make every cell an identical empty tuple, so the
    # sweep must describe its own coverage or "all matched" means nothing.
    cells = [((sname, event, body),
              _outcome(new_fn, current, combat, event=event, stat=bodies[body]))
             for (sname, current), event, body in itertools.product(
                 stadium_states, _COMPARABLE_EVENTS, sorted(bodies))]
    assert all(o[0] == "return" for _cell, o in cells), "no pool Stadium refuses on a valid event"

    non_empty = {cell for cell, o in cells if o[1]}
    assert len(non_empty) == 59, (
        "59 of the 567 cells return a NON-EMPTY clause tuple — the ones that do real selection "
        "work. Was 65 before Issue #433 added the `basic` resolver; 65 − 6 = 59, and the six are "
        "named individually below.")
    _assert_the_only_movement_is_the_1251_resolver(non_empty)


def test_the_comparator_can_actually_fail(combat, bodies, stadium_states):
    """The positive control: "found no differences" and "my comparator is broken" produce identical
    output, so the sweep above proves nothing until this passes."""
    for mutation in [("if on != event:", "if on == event:"),
                     ("if _admits(clause, stats) is not False:",
                      "if _admits(clause, stats) is False:")]:
        _same, _msg, real = _sweep(bd.stadium_clauses_for, _pre424(mutation),
                                   combat, bodies, stadium_states)
        assert real, f"the comparator is BLIND: mutation {mutation} produced no difference"


def test_the_static_event_is_new_by_construction(combat, bodies):
    """The old vocabulary refuses `"static"` and the new one answers, so the exclusion from the sweep
    is by construction rather than by omission."""
    assert bd.STADIUM_EVENTS - _PRE_424_EVENTS == {"static"}, "only `static` may have been added"
    assert _PRE_424_EVENTS - bd.STADIUM_EVENTS == set(), "no event may have been removed"

    gravity_mountain = {"stadium": [{"id": 1252}]}
    stage2 = bodies["stage2"]
    assert _outcome(_pre424(), gravity_mountain, combat,
                    event="static", stat=stage2)[0] == "raise"
    assert bd.stadium_clauses_for(gravity_mountain, combat,
                                  event="static", stat=stage2) != ()


def test_an_unknown_event_still_refuses_before_the_zone_is_read(combat):
    """The alleged regression: `event` validation moved AFTER the empty-zone early return, so a
    typo'd event on a Stadium-less board would fail OPEN."""
    for current in ({}, {"stadium": [{"id": 1252}]}):
        for fn in (bd.stadium_clauses_for, _pre424()):
            assert _outcome(fn, current, combat, event="stage_chnage", stat=None)[0] == "raise"
