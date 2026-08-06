"""Lively Stadium (1251) and the ``applies_to: "basic"`` resolver (Issue #433).

`board_delta._APPLIES_TO` shipped with two resolvers and a docstring asserting the other four
``applies_to`` values reach only clauses whose write-set is EMPTY, *"a reader for a case that cannot
occur"*. **Card 1251 falsifies that for ``basic``**: *"Each Basic Pokémon in play (both yours and
your opponent's) gets +30 HP"* (`data/EN_Card_Data.csv`) parses to a WRITING `hp_delta` clause
(`src/common/card_effects.json`), so it survives the writing-clause filter, reaches `_admits` with no
resolver, and comes back *unknown* — which every reader treats as refuse.

## What this file tests

* **The resolver answers** — +30 for a Basic, 0 for a Stage 1 and a Stage 2 (acceptance criterion 3).
* **The symmetric leg reaches OUR side too.** 1251 is ``symmetric: true`` and all five of this deck's
  Basics — Riolu, Solrock, Lunatone, Makuhita, Meowth ex — are lifted by it (criterion 7). That is
  the opposite of Gravity Mountain, whose self-side is structurally silent here because the deck runs
  no Stage 2, so this is the first Stadium whose self-side is *live* rather than *correctly quiet*.
* **The acceptance-criterion-5 ruling, in executable form.** The resolver un-refuses `_evolve` and
  does **not** un-refuse `_play`, and neither half is a choice — see the two tests at the bottom,
  which is where the reasoning is recorded.

## The three absent resolvers that stay absent

``metal`` (1244 Full Metal Lab), ``no_rule_box`` (1247 Neutralization Zone) and ``name_family``
(1255 Postwick) are the other unresolved values in the pool, and for them the original claim is
**true and re-measured here**: each reaches only a `damage_reduction` / `prevent_damage` /
`damage_boost` clause whose `snapshot_coverage` write-set is empty, so none survives the filter.
`test_the_other_three_absent_resolvers_really_do_reach_no_writing_clause` is the measurement, so the
corrected docstring rests on a re-run rather than on the note it replaces.
"""
from __future__ import annotations

import pytest

from common import board_delta as bd
from common.strategy.context import _EVOLVE, _PLAY
from pilot_helpers import opt, poke, state

LIVELY_STADIUM = 1251     # "Each Basic Pokémon in play (both yours and your opponent's) gets +30 HP."
GRAVITY_MOUNTAIN = 1252   # "Each Stage 2 Pokémon in play (both yours and your opponent's) gets -30 HP."

#: The mega_lucario deck's five Basics and its two Stage 1s (`data/EN_Card_Data.csv`; the
#: Riolu -> Mega Lucario ex single hop is stated outright in `docs/rulebook.txt` Appendix 1 — there is
#: no intermediate Lucario in this set). Stages are ASSERTED below, never trusted from the ids.
RIOLU, MAKUHITA, SOLROCK, LUNATONE, MEOWTH_EX = 677, 673, 676, 675, 1071
MEGA_LUCARIO_EX, HARIYAMA = 678, 674
DRAGAPULT_EX = 121        # Stage 2 — the class Gravity Mountain reaches, used as a live control


@pytest.fixture(scope="module")
def combat():
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot.combat


def _delta(combat, card_id, stat):
    """The shipped read, end to end: select the clauses, then price them."""
    clauses = bd.stadium_clauses_of(combat, card_id, event=bd.STADIUM_STATIC, stat=stat)
    return bd.stadium_hp_delta(clauses, stat)


def test_the_clause_is_a_writing_one_so_the_filter_was_never_what_refused(combat):
    """The premise, executed rather than read. If 1251's clause had an EMPTY write-set it would be
    dropped by `stadium_clauses_of`'s writing-clause filter and never reach `_admits` at all — in
    which case a resolver would fix nothing and this whole file would be aimed at the wrong line.

    Gravity Mountain is the **positive control**: the same call on a clause known to survive returns
    the same non-empty union, so an empty answer above would be a broken instrument rather than a
    filtered clause."""
    for card_id in (LIVELY_STADIUM, GRAVITY_MOUNTAIN):
        clauses = bd.card_clauses(combat, card_id)
        assert len(clauses) == 1, f"{card_id}: the compendium entry is a single clause"
        assert bd._one_clause_writes(combat, card_id, clauses[0]), \
            f"{card_id}: an EMPTY write-set would mean the filter, not `_admits`, is the refusal"


