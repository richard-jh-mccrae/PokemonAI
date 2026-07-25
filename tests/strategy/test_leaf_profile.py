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

#: The model fields the ATTACH DECIDER adds on any menu that offers an energy attach (#139,
#: ADR-0069), measured on the mega_starmie attach corpus. They are NOT in the per-decision profile
#: above because the sampled `dp_*` frames happen to carry no attach option — the two sets are
#: measurements of different menus, not a discrepancy.
#:
#: The cluster it drags in is the deck-availability chain (`visible_counts` -> `unseen_counts` ->
#: `deck_energy_counts` -> `deck_energy_types`), which the Attach Budget needs to know which colours
#: the deck can still yield (ADR-0067's fail-OPEN presence gate). That is a deliberate, bounded cost:
#: one pass over my zones per decision, memoized for the whole decision, and it is the price of the
#: Budget being typed at all. Everything else here is body-view construction (dict wrapping, no
#: derivation) plus the memoized per-body Budget and reachable-damage reads.
ATTACH_DECIDER_PROFILE = frozenset({
    "mine.active",
    "mine.attach_budget",
    "mine.bench",
    "mine.best_reachable_damage",
    "mine.bodies",
    "mine.body_raws",
    "mine.deck_count",
    "mine.deck_energy_counts",
    "mine.deck_energy_types",
    "mine.hand_energy_types",
    "mine.prizes_hidden",
    "mine.unseen_counts",
    "mine.visible_counts",
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
#: A leaf's simulated line re-runs my policy to end of turn, so it reaches menus WITH attaches and
#: pays the attach decider's reads too — hence the union rather than the per-decision set alone.
LEAF_PROFILE = PER_DECISION_PROFILE | ATTACH_DECIDER_PROFILE


class _Probe:
    """Captures the field set a call touches by handing every model build a shared probe.

    Restores the original **class-dict entry** (the `classmethod` descriptor), not the bound callable
    that attribute access yields — assigning the latter back would leave `StateModel.build` globally
    rebound for every test that runs afterwards, which is test pollution regardless of whether it
    changes an answer.
    """

    def __init__(self):
        self.fields: set = set()

    def __enter__(self):
        self._descriptor = StateModel.__dict__["build"]     # the classmethod itself
        probe, orig = self.fields, StateModel.build         # orig: bound, for delegation

        def build(obs, **kw):
            kw["probe"] = probe
            return orig(obs, **kw)

        StateModel.build = staticmethod(build)
        return self

    def __exit__(self, *exc):
        StateModel.build = self._descriptor                 # exact original semantics restored
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


#: Committed mega_starmie frames whose menu DOES offer an energy attach — the attach decider's
#: profile is meaningless on a menu it stays silent on.
_ATTACH_FRAMES = (("82523811", 59), ("83664340", 45), ("82750161", 59))


def _attach_frames():
    wanted, out = {(e, f) for e, f in _ATTACH_FRAMES}, []
    for jf in sorted((REPO / "data" / "corrections").glob("*/corrections.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if (str(d.get("episode_id")), d.get("decision", {}).get("frame")) in wanted:
                out.append(d["obs"])
    assert len(out) == len(wanted), "an attach profile frame went missing from data/corrections/"
    return out


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


def test_the_attach_decider_profile_is_pinned(pilot):
    """The attach decider's model reads, pinned on a menu that actually offers an energy attach. Same
    tripwire as the per-decision pin: if the decider starts reading the Needs assignment or a clock
    curve, this moves and the per-leaf cost needs re-measuring before it merges."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    ms = _build_pilot("mega_starmie")[0]
    with _Probe() as probe:
        for obs in _attach_frames():
            ms.explain(obs)
    added = probe.fields - PER_DECISION_PROFILE
    assert added == ATTACH_DECIDER_PROFILE, (
        "the attach decider's field set moved — re-measure before re-pinning\n"
        f"  added:   {sorted(added - ATTACH_DECIDER_PROFILE)}\n"
        f"  removed: {sorted(ATTACH_DECIDER_PROFILE - added)}")
    assert not any("incoming" in f or "needs" in f for f in added), (
        "the attach decider reached an expensive cluster it has no term for")


def test_an_unread_expensive_cluster_costs_nothing(pilot):
    """Laziness where it matters: reading a cheap my-side field must not drag in their clock curves
    or the deck-count derivation. This is what makes "maximal model, nothing speculative" coherent —
    an offered-but-unread field is free."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck).mine.prizes_remaining
    assert probe.fields == {"mine.prizes_remaining"}
    assert not any("incoming" in f or "deck_energy" in f for f in probe.fields)

# NB: the two ENGINE-DRIVEN halves of this pin live in `test_planner_engine.py`, not here.
# `test_leaf_profile` collects immediately before `test_lethal_helpers` / `test_lethal_recover`, and
# `ml_lethal_retreat_boost_to_ko_f24` is documented in `planner._develop_rollout_line` as depending on
# "the process's RNG position — the CI heisenbug". Starting a native battle ahead of those pins shifts
# that position and fires the heisenbug (it did, in CI). `test_planner_engine` already drives battles
# AND sorts after the lethal pins, so the engine halves belong there. Everything above is engine-free
# by design — keep it that way.
