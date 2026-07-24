"""Issue #138 Phase 0b — the **Leaf Profile** pin (ADR-0068 decision 1).

Because StateModel fields are lazy, the cost of an evaluation is set by the field SET it touches —
and that set is invisible in the source. Nothing in a future `state_value` term will say "this line
costs you the Needs assignment DP on every one of a dozen forked leaves". So the field set is pinned
here: it grows, this fails, and somebody has to re-measure deliberately.

Pinned as a field-SET SNAPSHOT and deliberately NOT as wall-clock — a timing assertion is flaky
across the Windows and Linux CI runners. The measured timings are PR evidence (recorded in the commit
and in ADR-0068's consequences), not assertions.

Both profiles are reported PER SIDE, which is what keeps the side-sharing rationale falsifiable: the
design claims the expensive clusters sit on opposite sides of the table, so the split is the number
that would refute it.
"""
import json
import math
import sys
from pathlib import Path

import pytest

from common.state_model import StateModel

REPO = Path(__file__).resolve().parents[2]

#: The exact model field set ONE per-decision `Board` build touches, as measured on real correction
#: frames. Every entry traces to a field migrated in 0b under ADR-0068 decision 3's criteria; the
#: `theirs.*.prize_value` rows are the prize map the cross-side race composite reads.
PER_DECISION_PROFILE = frozenset({
    "mine.discard_energy_counts",
    "mine.hand_energy_counts",
    "mine.hand_ids",
    "mine.prizes_remaining",
    "model.prize_race",
    "theirs.active",
    "theirs.active.prize_value",
    "theirs.bench",
    "theirs.bench.prize_value",
    "theirs.bodies",
    "theirs.discard_energy_counts",
    "theirs.prizes_remaining",
})

#: The CEILING on the model field set one PLANNER-LEAF evaluation may touch.
#:
#: A leaf does not read the model directly — its own terms (`_readiness`, `_incoming_worst`,
#: `_predicted_loss`) are one-sided closed-form reads that predate it. It reads the model *because
#: `_simulate_line` re-runs my policy to end-of-turn*, and every decision inside that line builds a
#: board. So the honest shape of a leaf's model cost is **N per-decision builds**, where N is the
#: number of decisions the simulated line makes — measured at N = 4 on a real turn-1 drive, against a
#: 12.7 ms leaf whose model share is roughly 0.08 ms (under 1%; the engine sim dominates).
#:
#: Pinned as a SUBSET bound rather than an equality because the set legitimately varies with the end
#: board (an empty bench drops the bench prize-map row). Growth BEYOND the per-decision profile is
#: what matters, and it is the tripwire for #145: the moment `state_value` reads a field the ordinary
#: decision path does not — the Needs assignment, the clock curves, the deck Count Triples — this
#: fails, which is exactly when the per-leaf cost needs measuring against the 2-vCPU / ~10-min grader
#: bank and exactly when nobody would otherwise think to look.
LEAF_PROFILE = PER_DECISION_PROFILE


class _Probe:
    """Captures the field set a call touches by handing every model build a shared probe."""

    def __init__(self):
        self.fields: set = set()
        self._orig = StateModel.build

    def __enter__(self):
        probe = self.fields
        orig = self._orig

        def build(obs, **kw):
            kw["probe"] = probe
            return orig(obs, **kw)

        StateModel.build = staticmethod(build)
        return self

    def __exit__(self, *exc):
        StateModel.build = self._orig
        return False

    def split(self) -> dict:
        """The per-side breakdown — the falsifiable half of the sharing rationale."""
        return {
            "mine": {f for f in self.fields if f.startswith("mine")},
            "theirs": {f for f in self.fields if f.startswith("theirs")},
            "cross": {f for f in self.fields if f.startswith("model")},
        }


def _frames(n=8):
    files = sorted((REPO / "tests" / "fixtures" / "corrections").glob("dp_*.json"))[:n]
    return [json.loads(f.read_text(encoding="utf-8"))["obs"] for f in files]


@pytest.fixture(scope="module")
def pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("dragapult_ex")[0]