def test_lively_stadium_lifts_a_basic_by_30_and_leaves_every_evolution_alone(combat):
    """Acceptance criterion 3, asserted on the shipped arithmetic.

    The two evolution classes are **discriminating, not merely quiet**: a resolver that answered True
    for everything would show up here as +30 on a Stage 1 and a Stage 2, and a resolver keyed on
    ``evolvesFrom is None`` instead of on ``stage`` would answer the same True for both Basics and
    diverge only on a card the pool does not have. The 0s are the class test working."""
    stats = {cid: bd._stat(combat, cid) for cid in (RIOLU, MEGA_LUCARIO_EX, DRAGAPULT_EX)}
    assert stats[RIOLU].stage == "basic"
    assert stats[MEGA_LUCARIO_EX].stage == "stage1"
    assert stats[DRAGAPULT_EX].stage == "stage2"

    assert _delta(combat, LIVELY_STADIUM, stats[RIOLU]) == 30
    assert _delta(combat, LIVELY_STADIUM, stats[MEGA_LUCARIO_EX]) == 0
    assert _delta(combat, LIVELY_STADIUM, stats[DRAGAPULT_EX]) == 0


def test_the_symmetric_leg_lifts_ALL_FIVE_of_our_own_basics(combat):
    """Acceptance criterion 7. ``symmetric: true`` means 1251 reaches our board as well as theirs,
    and unlike Gravity Mountain — silent on this deck because it runs no Stage 2 — the self-side here
    is **live**: every Basic we play gains 30 HP while it is out.

    The two Stage 1s are the discriminating half. Without them a resolver stuck at True would pass.

    ⚠️ **What this does NOT prove, stated rather than implied.** The ``symmetric`` key is never read
    by `board_delta` or by `pilot` — `_admits` branches on ``applies_to`` alone (the one
    ``clause.get("applies_to")`` in the module) and `stadium_hp_delta` has no seat dimension at all,
    so this test would pass unchanged if 1251's clause said ``symmetric: false``. What it establishes
    is the half that matters for AC7 and is actually in the code: the predicate is **seat-blind**, so
    our Basics are priced by exactly the call that prices theirs, and no self-side exemption exists to
    be forgotten. Making ``symmetric`` load-bearing would need a seat-aware `stadium_hp_delta`, which
    is a wider change than Issue #433 and is NOT what this asserts. The same limitation applies to
    Issue #424's Gravity Mountain symmetric test, which this mirrors."""
    for cid in (RIOLU, MAKUHITA, SOLROCK, LUNATONE, MEOWTH_EX):
        stat = bd._stat(combat, cid)
        assert stat.stage == "basic", f"{cid} {stat.name} is not a Basic — the fixture is wrong"
        assert _delta(combat, LIVELY_STADIUM, stat) == 30, f"{cid} {stat.name} was not lifted"

    for cid in (MEGA_LUCARIO_EX, HARIYAMA):
        stat = bd._stat(combat, cid)
        assert stat.stage == "stage1", f"{cid} {stat.name} is not a Stage 1 — the fixture is wrong"
        assert _delta(combat, LIVELY_STADIUM, stat) == 0, \
            f"{cid} {stat.name} was lifted, so the class test is dead rather than passing"


def test_every_pokemon_in_the_pool_carries_a_stage_so_the_resolver_never_answers_unknown(combat):
    """`_admits_basic`'s docstring justifies returning a plain bool — never *unknown* — on the claim
    that ``stage`` is total over Pokémon, unlike `_admits_basic_non_dark`'s ``energyType``. That is a
    census, so it is measured here rather than asserted in prose only.

    If a future set ships a Pokémon with no ``stage``, `_is_basic` would silently answer False and
    Lively's lift would be dropped from a body that deserves it — a mis-price, not a refusal. This
    test is what turns that into a build failure."""
    stages = {card_id: getattr(stat, "stage", None)
              for card_id, stat in ((c, bd._stat(combat, c)) for c in range(1, 1300))
              if stat is not None and getattr(stat, "is_pokemon", False)}

    assert len(stages) == 1061, "the pool census moved — re-derive the counts below before editing"
    counts = {s: sum(1 for v in stages.values() if v == s) for s in ("basic", "stage1", "stage2")}
    assert counts == {"basic": 600, "stage1": 345, "stage2": 116}
    assert sum(counts.values()) == len(stages), \
        f"{[c for c, s in stages.items() if s is None]} carry no `stage` — `_admits_basic` would " \
        f"answer False for a body whose class it cannot actually see"


