"""The develop-rollout rung (develop-rung Phase 1, ``docs/plans/turn-planner-develop-rung.md``).

The Turn Planner only committed KO-reaching lines; on a setup/develop turn ``plan_turn`` returned
None and the Pilot fell to greedy per-frame scoring. The develop rung is the deferred bottom rung: it
rolls out each candidate first action to its end-of-MY-turn board (``_engine_leaf_value``), and
commits the one whose leaf ranks highest — the within-turn rollout that needs no opponent model.

These tracers pin the rung's RANKING logic with the leaf stubbed (the engine sim is exercised
separately, `test_planner_engine.py`): given per-candidate leaf values, the rung must commit the
argmax as a ``goal="develop"`` line and stash the full ranking (sorted desc, committed + greedy
flagged) for telemetry.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import OptionTrace, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Plan, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

WINCON = 900
JUNK = 800


def _pilot(**kw):
    stats = DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="wincon", hp=200, energyType=3),
        JUNK: CardStat(JUNK, synthetic=True, name="junk", hp=60, energyType=3),
    })
    return Pilot(Strategy(roles={WINCON: ["primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}), **kw)


def _trace(index, score):
    return OptionTrace(index=index, score=score, plan=Plan.SETUP, card_id=None, fired=[])


def _stub_leaf(pilot, by_step):
    """Stub ``_engine_leaf_value`` to a fixed value per first-step (bypasses the native engine).
    Mirrors the real signature: ``with_stream=True`` returns ``(value, stream)`` — always RNG-free
    here (the stream-exclusion path has its own tests in `test_planner.py`)."""
    def leaf(obs, step, spend_account=True, with_stream=False):
        val = by_step.get(tuple(step))
        return (val, False) if with_stream else val
    pilot._engine_leaf_value = leaf


@pytest.mark.req("REQ-PLANNER-0012")
def test_rung_commits_the_highest_leaf_candidate_as_a_develop_line():
    """Three develop candidates; greedy (top score) is option 0, but the rollout values option 2
    highest. The rung commits option 2 as a develop line carrying its leaf value, and marks it
    diverged (it overrode greedy's pick)."""
    p = _pilot()
    options = [{"type": 0}, {"type": 0}, {"type": 0}]
    traces = [_trace(0, 5.0), _trace(1, 4.0), _trace(2, 3.0)]     # greedy argmax = option 0
    _stub_leaf(p, {(0,): 30.0, (1,): 40.0, (2,): 55.0})          # rollout ranks option 2 top
    line = p._develop_rollout_line({}, None, None, options, traces)
    assert line is not None
    assert line.goal == "develop"
    assert line.next_step == [2]
    assert line.value == 55.0
    assert line.ranked_by == "engine"
    assert line.diverged is True                                 # 2 != greedy 0


@pytest.mark.req("REQ-PLANNER-0012")
def test_rung_stashes_the_ranked_candidates_sorted_with_flags():
    """The rung keeps the ranking it already computed: top-K end-boards sorted by value desc, the
    committed pick flagged, and greedy's pick flagged (with its own rollout value) so an override is
    measurable."""
    p = _pilot()
    options = [{"type": 0}, {"type": 0}, {"type": 0}]
    traces = [_trace(0, 5.0), _trace(1, 4.0), _trace(2, 3.0)]
    _stub_leaf(p, {(0,): 30.0, (1,): 40.0, (2,): 55.0})
    p._develop_rollout_line({}, None, None, options, traces)
    cand = p._develop_candidates_pending
    assert [c["value"] for c in cand] == [55.0, 40.0, 30.0]       # sorted desc
    assert next(c for c in cand if c.get("committed"))["step"] == [2]
    assert next(c for c in cand if c.get("greedy"))["step"] == [0]


@pytest.mark.req("REQ-PLANNER-0012")
def test_rung_defers_when_no_candidate_can_be_simmed():
    """Every rollout returns None (sim unavailable) — the rung has nothing to rank, so it defers to
    the tuned scoring (returns None) rather than committing a blind pick."""
    p = _pilot()
    options = [{"type": 0}, {"type": 0}]
    traces = [_trace(0, 5.0), _trace(1, 4.0)]
    _stub_leaf(p, {})                                            # all sims None
    assert p._develop_rollout_line({}, None, None, options, traces) is None


@pytest.mark.req("REQ-PLANNER-0012")
def test_gate_fires_only_when_greedy_is_weak_or_indifferent():
    """Augment-not-override: the rung fires only where greedy has no confident pick — the top score
    is weak, OR the top two are near-tied. A decisive greedy pick (high, well-separated top score)
    keeps the turn, so the tuned rules stay in charge where they already decide."""
    p = _pilot()
    assert p._develop_should_fire([_trace(0, 10.0), _trace(1, 8.0)]) is True    # weak: top score low
    assert p._develop_should_fire([_trace(0, 50.0), _trace(1, 48.0)]) is True   # indifferent: near-tied
    assert p._develop_should_fire([_trace(0, 50.0), _trace(1, 5.0)]) is False   # decisive: strong + clear


@pytest.mark.req("REQ-PLANNER-0012")
def test_rung_defers_on_a_win_class_rollout_value():
    """Soundness guard: the develop rollout is HEURISTIC (auto coins, predicted opponent zones), so a
    KO_SCORE-class leaf is an UNVERIFIED 'win'. Sound wins are the win rung's job — it runs first and
    already declined — so the develop rung must never commit on a phantom rollout-win. It defers,
    leaving such a board to the tuned scoring / the sound solver (ml f24: a rollout 'win' was overriding
    the human's real lethal-enabling attach)."""
    from common.strategy.planner import KO_SCORE
    p = _pilot()
    options = [{"type": 0}, {"type": 0}]
    traces = [_trace(0, 5.0), _trace(1, 4.0)]
    _stub_leaf(p, {(0,): KO_SCORE * 3, (1,): 40.0})             # option 0 sims to a 'win' (unsound)
    assert p._develop_rollout_line({}, None, None, options, traces) is None
    assert p._develop_candidates_pending is None


@pytest.mark.req("REQ-PLANNER-0012")
def test_rung_captures_every_rolled_out_candidate_for_the_corpus():
    """Phase-3 corpus harvest (armed-ON): the rung must emit the leaf value for EVERY rolled-out option,
    so the human's later `correct` pick is always in the trace with its value — even when it's neither
    the committed nor the greedy pick. A realistic menu (here 5 options) is captured in full."""
    p = _pilot()
    options = [{"type": 0}] * 5
    traces = [_trace(i, 5.0 - i) for i in range(5)]              # greedy = option 0
    _stub_leaf(p, {(0,): 30.0, (1,): 40.0, (2,): 55.0, (3,): 45.0, (4,): 35.0})
    p._develop_rollout_line({}, None, None, options, traces)
    steps = {tuple(c["step"]) for c in p._develop_candidates_pending}
    assert steps == {(0,), (1,), (2,), (3,), (4,)}              # all five leaf values captured


# ── Option Equivalence Class canonicalisation (ADR-0091 decisions 5+8, Issue #247) ───────────

def _twin_frame(bodies):
    """A board whose option i picks bench body i — the shape that produced the measured asymmetry."""
    return {"current": {"yourIndex": 0, "looking": None,
                        "players": [{"active": [], "bench": list(bodies), "hand": [], "discard": []},
                                    {"active": [], "bench": [], "hand": [], "discard": []}]}}


def _riolu(serial, *, hp=70):
    return {"appearThisTurn": False, "energies": [], "energyCards": [], "hp": hp, "id": 1030,
            "maxHp": 70, "playerIndex": 0, "preEvolution": [], "serial": serial, "tools": []}


def _bench_options(n):
    return [{"area": 5, "index": i, "playerIndex": 0, "type": 3} for i in range(n)]


def _counting_leaf(pilot, by_step, *, streams=()):
    """Like `_stub_leaf`, but RECORDS which first-steps were actually simmed — the point of the
    canonicalisation is that identical options are not simmed twice."""
    seen = []

    def leaf(obs, step, spend_account=True, with_stream=False):
        seen.append(tuple(step))
        val = by_step.get(tuple(step))
        stream = tuple(step) in streams
        return (val, stream) if with_stream else val
    pilot._engine_leaf_value = leaf
    return seen


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_rung_sims_ONE_representative_per_equivalence_class():
    """`81903490|0|decision|49`'s shape: three byte-identical Riolu. They are one decision, so the
    rung sims the lowest index and never touches the other two — which is also why the change makes
    the rung cheaper rather than more expensive."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2), _riolu(3)])
    options = _bench_options(3)
    traces = [_trace(0, 5.0), _trace(1, 4.0), _trace(2, 3.0)]
    seen = _counting_leaf(p, {(0,): 100.0})
    line = p._develop_rollout_line(obs, None, None, options, traces)
    assert seen == [(0,)], "three identical bodies are ONE rollout"
    assert line is not None and line.next_step == [0] and line.value == 100.0


@pytest.mark.req("REQ-PLANNER-0012")
def test_every_member_of_a_class_carries_the_class_MAXIMUM():
    """The fix itself. The representative's value is the whole class's — so the rung can no longer
    prefer one of two identical decisions over the other, which is what the measured 1167.0-vs-95.4
    split amounted to.

    Values are held BELOW `KO_SCORE`: a rollout value at or above it is treated as an unsound
    phantom win and defers the rung outright (ml f24), which would mask what this asserts."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2)])
    options = _bench_options(2) + [{"type": 14}]
    traces = [_trace(0, 5.0), _trace(1, 4.0), _trace(2, 3.0)]
    _counting_leaf(p, {(0,): 116.7, (2,): 9.54})
    p._develop_rollout_line(obs, None, None, options, traces)
    cand = p._develop_candidates_pending
    assert sorted(c["value"] for c in cand) == [9.54, 116.7, 116.7]


@pytest.mark.req("REQ-PLANNER-0012")
def test_a_DISTINGUISHABLE_body_is_still_simmed_and_ranked_separately():
    """The negative half — canonicalisation must not swallow genuine differences. A damaged twin is
    a different decision, so it gets its own rollout and its own value."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2, hp=30)])
    options = _bench_options(2)
    traces = [_trace(0, 5.0), _trace(1, 4.0)]
    seen = _counting_leaf(p, {(0,): 100.0, (1,): 20.0})
    line = p._develop_rollout_line(obs, None, None, options, traces)
    assert seen == [(0,), (1,)]
    assert line.next_step == [0] and line.value == 100.0


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_kill_switch_OFF_is_byte_identical_to_the_pre_247_rung():
    """`leaf_option_equivalence=False` must sim every option, exactly as before — the property that
    makes the flag a real one-line rollback rather than a partial one."""
    p = _pilot(leaf_option_equivalence=False)
    obs = _twin_frame([_riolu(1), _riolu(2), _riolu(3)])
    options = _bench_options(3)
    traces = [_trace(0, 5.0), _trace(1, 4.0), _trace(2, 3.0)]
    seen = _counting_leaf(p, {(0,): 116.7, (1,): 9.54, (2,): 9.54})
    line = p._develop_rollout_line(obs, None, None, options, traces)
    assert seen == [(0,), (1,), (2,)]
    assert line.value == 116.7


@pytest.mark.req("REQ-PLANNER-0012")
def test_a_stream_riding_REPRESENTATIVE_still_defers_the_whole_rung():
    """All-or-nothing is unchanged in RULE (#178): an unreproducible value in the ranking means the
    rung hands the turn back to the tuned scoring."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2)])
    options = _bench_options(2)
    traces = [_trace(0, 5.0), _trace(1, 4.0)]
    _counting_leaf(p, {(0,): 100.0}, streams={(0,)})
    assert p._develop_rollout_line(obs, None, None, options, traces) is None


@pytest.mark.req("REQ-PLANNER-0012")
def test_a_stream_riding_NON_representative_no_longer_defers():
    """The narrowing (decision 8), and the reason it is sound: option 1 is never simmed, so its coin
    never enters the ranking. Before, a class surrendered the whole turn whenever one isomorphic
    sibling happened to roll a coin its twin did not — and which sibling rolls is exactly the
    cross-process variance #178 documents. Every value the rung consults is still reproducible."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2)])
    options = _bench_options(2)
    traces = [_trace(0, 5.0), _trace(1, 4.0)]
    seen = _counting_leaf(p, {(0,): 100.0, (1,): 95.0}, streams={(1,)})
    line = p._develop_rollout_line(obs, None, None, options, traces)
    assert seen == [(0,)]
    assert line is not None and line.value == 100.0


@pytest.mark.req("REQ-PLANNER-0012")
def test_the_committed_pick_is_the_LOWEST_index_of_a_winning_class():
    """Determinism across processes: ties break to the class representative, never to whichever
    member the iteration happened to reach first."""
    p = _pilot(leaf_option_equivalence=True)
    obs = _twin_frame([_riolu(1), _riolu(2)])
    options = [{"type": 14}] + _bench_options(2)
    # the option list puts the non-class option FIRST, so the class's members are indices 1 and 2
    traces = [_trace(0, 9.0), _trace(1, 4.0), _trace(2, 3.0)]
    _counting_leaf(p, {(0,): 10.0, (1,): 500.0})
    line = p._develop_rollout_line(obs, None, None, options, traces)
    assert line.next_step == [1]
