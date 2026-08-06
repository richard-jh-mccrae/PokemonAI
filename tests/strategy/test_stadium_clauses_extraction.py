"""`stadium_clauses_for` before and after Issue #424's extraction, executed side by side.

Issue #424 split `board_delta.stadium_clauses_for` into a thin `current["stadium"]` read plus a new
card-keyed core, `stadium_clauses_of`. The claim made for that split was *"a pure extraction — zero
behaviour change to any existing caller"*, and the evidence offered was a green suite and flat
watchdog gates. **That is inference from an absence of failures, not a demonstration of
equivalence**, and `stadium_clauses_for` is not a function that gets accepted on inference: it is a
shared apply-seam predicate on the parity path, reached by `board_delta._evolve` and
`board_delta._play` (twice).

So this file executes both versions over the whole input space and compares them exactly.

## What is compared

**Both outcomes, not just return values.** Each call is reduced to either ``("return", value)`` or
``("raise", <exception type>, <message>)``. A refusal that silently became a return — the precise
regression class `/code-review`'s Spec axis alleged for this diff, and which was refuted by reading
the code — would show up here as a kind mismatch. This is the executing version of that refutation.

**The refusal MESSAGE changed on purpose and this file says so rather than hiding it.** The old text
read *"a Stadium is in play whose effect the seam cannot model"*, which is false of a card still in
hand — the counterfactual caller `pilot._stadium_hp_shift` asks about exactly that. The new text
drops the four words. Message differences are therefore counted and reported SEPARATELY from
outcome-kind and return-value differences, which must be zero.

## What is deliberately out of scope

The ``"static"`` event is **new**, so it has no old counterpart and cannot appear in a differential
comparison by construction. The pre-change `STADIUM_EVENTS` does not contain it, so the old function
raises for it while the new one answers — a difference that is the feature, not a regression. It is
asserted directly in :func:`test_the_static_event_is_new_by_construction` rather than silently
omitted from the sweep.

## The vendored copy

`_PRE_424_SOURCE` is the CODE of `stadium_clauses_for` copied verbatim from
``git show 55017df0:src/common/board_delta.py`` (its docstring, which is prose only, replaced by a
one-line marker). `55017df0` is the correct pre-change ref: it is this commit's parent, and
`board_delta.py` is byte-identical there to `278063cc` (PR #430's merge) because Issue #425's commit
in between touched only `strategy.py` and one test file — asserted at 61369 characters.

It is executed against the CURRENT module's collaborators (`_admits`, `card_clauses`,
`_one_clause_writes`, `_TRIGGER_EVENTS`), which is the honest scope: this is a differential test of
`stadium_clauses_for` itself, holding everything it calls fixed. Of those collaborators only
`STADIUM_EVENTS` changed at all, and this file overrides it back to its pre-change value and asserts
the two differ by exactly ``{"static"}``.
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
    """The pre-Issue-#424 `stadium_clauses_for`, built over the CURRENT module's collaborators.

    ``mutation`` is ``(old, new)`` applied to the vendored source — the positive control's lever.
    Asserted to actually change the text, so a typo in the mutation cannot masquerade as a passing
    control."""
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
    """A body-class spread that actually exercises `_admits`, plus the two shapes it accepts.

    Real cards, every class verified at source in `data/EN_Card_Data.csv`: Riolu is a Basic
    non-{D}, Zorua a Basic **{D}** (the one class `_admits_basic_non_dark` answers False for),
    Hariyama a Stage 1, Dragapult ex a Stage 2. `None` is the no-body-class case, which `_admits`
    resolves to *unknown*; the tuples are the `stage_change` form, where an old and a new body are
    asked together. Read through `board_delta._stat`, the module's OWN accessor (ADR-0056's Stat
    Provider seam), so the bodies reach `_admits` exactly as they do in production."""
    riolu, zorua = bd._stat(combat, 677), bd._stat(combat, 136)
    hariyama, dragapult = bd._stat(combat, 674), bd._stat(combat, 121)
    assert riolu and zorua and hariyama and dragapult, "the stat provider did not return a body"
    # The classes are the whole point of the spread — assert them rather than trusting the ids.
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
    """Every Stadium in the pool as the in-play card, plus the EMPTY zone.

    Card ids 1242–1267 are the 26 Stadiums in `data/EN_Card_Data.csv`; the empty zone is the
    early-return path the extraction moved, so it is the one state most worth including."""
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


def test_the_extraction_changed_no_outcome_on_any_input(combat, bodies, stadium_states):
    """27 stadium states × 3 pre-existing events × 7 body classes = **567 cells**, both versions.

    Zero may differ in outcome KIND or RETURN VALUE. Message-only differences would be permitted —
    the refusal text deliberately lost the words *"is in play"*, which are false of a card still in
    hand — but **measured, there are none**, because no cell in the comparable space reaches the
    re-raise at all (see the coverage assertions below). The rewording is therefore provably
    unobservable here; the other refusal path, an unrecognised ``event``, is covered by
    :func:`test_an_unknown_event_still_refuses_before_the_zone_is_read`."""
    new_fn, old_fn = bd.stadium_clauses_for, _pre424()
    same, message_only, real = _sweep(new_fn, old_fn, combat, bodies, stadium_states)

    assert len(same) + len(message_only) + len(real) == 567
    assert not real, f"{len(real)} cell(s) changed outcome: {real[:3]}"
    for cell, old_msg, new_msg in message_only:                  # permitted, but assert the shape
        assert new_msg == old_msg.replace("a Stadium is in play whose", "a Stadium whose", 1), cell

    # ── the sweep DESCRIBES ITS OWN COVERAGE, so "567 matched" cannot be 567 trivial cells ──
    # Without this, a provider that returned no clauses at all would make every cell an identical
    # empty tuple and the test would pass while proving nothing.
    outcomes = [_outcome(new_fn, current, combat, event=event, stat=bodies[body])
                for (_n, current), event, body in itertools.product(
                    stadium_states, _COMPARABLE_EVENTS, sorted(bodies))]
    assert all(o[0] == "return" for o in outcomes), "no pool Stadium refuses on a valid event"
    assert sum(1 for o in outcomes if o[1]) == 65, \
        "65 of the 567 cells return a NON-EMPTY clause tuple — the ones that do real selection work"


def test_the_comparator_can_actually_fail(combat, bodies, stadium_states):
    """**The positive control, and it is mandatory.** *"Found no differences"* and *"my comparator is
    broken"* produce identical output, so the sweep above proves nothing until this passes.

    Two independent mutations of the vendored old function, each of which MUST make the comparator
    report real differences: inverting the trigger event filter, and inverting the `_admits` gate."""
    for mutation in [("if on != event:", "if on == event:"),
                     ("if _admits(clause, stats) is not False:",
                      "if _admits(clause, stats) is False:")]:
        _same, _msg, real = _sweep(bd.stadium_clauses_for, _pre424(mutation),
                                   combat, bodies, stadium_states)
        assert real, f"the comparator is BLIND: mutation {mutation} produced no difference"


def test_the_static_event_is_new_by_construction(combat, bodies):
    """`"static"` has no old counterpart, so it is out of the sweep by construction rather than by
    omission — the old vocabulary refuses it, the new one answers.

    Asserted here so the exclusion is visible instead of implicit."""
    assert bd.STADIUM_EVENTS - _PRE_424_EVENTS == {"static"}, "only `static` may have been added"
    assert _PRE_424_EVENTS - bd.STADIUM_EVENTS == set(), "no event may have been removed"

    gravity_mountain = {"stadium": [{"id": 1252}]}
    stage2 = bodies["stage2"]
    assert _outcome(_pre424(), gravity_mountain, combat,
                    event="static", stat=stage2)[0] == "raise"
    assert bd.stadium_clauses_for(gravity_mountain, combat,
                                  event="static", stat=stage2) != ()


def test_an_unknown_event_still_refuses_before_the_zone_is_read(combat):
    """The regression `/code-review`'s Spec axis alleged and this file exists to settle by executing.

    The claim was that the extraction moved the `event` validation AFTER the empty-zone early
    return, so a typo'd event on a board with no Stadium would fail OPEN. Both versions must raise,
    with and without a Stadium in play."""
    for current in ({}, {"stadium": [{"id": 1252}]}):
        for fn in (bd.stadium_clauses_for, _pre424()):
            assert _outcome(fn, current, combat, event="stage_chnage", stat=None)[0] == "raise"