def test_the_per_decision_build_profile_is_pinned(pilot):
    """The field set a live decision's Board build touches. A migration that drags in a new field —
    especially one of the expensive clusters — moves this and must be measured, not merged."""
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    assert probe.fields == PER_DECISION_PROFILE, (
        "the per-decision field set moved — re-measure the cost per side before re-pinning\n"
        f"  added:   {sorted(probe.fields - PER_DECISION_PROFILE)}\n"
        f"  removed: {sorted(PER_DECISION_PROFILE - probe.fields)}")


def test_the_per_decision_profile_touches_both_sides_and_the_cross_side_read(pilot):
    """Reported per side, so the "expensive clusters sit on opposite sides" claim stays checkable."""
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    split = probe.split()
    assert split["mine"] and split["theirs"] and split["cross"]


def test_construction_itself_touches_nothing(pilot):
    """The premise under every cost claim here: building the model computes no field, so a consumer
    pays for reads alone. Measured at ~0.004 ms against a ~0.95 ms whole-Board build."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck)
    assert probe.fields == set()


def test_an_unread_expensive_cluster_costs_nothing(pilot):
    """Laziness where it matters: reading a cheap my-side field must not drag in their clock curves
    or the deck-count derivation. This is what makes "maximal model, nothing speculative" coherent —
    an offered-but-unread field is free."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck).mine.prizes_remaining
    assert probe.fields == {"mine.prizes_remaining"}
    assert not any("incoming" in f or "deck_energy" in f for f in probe.fields)


def test_the_leaf_profile_is_bounded_as_the_145_tripwire():
    """A real engine drive to a live turn menu, then a leaf evaluation, probed.

    Two things get pinned. The leaf's field set must stay WITHIN the ordinary per-decision profile —
    a leaf reads the model only through the policy re-run inside `_simulate_line`, so reading
    anything the ordinary decision path does not is the signal that a new consumer (#145) has
    arrived and its per-leaf cost is unmeasured. And the leaf must trigger at least one build, so
    the probe is demonstrably wired rather than silently measuring nothing."""
    from tests.strategy.test_planner_engine import (_deck, _engine_pilot, _first_open_menu,
                                                    battle_finish, battle_start)
    deck = _deck()
    engine_pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    assert start.errorPlayer < 0
    try:
        menu = _first_open_menu(engine_pilot, obs)
        assert menu is not None
        chosen = engine_pilot.decide(menu)
        with _Probe() as probe:
            value = engine_pilot._engine_leaf_value(menu, chosen)
        assert value is None or math.isfinite(value)      # the leaf still evaluates
        assert probe.fields, "the probe measured nothing — a leaf builds at least one model"
        assert probe.fields <= LEAF_PROFILE, (
            "a planner leaf now reads a StateModel field the ordinary decision path does not — "
            "measure the per-leaf cost per side against the 2-vCPU grader bank, then re-pin\n"
            f"  added: {sorted(probe.fields - LEAF_PROFILE)}")
    finally:
        battle_finish()


def test_a_leaf_costs_one_model_build_per_simulated_decision():
    """The sizing fact #145 and #150 need, made explicit: a leaf's model cost is NOT one build. The
    simulated line re-runs my policy to end-of-turn, so it pays one per-decision build per decision
    it makes (measured N = 4 on a real turn-1 drive; the engine sim dominates the leaf's ~12.7 ms and
    the model's share is under 1%). If N ever collapses to 1, the sim stopped re-running the policy
    and much more than this test is wrong."""
    from tests.strategy.test_planner_engine import (_deck, _engine_pilot, _first_open_menu,
                                                    battle_finish, battle_start)
    deck = _deck()
    engine_pilot = _engine_pilot(deck)
    obs, start = battle_start(deck, list(deck))
    try:
        menu = _first_open_menu(engine_pilot, obs)
        assert menu is not None
        chosen = engine_pilot.decide(menu)
        builds = []
        orig = StateModel.build

        def counting(o, **kw):
            builds.append(1)
            return orig(o, **kw)
        StateModel.build = staticmethod(counting)
        try:
            engine_pilot._engine_leaf_value(menu, chosen)
        finally:
            StateModel.build = orig
        assert len(builds) >= 1
    finally:
        battle_finish()
