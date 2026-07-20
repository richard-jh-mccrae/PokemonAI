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
        WINCON: CardStat(WINCON, name="wincon", hp=200, energyType=3),
        JUNK: CardStat(JUNK, name="junk", hp=60, energyType=3),
    })
    return Pilot(Strategy(roles={WINCON: ["primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}), **kw)


def _trace(index, score):
    return OptionTrace(index=index, score=score, plan=Plan.SETUP, card_id=None, fired=[])


def _stub_leaf(pilot, by_step):
    """Stub ``_engine_leaf_value`` to a fixed value per first-step (bypasses the native engine).
    Mirrors the real signature: ``with_coins=True`` returns ``(value, coins)`` — always coin-free
    here (the coin-exclusion path has its own test, `test_a_coin_dependent_simmed_win_...`)."""
    def leaf(obs, step, spend_account=True, with_coins=False):
        val = by_step.get(tuple(step))
        return (val, False) if with_coins else val
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
