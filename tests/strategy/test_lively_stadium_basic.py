"""Lively Stadium (1251) and the ``applies_to: "basic"`` resolver (Issue #433).

1251's *"Each Basic Pokémon in play gets +30 HP"* parses to a WRITING `hp_delta` clause, so it
survives the writing-clause filter, reaches `_admits` with no resolver, and comes back *unknown* —
which every reader treats as refuse. ``metal``, ``no_rule_box`` and ``name_family`` are the other
unresolved values, and are re-measured below to still reach no writing clause.
"""
from __future__ import annotations

import pytest

from common import board_delta as bd
from common.strategy.context import _EVOLVE, _PLAY
from pilot_helpers import opt, poke, state

LIVELY_STADIUM = 1251     # "Each Basic Pokémon in play (both yours and your opponent's) gets +30 HP."
GRAVITY_MOUNTAIN = 1252   # "Each Stage 2 Pokémon in play (both yours and your opponent's) gets -30 HP."

#: Riolu -> Mega Lucario ex is a SINGLE hop — no intermediate Lucario in this set
#: (`docs/rulebook.txt` Appendix 1). Stages are ASSERTED below, never trusted from the ids.
RIOLU, MAKUHITA, SOLROCK, LUNATONE, MEOWTH_EX = 677, 673, 676, 675, 1071
MEGA_LUCARIO_EX, HARIYAMA = 678, 674
DRAGAPULT_EX = 121        # Stage 2 — the class Gravity Mountain reaches, used as a live control


@pytest.fixture(scope="module")
def combat():
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot.combat


def _delta(combat, card_id, stat):
    clauses = bd.stadium_clauses_of(combat, card_id, event=bd.STADIUM_STATIC, stat=stat)
    return bd.stadium_hp_delta(clauses, stat)


def test_the_clause_is_a_writing_one_so_the_filter_was_never_what_refused(combat):
    """An EMPTY write-set would mean the FILTER refused rather than `_admits`, and a resolver would
    fix nothing. Gravity Mountain is the positive control: a clause known to survive."""
    for card_id in (LIVELY_STADIUM, GRAVITY_MOUNTAIN):
        clauses = bd.card_clauses(combat, card_id)
        assert len(clauses) == 1, f"{card_id}: the compendium entry is a single clause"
        assert bd._one_clause_writes(combat, card_id, clauses[0]), \
            f"{card_id}: an EMPTY write-set would mean the filter, not `_admits`, is the refusal"


def test_lively_stadium_lifts_a_basic_by_30_and_leaves_every_evolution_alone(combat):
    """The two evolution classes are DISCRIMINATING, not merely quiet: a resolver stuck at True, or
    one keyed on ``evolvesFrom is None`` rather than ``stage``, shows up here as a non-zero delta."""
    stats = {cid: bd._stat(combat, cid) for cid in (RIOLU, MEGA_LUCARIO_EX, DRAGAPULT_EX)}
    assert stats[RIOLU].stage == "basic"
    assert stats[MEGA_LUCARIO_EX].stage == "stage1"
    assert stats[DRAGAPULT_EX].stage == "stage2"

    assert _delta(combat, LIVELY_STADIUM, stats[RIOLU]) == 30
    assert _delta(combat, LIVELY_STADIUM, stats[MEGA_LUCARIO_EX]) == 0
    assert _delta(combat, LIVELY_STADIUM, stats[DRAGAPULT_EX]) == 0


def test_the_symmetric_leg_lifts_ALL_FIVE_of_our_own_basics(combat):
    """⚠️ ``symmetric`` is never READ — `_admits` branches on ``applies_to`` alone and
    `stadium_hp_delta` has no seat dimension — so what this establishes is a SEAT-BLIND predicate."""
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
    """`_admits_basic` returns a plain bool, never *unknown*, on the claim that ``stage`` is TOTAL
    over Pokémon: a body without one would be silently mis-priced rather than refused."""
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
    """A new key in `_APPLIES_TO` must not widen an existing one."""
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, DRAGAPULT_EX)) == -30
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, RIOLU)) == 0
    assert _delta(combat, GRAVITY_MOUNTAIN, bd._stat(combat, MEGA_LUCARIO_EX)) == 0


def test_the_other_three_absent_resolvers_really_do_reach_no_writing_clause(combat):
    """The assertion on the collected keys is the POSITIVE CONTROL: an empty failure list must mean
    the three unresolved values are harmless, not that the sweep never ran."""
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
    """`_evolve` asks about the OLD and NEW body together but prices against the NEW one, which is
    never a Basic, so the lift stops at the hop and the evolved body lands on its printed maximum."""
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
    """Damage carries across as a DELTA: the floating modifier sits in both rendered `hp` and
    `maxHp` and cancels in ``maxHp − hp``, so the carry needed no re-derivation."""
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
    """Gravity Mountain is the POSITIVE CONTROL: the identical deploy succeeds under it, so the
    refusal under Lively is its static reaching a bench arrival, not a generally broken deploy."""
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
    """The refusal is DELIBERATE: `bench_body` mints ``hp = maxHp = stat.hp`` while the engine renders
    an arriving Basic at printed+30, so un-refusing without an applier mints every body 30 HP light."""
    makuhita = bd._stat(combat, MAKUHITA)
    assert makuhita.stage == "basic"

    reaching = bd.stadium_clauses_of(combat, LIVELY_STADIUM, event="bench_play", stat=makuhita)
    assert reaching, "Lively's static reaches a Basic arriving on the Bench"
    with pytest.raises(bd.Unmodellable, match="arriving on the Bench"):
        bd.apply_bench_arrival(bd.bench_body(MAKUHITA, makuhita, seat_index=0, serial=1),
                               reaching, makuhita)

    quiet = bd.stadium_clauses_of(combat, GRAVITY_MOUNTAIN, event="bench_play", stat=makuhita)
    assert quiet == (), "a Basic is not a Stage 2 — the control must be filtered out, not refused"