def test_gravity_mountain_is_untouched_by_the_new_resolver(combat):
    """The `stage2` resolver answers exactly as before — a new key in `_APPLIES_TO` must not widen
    an existing one. Both classes asserted, so a resolver table that had started matching on the
    wrong key would fail here rather than pass by omission."""
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, DRAGAPULT_EX)) == -30
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, RIOLU)) == 0
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, MEGA_LUCARIO_EX)) == 0


def test_the_other_three_absent_resolvers_really_do_reach_no_writing_clause(combat):
    """`_APPLIES_TO`'s corrected docstring keeps the *"a case that cannot occur"* claim for the
    remaining three values, so this re-measures it rather than inheriting it.

    Every Stadium in the pool (1242–1267) is swept; any clause whose ``applies_to`` has no resolver
    must have an EMPTY write-set, i.e. be dropped by the filter before `_admits` is ever consulted.
    The assertion on the collected keys is the **positive control**: the sweep really did find the
    three unresolved values, so an empty failure list means they are harmless rather than that the
    loop never ran."""
    unresolved = {}
    for card_id in range(1242, 1268):
        for clause in bd.card_clauses(combat, card_id):
            key = clause.get("applies_to")
            if key is not None and key not in bd._APPLIES_TO:
                unresolved[key] = unresolved.get(key, ()) + (card_id,)
                assert not bd._one_clause_writes(combat, card_id, clause), (
                    f"{card_id}: `applies_to` {key!r} has no resolver AND writes the board — the "
                    f"same gap Issue #433 fixed for `basic`, in a second place")

    assert set(unresolved) == {"metal", "no_rule_box", "name_family"}, \
        f"the sweep found {sorted(unresolved)} — `basic` must be resolved and nothing new unresolved"


# ── acceptance criterion 5: the ruling on `_evolve` and `_play`, executed ──────────────────────────

def test_evolving_under_lively_stadium_STOPS_refusing_and_lands_on_the_printed_maximum(combat):
    """**AC5, first half — `_evolve` un-refuses, and that is correct rather than merely permitted.**

    `_evolve` asks `stadium_clauses_for` about the OLD and the NEW body together (the delta may start
    or stop applying) and then prices `stadium_hp_delta` against the **new body only**. Under 1251
    the new body of an evolution is never a Basic — an Evolution card by definition is not — so the
    delta is always 0 and the evolved body lands on its printed maximum. Riolu (80 HP, rendered 110
    under Lively) evolving into Mega Lucario ex must therefore arrive at 340/340, not 370/370.

    Damage already taken carries across as a DELTA and is invariant to the floating modifier, since
    the rendered `hp` and `maxHp` both carry it and it cancels in the subtraction — asserted at the
    entry point by :func:`test_evolving_under_lively_stadium_at_the_REAL_entry_point`."""
    riolu, mega = bd._stat(combat, RIOLU), bd._stat(combat, MEGA_LUCARIO_EX)
    clauses = bd.stadium_clauses_of(combat, LIVELY_STADIUM, event="stage_change",
                                    stat=(riolu, mega))
    assert clauses, "the clause must still REACH the transition — it is the arithmetic that answers 0"
    assert bd.stadium_hp_delta(clauses, mega) == 0, \
        "an evolved body is never a Basic, so Lively's lift stops applying"

    # The old body's class is what the tuple form is for: the delta really did apply BEFORE the hop.
    assert bd.stadium_hp_delta(clauses, riolu) == 30, \
        "the pre-evolution Basic WAS lifted — the tuple form is live, not dead"


def test_evolving_under_lively_stadium_at_the_REAL_entry_point(combat):
    """The same ruling driven through `board_delta._evolve` itself, because that is the production
    path Issue #433 made newly reachable and the assertions above stop one call short of it.

    Three boards, one call. Under no Stadium and under Gravity Mountain the evolution already worked;
    under Lively Stadium it **refused before this change** and now lands on the printed 340/340 — not
    370/370, because a Stage 1 is not a Basic and the lift stops at the hop.

    The damaged case is the invariance leg: 30 damage on the pre-evolution Riolu (rendered 80/110
    under Lively) carries across as a DELTA, so the evolved body is 310/340. The floating modifier
    cancels in ``maxHp − hp``, which is why applying the Stadium needed no re-derivation of the
    carry."""
    def evolve(stadium, *, damage=0):
        lift = 30 if stadium == LIVELY_STADIUM else 0
        rendered_max = int(bd._stat(combat, RIOLU).hp) + lift
        cur = state(active=poke(RIOLU, hp=rendered_max - damage, max_hp=rendered_max),
                    hand=[MEGA_LUCARIO_EX], opp_active=poke(DRAGAPULT_EX, hp=320),
                    turn=6, prizes=6, opp_prizes=6)
        if stadium is not None:
            cur["stadium"] = [{"id": stadium, "serial": 900, "playerIndex": 1}]
        delta = bd._evolve({"current": cur},
                           opt(_EVOLVE, index=0, inPlayArea=bd.AREA_ACTIVE, inPlayIndex=0),
                           seat_index=0, combat=combat)
        body = delta.obs["current"]["players"][0]["active"][0]
        return body["id"], body["hp"], body["maxHp"]

    assert evolve(None) == (MEGA_LUCARIO_EX, 340, 340)              # the pre-existing baseline
    assert evolve(GRAVITY_MOUNTAIN) == (MEGA_LUCARIO_EX, 340, 340)  # reaches no Stage 1 — control
    assert evolve(LIVELY_STADIUM) == (MEGA_LUCARIO_EX, 340, 340), \
        "the lift must STOP at the hop — 370 here would mean a Stage 1 kept a Basic's bonus"
    assert evolve(LIVELY_STADIUM, damage=30) == (MEGA_LUCARIO_EX, 310, 340), \
        "damage carries as a DELTA and is invariant to the floating modifier"


