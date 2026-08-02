"""The **Damage Formula's** scaler context — the ONE builder, and the model's direction-aware
accessor (Issue #279, POC-T3.5).

Three claims are pinned here, in the order they matter:

1. **One builder.** :func:`common.strategy.damage_context.damage_context` owns the key vocabulary,
   and both live suppliers — the Pilot and the StateModel — assemble through it from the SAME
   fact-gatherer. The parity test is what keeps that honest: two hand-rolled builders of one fact
   are free to drift, and `CombatMath.card_level_damage` exists because a pair of them did
   (`combat.py`: *"One fact, two hand-rolled call sites, free to drift — and they did."*).
2. **Direction.** The Formula's variables are named relative to the ATTACKER (`atk_*` / `def_*`),
   so "their attack on me" and "my attack on them" are different dicts, not one dict read twice.
   The `both_` class is the one direction-symmetric exception (ADR-0083, Issue #213).
3. **Identity stability.** The model memoizes per direction, so the returned dict is the SAME
   object for the model's lifetime. Every clock memo downstream keys the context through
   `_Lazily._key`, whose per-object projection cache is only paid once for a stable dict — a fresh
   dict per call re-canonicalises the whole context on every read and grows that cache without
   bound.

**No scoring change is asserted here and none is intended** (Issue #279's acceptance): nothing
consumes `StateModel.damage_context` yet, so both gates must stay byte-identical. What this file
guards is that the extraction did not move the Pilot's answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from common.state_model import StateModel
from common.strategy.damage_context import SideFacts, damage_context

REPO = Path(__file__).resolve().parents[2]


# ── the assembler, pure ───────────────────────────────────────────────────────────────────────────

def _facts(**kw) -> SideFacts:
    return SideFacts(**kw)


@pytest.mark.req("REQ-DMGCTX-0001")
def test_an_empty_pair_of_sides_claims_nothing_but_still_answers_every_key():
    """Fail-closed: an absent field contributes its IDENTITY (0 / empty), never a guess — and never
    a missing key, because the oracle's `context.get(var) is not None` test is what decides whether
    a scaler is priced at all (`strategy/damage.py`)."""
    ctx = damage_context(_facts(), _facts())
    assert ctx["atk_hand"] == 0 and ctx["def_hand"] == 0
    assert ctx["both_bench"] == 0 and ctx["both_active_energy"] == 0
    assert ctx["atk_discard_basic_by_type"] == {}
    assert ctx["atk_bench_names"] == () and ctx["atk_boosts"] == ()
    assert "atk_deck_count" not in ctx and "atk_deck_basic_by_type" not in ctx


@pytest.mark.req("REQ-DMGCTX-0001")
def test_every_directional_key_reads_the_side_it_is_named_for():
    atk = _facts(hand_size=7, active_energy=3, bench_count=4, prizes_taken=2, active_counters=5,
                 bench_stage2=1, counters_in_play=99, ex_in_play=99)
    dfn = _facts(hand_size=1, active_energy=2, bench_count=0, prizes_taken=5, active_counters=6,
                 bench_stage2=99, counters_in_play=8, ex_in_play=3)
    ctx = damage_context(atk, dfn)
    assert (ctx["atk_hand"], ctx["def_hand"]) == (7, 1)
    assert (ctx["atk_active_energy"], ctx["def_active_energy"]) == (3, 2)
    assert (ctx["atk_bench"], ctx["def_bench"]) == (4, 0)
    assert (ctx["atk_prizes_taken"], ctx["def_prizes_taken"]) == (2, 5)
    assert (ctx["atk_self_counters"], ctx["def_counters"]) == (5, 6)
    # the two FILTERED counts are single-direction by construction (`src/common/CONTEXT.md`):
    # "Stage 2 on YOUR Bench" is attacker-side, "{ex} in play" / "counters on ALL of your
    # opponent's" are defender-side — so neither side's mirror exists to be read.
    assert ctx["atk_bench_stage2"] == 1
    assert (ctx["def_counters_all"], ctx["def_ex_in_play"]) == (8, 3)


@pytest.mark.req("REQ-DMGCTX-0001")
def test_the_both_class_is_direction_symmetric():
    """ADR-0083 §4 / Issue #213: a `both_` variable is the SUM of its two halves, so ONE key is
    correct whichever side attacks — swapping the arguments must not move it."""
    a, b = _facts(bench_count=3, active_energy=2), _facts(bench_count=5, active_energy=1)
    fwd, rev = damage_context(a, b), damage_context(b, a)
    assert fwd["both_bench"] == rev["both_bench"] == 8
    assert fwd["both_active_energy"] == rev["both_active_energy"] == 3
    assert fwd["atk_bench"] != rev["atk_bench"]      # ... while the per-side halves DO swap


@pytest.mark.req("REQ-DMGCTX-0001")
def test_the_attackers_private_zones_never_mirror():
    """The discard, the bench-partner names, the live boosts and the deck facts are read for the
    ATTACKER only — they price the attacker's own scalers, and there is no `def_` counterpart in the
    vocabulary to hold a mirror."""
    atk = _facts(discard_energy_total=4, discard_basic_by_type={3: 2},
                 bench_names=("Lunatone",), damage_boosts=((30, None, False),))
    dfn = _facts(discard_energy_total=9, discard_basic_by_type={1: 9},
                 bench_names=("Solrock",), damage_boosts=((10, 6, True),))
    ctx = damage_context(atk, dfn)
    assert ctx["atk_discard_energy_total"] == 4
    assert ctx["atk_discard_basic_by_type"] == {3: 2}
    assert ctx["atk_bench_names"] == ("Lunatone",)
    assert ctx["atk_boosts"] == ((30, None, False),)
    assert not [k for k in ctx if k.startswith("def_discard") or k.startswith("def_boost")
                or k.startswith("def_bench_names")]


@pytest.mark.req("REQ-DMGCTX-0001")
def test_the_deck_leg_appears_only_when_the_prizes_are_anchored():
    """The hidden deck-discard scaler's fuel (Hammer-lanche class) is EXACT only once the deck
    tracker has resolved the prizes. Unanchored, the pair is absent and the oracle falls back to its
    own bound — a present-but-zero pair would be a positive claim the board cannot support."""
    assert "atk_deck_count" not in damage_context(_facts(deck_count=None), _facts())
    ctx = damage_context(_facts(deck_count=31, deck_basic_by_type={3: 5}), _facts())
    assert ctx["atk_deck_count"] == 31 and ctx["atk_deck_basic_by_type"] == {3: 5}
    # the defender's deck is never read — only the ATTACKER's fuels its own attack
    assert "atk_deck_count" not in damage_context(_facts(), _facts(deck_count=31))


@pytest.mark.req("REQ-DMGCTX-0001")
def test_the_key_set_is_exactly_the_shipped_vocabulary():
    """The closed vocabulary, pinned. Every name here is either a `scaleVar` the parser can emit
    (`scouting/card_text.py`), an override-only `scaleVar` (`attack_overrides.json`), or one of the
    non-scaler riders the oracle reads off the same dict (`atk_bench_names` for a bench-partner
    condition, `atk_boosts` for a flat Trainer/Tool boost, the `atk_deck_*` pair for a hidden deck
    scaler). A key added without a consumer is dead weight; one removed is a silent 0.

    `hidden_units` is deliberately ABSENT though the oracle reads it (`strategy/damage.py`): it is a
    caller's direct OVERRIDE of the hidden-scaler count, which this builder answers instead with the
    deck facts the oracle turns into a pigeonhole floor / hypergeometric mean. Emitting both would
    be two answers to one question, and the override wins — so the builder must not offer one."""
    assert set(damage_context(_facts(), _facts())) == {
        "atk_hand", "def_hand",
        "atk_active_energy", "def_active_energy", "both_active_energy",
        "atk_bench", "def_bench", "both_bench",
        "atk_discard_energy_total", "atk_discard_basic_by_type",
        "atk_bench_names", "atk_boosts",
        "atk_self_counters", "def_counters", "def_counters_all",
        "atk_prizes_taken", "def_prizes_taken",
        "atk_bench_stage2", "def_ex_in_play",
    }


# ── the model accessor ────────────────────────────────────────────────────────────────────────────

WATER_E, RIOLU = 1000, 2000


def _stats():
    from common.scouting.provider import CardStat, DictCardStatProvider
    return DictCardStatProvider({
        WATER_E: CardStat(WATER_E, name="Basic Water Energy", cardType=5, energyType=3),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70),
    })


@pytest.fixture
def combat():
    from common.strategy.combat import CombatMath
    return CombatMath(_stats(), None)


def _asymmetric_obs():
    """A board asymmetric in every direction-sensitive variable, so a mirrored read is visible."""
    from pilot_helpers import poke, state
    return {"current": state(
        active=poke(RIOLU, energy=2, hp=50, max_hp=70, energy_card=WATER_E),
        bench=[poke(RIOLU, hp=70, max_hp=70)],
        hand=[RIOLU, RIOLU, RIOLU], discard=[WATER_E, WATER_E], prizes=4,
        opp_active=poke(RIOLU, energy=1, hp=70, max_hp=70, energy_card=WATER_E),
        opp_bench=[poke(RIOLU, hp=60, max_hp=70), poke(RIOLU, hp=70, max_hp=70)],
        opp_discard=[WATER_E], opp_prizes=6, opp_hand_count=8)}


@pytest.mark.req("REQ-DMGCTX-0002")
def test_the_context_is_the_same_object_on_every_read(combat):
    """The property the whole design rests on. Every downstream clock memo carries the context in
    its key (`incoming`, `turns_to_ko_me` both take `self._key(context)`), and `_Lazily._key` caches
    its canonical projection per OBJECT — so a stable dict is projected once and then hits a plain
    dict lookup, while a freshly-allocated one re-walks the whole context on every read."""
    model = StateModel.build(_asymmetric_obs(), combat=combat)
    assert model.damage_context(attacker="mine") is model.damage_context(attacker="mine")
    assert model.damage_context(attacker="theirs") is model.damage_context(attacker="theirs")
    assert model.damage_context(attacker="mine") is not model.damage_context(attacker="theirs")


@pytest.mark.req("REQ-DMGCTX-0002")
def test_the_two_directions_are_different_dicts_and_agree_only_on_the_both_class(combat):
    model = StateModel.build(_asymmetric_obs(), combat=combat)
    mine = model.damage_context(attacker="mine")
    theirs = model.damage_context(attacker="theirs")
    # my hand is 3 cards, theirs is 8 — so `atk_hand` swaps with the direction, and each
    # direction's `def_hand` is the other side's number.
    assert (mine["atk_hand"], mine["def_hand"]) == (3, 8)
    assert (theirs["atk_hand"], theirs["def_hand"]) == (8, 3)
    assert (mine["atk_bench"], mine["def_bench"]) == (1, 2)
    assert (theirs["atk_bench"], theirs["def_bench"]) == (2, 1)
    assert mine["both_bench"] == theirs["both_bench"] == 3
    assert mine["both_active_energy"] == theirs["both_active_energy"] == 3


@pytest.mark.req("REQ-DMGCTX-0002")
def test_each_side_reads_its_own_zones(combat):
    model = StateModel.build(_asymmetric_obs(), combat=combat)
    mine = model.damage_context(attacker="mine")
    theirs = model.damage_context(attacker="theirs")
    # discard: mine holds 2 Water, theirs 1 — and only the ATTACKER's is read
    assert mine["atk_discard_energy_total"] == 2 and mine["atk_discard_basic_by_type"] == {3: 2}
    assert theirs["atk_discard_energy_total"] == 1 and theirs["atk_discard_basic_by_type"] == {3: 1}
    # damage counters: my Active is at 50/70 (2 counters), theirs at 70/70 (0); their bench carries
    # one body at 60/70, which is what makes `def_counters_all` different from `def_counters`.
    assert (mine["atk_self_counters"], mine["def_counters"]) == (2, 0)
    assert mine["def_counters_all"] == 1
    assert (theirs["atk_self_counters"], theirs["def_counters"]) == (0, 2)
    assert theirs["def_counters_all"] == 2
    # prizes taken = 6 - remaining; I have 4 left (2 taken), they have 6 (none taken)
    assert (mine["atk_prizes_taken"], mine["def_prizes_taken"]) == (2, 0)
    assert (theirs["atk_prizes_taken"], theirs["def_prizes_taken"]) == (0, 2)


@pytest.mark.req("REQ-DMGCTX-0002")
def test_an_absent_prize_zone_claims_nothing_rather_than_six_taken(combat):
    """Fail-closed, and the reason `prizes_taken` is not `6 - prizes_remaining`: a hand-built board
    that carries no `prize` list has an EMPTY remaining count, which that subtraction would read as
    "all six taken" — a maximal positive claim from an absent zone."""
    obs = {"current": {"yourIndex": 0, "players": [{"active": []}, {"active": []}]}}
    ctx = StateModel.build(obs, combat=combat).damage_context(attacker="mine")
    assert ctx["atk_prizes_taken"] == 0 and ctx["def_prizes_taken"] == 0


@pytest.mark.req("REQ-DMGCTX-0002")
def test_an_unknown_direction_is_rejected(combat):
    """The Formula has exactly two directions. A typo must be an error, never a silently-mine dict:
    a survival read handed MY attacker's scalers under-reads their damage, which is the one
    direction a survival estimate may never fail in."""
    model = StateModel.build(_asymmetric_obs(), combat=combat)
    with pytest.raises(ValueError):
        model.damage_context(attacker="opponent")


@pytest.mark.req("REQ-DMGCTX-0002")
def test_two_clock_reads_at_one_direction_share_one_memo_entry(combat):
    """Memo soundness, the point of identity stability — asserted through the model's own probe.

    `turns_to_ko_me` puts the context in its memo key. Called twice with the SAME direction's
    context the second call must be a memo HIT, which the probe shows as a single recorded access
    per read and an unchanged memo size."""
    probe: set = set()
    model = StateModel.build(_asymmetric_obs(), combat=combat, probe=probe)
    ctx = model.damage_context(attacker="theirs")
    body = model.mine.active.body
    before = len(model.theirs._memo)
    first = model.theirs.turns_to_ko_me(body, context=ctx)
    grew = len(model.theirs._memo) - before
    second = model.theirs.turns_to_ko_me(body, context=model.damage_context(attacker="theirs"))
    assert first == second
    assert len(model.theirs._memo) - before == grew, "the second read allocated a second memo entry"
    assert "model.damage_context" in probe


# ── parity with the Pilot ─────────────────────────────────────────────────────────────────────────

def _frames(n=12):
    """``(name, obs)`` for the first ``n`` committed correction fixtures (all of them for None)."""
    files = sorted((REPO / "tests" / "fixtures" / "corrections").glob("*.json"))
    return [(f.name, json.loads(f.read_text(encoding="utf-8"))["obs"])
            for f in (files if n is None else files[:n])]


@pytest.fixture(scope="module")
def live_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


@pytest.mark.req("REQ-DMGCTX-0003")
def test_the_model_context_equals_the_pilots_key_for_key(live_pilot):
    """**The guard that keeps the extraction honest** (Issue #279).

    Runs the production path — the Pilot's own `_turn_boosts.observe` + `_board`, which is what a
    live decision does — then asserts the model's accessor answers exactly what the Pilot's builder
    answers, in BOTH directions, on real corpus frames. A key present on one side and not the other
    is a silent 0 in whichever consumer reads the thinner dict.
    """
    checked = 0
    for name, obs in _frames():
        live_pilot._turn_boosts.observe(obs)
        live_pilot._board(obs, obs.get("select"), carried=live_pilot.carried())
        model = live_pilot._state_model
        assert model.damage_context(attacker="theirs") == live_pilot._opp_attack_context, name
        assert model.damage_context(attacker="mine") == live_pilot._damage_context(obs), name
        checked += 1
    assert checked >= 10, "the parity corpus went missing"


@pytest.mark.req("REQ-DMGCTX-0003")
def test_the_pilots_my_direction_is_built_once_per_decision(live_pilot):
    """`_opp_attack_context` has been cached per decision since ADR-0032 P1; MY direction now is
    too. The three per-option consumers (`_tactical`, the bench-partner enabler, the boost-lethal
    tactical) each used to rebuild it, so an attack-heavy menu paid for the same dict N times — and
    N fresh dicts also cannot hit the clock memos the previous one filled."""
    seen = []
    for _name, obs in _frames(4):
        live_pilot._turn_boosts.observe(obs)
        live_pilot._board(obs, obs.get("select"), carried=live_pilot.carried())
        first = live_pilot._my_damage_context(obs)
        assert live_pilot._my_damage_context(obs) is first, "rebuilt within one decision"
        assert first == live_pilot._damage_context(obs), "the cache drifted from the builder"
        seen.append(first)
    # a DIFFERENT observation must rebuild rather than serve the previous decision's answer
    assert len({id(c) for c in seen}) == len(seen)


@pytest.mark.req("REQ-DMGCTX-0003")
def test_the_pilot_and_the_model_carry_the_same_deck_leg(live_pilot):
    """The one key pair the model cannot derive from its own zones today — `MySide.visible_counts`
    walks `energies`/`energy` while the Pilot's deck tracker walks `energyCards`, and reconciling
    those two moves the Attach Budget, which Issue #279 may not do. So the anchored deck resolution
    is THREADED into the snapshot exactly as `deck` / `own_prizes` / `deck_empty` already are, and
    this pins that the threading actually reaches the context."""
    anchored = 0
    for _name, obs in _frames(None):
        if not obs.get("own_prizes"):
            continue
        live_pilot._turn_boosts.observe(obs)
        live_pilot._board(obs, obs.get("select"), carried=live_pilot.carried())
        mine = live_pilot._state_model.damage_context(attacker="mine")
        if "atk_deck_count" in mine:
            anchored += 1
            assert mine["atk_deck_count"] == live_pilot._damage_context(obs)["atk_deck_count"]
    assert anchored, "no committed frame carries an anchored deck — the deck leg is untested"
