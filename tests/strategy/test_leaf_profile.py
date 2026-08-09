"""Issue #138 Phase 0b — the **Leaf Profile** pin (ADR-0068 decision 1).

StateModel fields are lazy, so an evaluation's cost is set by the field SET it touches and that set
is invisible in the source. Pinned as a field-SET SNAPSHOT, deliberately NOT as wall-clock (flaky
across the CI runners): it grows, this fails, and somebody re-measures deliberately.
"""
import json
import sys
from pathlib import Path

import pytest

from common.state_model import StateModel

REPO = Path(__file__).resolve().parents[2]

#: The field set ONE per-decision `Board` build touches (ADR-0068 decision 3). Re-measure before
#: re-pinning: a per-BODY spelling of a per-BENCH clock cost +36%, and this pin caught it (Issue #261).
PER_DECISION_PROFILE = frozenset({
    "mine.active",
    "mine.active.energy_count",
    "mine.active.energy_key",
    "mine.active.stat",            # the fail-OPEN unreadable-body check the famine read makes first
    "mine.active_famine",
    "mine.attach_budget",
    "mine.attack_blocked",
    "mine.bench",
    "mine.bench_count",
    "mine.bench_full",
    "mine.bodies",
    "mine.body_raws",
    "mine.deck_count",
    "mine.deck_energy_counts",
    "mine.deck_energy_types",
    "mine.deck_energy_types_provable",
    "mine.discard_energy_counts",
    "mine.hand_energy_counts",
    "mine.hand_energy_types",
    "mine.hand_ids",
    "mine.hand_size",
    "mine.hidden_outside_deck",
    "mine.prizes_hidden",
    "mine.prizes_remaining",
    "mine.reachable_attach",
    "mine.unseen_counts",
    "mine.unknown_hand_count",
    "mine.visible_counts",
    "model.prize_race",
    "theirs.active",
    "theirs.active.prize_value",
    "theirs.active.attached_types",   # Deny Relevance
    "theirs.active_raw",              # the harvest clock's opponent-Active argument
    "theirs.bench",
    "theirs.bench.attached_types",
    "theirs.bench.prize_value",
    "theirs.bench_harvest_clock",     # the Prize Path's RIDER route to my Bench
    "theirs.bodies",
    "theirs.body_raws",               # that clock's opponent-board argument
    "theirs.discard_energy_counts",
    "theirs.discard_ids",             # `opp_has_played_gust`
    "theirs.hand_size",
    "theirs.incoming",                # the FOLDED doom read, at the `UNCHARGED` policy
    "theirs.prizes_remaining",
    # ADR-0117 renamed this from `theirs.turns_to_ko_me`; the integer route is that clock's `.turns`
    # view, and `turns_to_ko_me` no longer calls `_memoized`, so there is no second registration.
    "theirs.survival_clock",
    # ADR-0119: `prize_advance` is the LINE's prize, so the rows ask what each opponent body BECOMES.
    # The doubled "their" matches the sibling `their_forward_payoff` memo key.
    "theirs.their_forward_line_prize",
})

#: What the ATTACH DECIDER adds on a menu offering an energy attach (Issue #139, ADR-0069). Nearly
#: empty because the famine read now pays the deck-availability chain on every decision.
ATTACH_DECIDER_PROFILE = frozenset({
    "mine.best_reachable_damage",
})

#: What the PROMOTE/RETREAT DECIDER adds (Issue #141, ADR-0100). It also reads the survival clock's
#: opponent side, which nets out of this subtraction because the per-decision build now reads it too.
PROMOTE_DECIDER_PROFILE = frozenset({
    "mine.bench_raws",
})

#: What the DENY-SLOT keep price adds (ADR-0080 / Issue #187). ⚠️ UNEXERCISED here — no `_DISCARD`
#: select in this corpus — so it is kept in `LEAF_PROFILE` but never asserted as ADDED (Issue #261).
DENY_SLOT_PROFILE = frozenset({
    "theirs.discard_recur_fuel",
    "theirs.turns_to_afford",
})

#: What the `ko_for_prizes` KO lines add beyond the per-decision build and the two deciders. Separate
#: from `PER_DECISION_PROFILE` because that one is pinned with `==` against a bare Board build.
KO_LINE_PROFILE = frozenset({
    # The Probability Leg (ADR-0074 decision 2). A THIRD projection of the same `deck_energy_counts`
    # derivation already pinned above, so it is a dict comprehension, not a second walk over my zones.
    "mine.deck_energy_p",
})