def test_playing_a_basic_under_lively_stadium_refuses_at_the_REAL_entry_point(combat):
    """The other half of the ruling, driven through `board_delta._play`.

    Gravity Mountain is the **positive control** and it is the whole point of the test: the identical
    deploy succeeds under it, so the refusal under Lively is that Stadium's static reaching a bench
    arrival — not the deploy being broken generally."""
    def play(stadium):
        cur = state(active=poke(RIOLU, hp=80, max_hp=80), hand=[MAKUHITA],
                    opp_active=poke(DRAGAPULT_EX, hp=320), turn=6, prizes=6, opp_prizes=6)
        if stadium is not None:
            cur["stadium"] = [{"id": stadium, "serial": 900, "playerIndex": 1}]
        return bd._play({"current": cur}, opt(_PLAY, index=0), seat_index=0, combat=combat)

    for control in (None, GRAVITY_MOUNTAIN):
        benched = play(control).obs["current"]["players"][0]["bench"]
        assert [(b["id"], b["hp"], b["maxHp"]) for b in benched] == [(MAKUHITA, 80, 80)]

    with pytest.raises(bd.Unmodellable, match="arriving on the Bench"):
        play(LIVELY_STADIUM)


def test_playing_a_basic_to_the_bench_under_lively_stadium_STILL_REFUSES(combat):
    """**AC5, second half — `_play` keeps refusing, and the resolver is not what decides that.**

    Measured before and after the resolver: the refusal is unchanged in both site and message. It
    comes from `apply_bench_arrival`, which has an applier for a `stadium_trigger`'s damage counters
    and for nothing else, so a `stadium_static` reaching a bench arrival raises there — a path
    `_admits` never gets to influence, because `stadium_clauses_of` returns the clause under the
    resolver (True) exactly as it did under no resolver (unknown, fail-closed).

    **Keeping it is the ruling, not an omission.** `bench_body` mints ``hp = maxHp = stat.hp``, the
    printed maximum; under Lively the engine renders an arriving Basic at ``printed + 30``
    (`cgpy/render.py:pokemon_dict` adds the floating delta at render). Un-refusing without an applier
    would therefore mint a body 30 HP light on every deploy — a silently wrong board in the one place
    this seam exists to keep honest. Widening it needs a bench-arrival applier for the static case,
    which is the apply/parity seam and its own work; refusing costs nothing today (1251 is in no
    agent decklist and in 0 of the 377 committed parity traces).

    Gravity Mountain is the **positive control**: it reaches the same call site on the same event and
    is correctly filtered out by `_admits` (a Basic is not a Stage 2), so the empty tuple there proves
    the refusal above is Lively's clause and not the call itself."""
    makuhita = bd._stat(combat, MAKUHITA)
    assert makuhita.stage == "basic"

    reaching = bd.stadium_clauses_of(combat, LIVELY_STADIUM, event="bench_play", stat=makuhita)
    assert reaching, "Lively's static reaches a Basic arriving on the Bench"
    with pytest.raises(bd.Unmodellable, match="arriving on the Bench"):
        bd.apply_bench_arrival(bd.bench_body(MAKUHITA, makuhita, seat_index=0, serial=1),
                               reaching, makuhita)

    quiet = bd.stadium_clauses_of(combat, GRAVITY_MOUNTAIN, event="bench_play", stat=makuhita)
    assert quiet == (), "a Basic is not a Stage 2 — the control must be filtered out, not refused"