#: What `state_value` adds when the planner leaf scores its end board (POC-T3 / Issue #262). Size a
#: beam against the CORPUS cost (`tools/train/value_lab.py`), never a turn-1 board: `needs` is LAZY.
STATE_VALUE_PROFILE = frozenset({
    # `state_value` memoizes its own per-family dict on the model (Issue #262's incremental-eval
    # line), so the scalar itself appears as a cross-side memo key beside the fields it reads.
    "model.state_value",
    "mine.active.attacks",
    "mine.active.hp_remaining",
    "mine.active.prize_value",
    "mine.bench.attacks",
    "mine.bench.hp_remaining",
    "mine.bench.prize_value",
    "mine.bench.stat",
    "mine.bench_names",
    "mine.forward_index",
    "mine.forward_payoff",
    "mine.mine_turns_to_afford",
    "mine.needs",
    "mine.attack_payoff",
    "mine.readiness_p",
    "mine.role_worth",
    "theirs.active.hp_remaining",
    "theirs.reachable_incoming",
    "theirs.turns_to_ko_me",

    # ADR-0115: the open filtered-count predicate's argument lives on the ATTACK, which the context
    # builder never sees, so `damage_facts` walks raw names on both sides rather than a reduced count.
    "mine.in_play_names",
    "theirs.in_play_names",
    "mine.in_play_attack_names",
    "theirs.in_play_attack_names",

    "mine.best_reachable_damage_vs",
    "model.damage_context",
    # the gatherer, and the per-side countables it walks (`_SideBase.damage_facts`). Both sides,
    # because the Formula's variables are `atk_`/`def_`-relative and one direction needs both.
    "mine.damage_facts",
    "theirs.damage_facts",
    "mine.active.damage_counters",
    "mine.active.is_ex",
    "mine.active.tool_ids",
    "mine.bench.damage_counters",
    "mine.bench.is_ex",
    "mine.bench.is_stage2",
    "mine.damage_boosts",
    "mine.discard_energy_total",
    "mine.discard_ids",
    "mine.prizes_taken",
    # The `theirs.bench.*` half of the SAME gatherer, DECLARED rather than measured: the drive this
    # ceiling is asserted against reaches the leaf with an empty opponent Bench, and `<=` allows it.
    "theirs.bench.damage_counters",
    "theirs.bench.is_ex",
    "theirs.bench.is_stage2",
    "theirs.bench.stat",
    # …and `bench_names`, the fourth thing that same walk reads. DECLARED on the same `<=` ceiling.
    "theirs.bench_names",
    "theirs.active.damage_counters",
    "theirs.active.energy_count",
    "theirs.active.energy_key",
    "theirs.active.is_ex",
    "theirs.active.stat",
    "theirs.active.tool_ids",
    "theirs.bench_count",
    "theirs.damage_boosts",
    "theirs.discard_energy_total",
    "theirs.prizes_taken",

    # Issue #284: `threat` reads their BENCH too. The bench route is the attack's printed snipe RIDER
    # under the same Attach Budget — a rider ignores Weakness/Resistance (ADR-0022), so no scaler.
    "mine.best_reachable_bench_damage",
    "theirs.bench.hp_remaining",
})

LEAF_PROFILE = (PER_DECISION_PROFILE | ATTACH_DECIDER_PROFILE | PROMOTE_DECIDER_PROFILE
                | DENY_SLOT_PROFILE | KO_LINE_PROFILE | STATE_VALUE_PROFILE)


class _Probe:
    """Restores the original class-dict entry (the `classmethod` descriptor), not the bound callable
    attribute access yields — the latter leaves `StateModel.build` globally rebound."""

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
    """THE Corpus Reader (ADR-0087 / ADR-0089): `corpus_records` raises on a missing frame, naming
    it, and dedups — a hand-rolled walk turns both failures into a silent pass."""
    from corpus_helpers import corpus_records
    return [c.obs for c in corpus_records(_ATTACH_FRAMES)]


@pytest.fixture(scope="module")
def pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("dragapult_ex")[0]


def test_the_per_decision_build_profile_is_pinned(pilot):
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    assert probe.fields == PER_DECISION_PROFILE, (
        "the per-decision field set moved — re-measure the cost per side before re-pinning\n"
        f"  added:   {sorted(probe.fields - PER_DECISION_PROFILE)}\n"
        f"  removed: {sorted(PER_DECISION_PROFILE - probe.fields)}")


def test_the_per_decision_profile_touches_both_sides_and_the_cross_side_read(pilot):
    with _Probe() as probe:
        for obs in _frames():
            pilot._board(obs, obs.get("select"), carried=pilot.carried())
    split = probe.split()
    assert split["mine"] and split["theirs"] and split["cross"]


def test_construction_itself_touches_nothing(pilot):
    """The premise under every cost claim here: a consumer pays for reads alone."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck)
    assert probe.fields == set()


def test_the_attach_decider_profile_is_pinned(pilot):
    """Driven at the DECIDERS, not through `explain()`: `plan_turn`'s beam touches dozens of further
    fields no decider reads, so subtracting the per-decision profile would measure the composer."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    ms = _build_pilot("mega_starmie")[0]
    with _Probe() as probe:
        for obs in _attach_frames():
            sel = obs.get("select")
            board = ms._board(obs, sel, carried=ms.carried())
            for option in (sel or {}).get("option") or []:
                ms._attach_decision(obs, sel, board, option)
                ms._promote_retreat_decision(obs, sel, board,
                                             ms._context(obs, sel, board, option), option)
    added = probe.fields - PER_DECISION_PROFILE
    expected = ATTACH_DECIDER_PROFILE | PROMOTE_DECIDER_PROFILE   # not DENY_SLOT — see its comment
    assert added == expected, (
        "the decider field set moved — re-measure before re-pinning\n"
        f"  added:   {sorted(added - expected)}\n"
        f"  removed: {sorted(expected - added)}")
    # The promote/retreat decider's reads net out because it DOES have a term for the clock
    # (ADR-0100 §6); the subtraction is against the union so it keeps biting if that ever reverses.
    attach_only = added - PROMOTE_DECIDER_PROFILE - DENY_SLOT_PROFILE - PER_DECISION_PROFILE
    assert not any("incoming" in f or "needs" in f for f in attach_only), (
        "the attach decider reached an expensive cluster it has no term for")


def test_an_unread_expensive_cluster_costs_nothing(pilot):
    """An offered-but-unread field is free, which is what makes "maximal model, nothing
    speculative" coherent."""
    with _Probe() as probe:
        for obs in _frames():
            StateModel.build(obs, combat=pilot.combat, deck=pilot.deck).mine.prizes_remaining
    assert probe.fields == {"mine.prizes_remaining"}
    assert not any("incoming" in f or "deck_energy" in f for f in probe.fields)

# NB: the ENGINE-DRIVEN halves of this pin live in `test_planner_engine.py`. Everything above is
# engine-free BY DESIGN — a native battle collected ahead of the lethal pins once fired a CI flake.
