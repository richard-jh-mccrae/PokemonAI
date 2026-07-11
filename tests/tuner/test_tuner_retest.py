"""Retest: diff how the agent would decide now vs the embedded live trace (ADR-0019)."""
import json
import sys
from pathlib import Path

from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy
from pilot_helpers import BENCH, DAMAGE, HAND, MAIN, card_opt, make_select, poke, state

from train.blunder.correction import build_correction
from train.blunder.decisions import Decision
from train.tuner.retest import retest, retest_span


def _correction(obs, *, correct, live_trace):
    d = Decision(episode_id="t", frame=0, seat=0, turn=2, select_context="Main",
                 select_type="Main", options=obs["select"]["option"], chosen=[0],
                 current=obs["current"], obs=obs)
    return build_correction(d, source="own", agent="x", correct=correct,
                            category="bad_target", rationale="r", live_trace=live_trace)


def test_retest_reports_fixed_only_when_correct_now_wins():
    """REQ-TUNER-0014: retest re-derives the decision in live-telemetry format and flags `fixed`
    once the correct option is chosen; `before` comes from the embedded live trace."""
    boost = Hypothesis("boost", "", when=lambda c: c.card_id == 222, weight=0)  # off by default
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=MAIN,
                      current=state(hand=[111, 222]))
    corr = _correction(obs, correct=[1], live_trace={"chosen": [0], "margin": 0})

    base = retest(corr, Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60))
    assert base["chosen_after"] == [0] and base["fixed"] is False     # blunder still occurs
    assert base["chosen_before"] == [0]                                # from live trace

    tuned = retest(corr, Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60, overrides={"boost": 50.0}))
    assert tuned["chosen_after"] == [1] and tuned["fixed"] is True     # fix makes correct win
    assert tuned["after"]["opts"][1]["fired"] == [["boost", 50.0]]     # live-format trace


def test_retest_surfaces_layer_verdicts():
    """REQ-TUNER-0015: the summary lifts the lethal/planned layer verdicts (ADR-0030/0031) out of
    the before/after records — a solver/planner fix's proof is one glance, no trace digging."""
    obs = make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=MAIN,
                      current=state(hand=[111, 222]))
    planned = {"step": [1], "goal": "ko_for_prizes", "why": "retreat->attach->KO"}
    corr = _correction(obs, correct=[1],
                       live_trace={"chosen": [0], "margin": 0, "lethal": None, "planned": planned})

    r = retest(corr, Pilot(Strategy(hypotheses=[]), deck=[1] * 60))
    assert r["planned_before"] == planned and r["lethal_before"] is None
    assert r["planned_after"] is None and r["lethal_after"] is None    # plain pilot commits nothing

    legacy = retest(_correction(obs, correct=[1], live_trace={"chosen": [0], "margin": 0}),
                    Pilot(Strategy(hypotheses=[]), deck=[1] * 60))
    assert legacy["planned_before"] is None                            # pre-planner trace degrades


def test_retest_treats_indistinguishable_duplicate_species_as_fixed():
    """Duplicate-species reconciliation: two byte-identical bench bodies (the f75 shape) are
    interchangeable snipe targets, so picking either satisfies the doctrine — the strict-index bar
    wrongly re-flagged the equally-valid twin the engine deterministically lands on."""
    twin = lambda: poke(677, energy=0, hp=80, max_hp=80)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE, current=state(opp_bench=[twin(), twin()]))
    corr = _correction(obs, correct=[1], live_trace={"chosen": [0], "margin": 0})

    r = retest(corr, Pilot(Strategy(hypotheses=[]), deck=[1] * 60))
    assert r["chosen_after"] == [0]        # bare pilot breaks the tie to the first option
    assert r["fixed"] is True              # ...but [0] is the identical twin of correct [1]


def test_retest_does_not_treat_an_energized_copy_as_interchangeable():
    """The guard is state-exact: two copies of one card that differ in ATTACHED ENERGY are NOT
    interchangeable, so a real positional miss (wanted the energized copy) still reports unfixed."""
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)],
                      context=DAMAGE,
                      current=state(opp_bench=[poke(677, energy=0, hp=80, max_hp=80),
                                              poke(677, energy=2, hp=80, max_hp=80)]))
    corr = _correction(obs, correct=[1], live_trace={"chosen": [0], "margin": 0})

    r = retest(corr, Pilot(Strategy(hypotheses=[]), deck=[1] * 60))
    assert r["chosen_after"] == [0]        # picked the bare copy
    assert r["fixed"] is False             # correct [1] is energized — different body, not a twin


def test_retest_reconciles_the_reopened_f75_duplicate_riolu_snipe():
    """The reopened f75 case end-to-end: the shipped mega_starmie Pilot snipes a Riolu, but an
    identical twin, so its slot differs from correct=[3]. Body reconciliation reports it FIXED,
    mirroring tests/strategy/test_snipe_the_real_attacker.py's by_card_id assertion."""
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo / "tools"))
    from train.tune import _build_pilot
    fx = json.loads((repo / "tests" / "fixtures" / "corrections" /
                     "ms_snipe_evolving_wincon_preevo_f75.json").read_text(encoding="utf-8"))
    corr = _correction(fx["obs"], correct=fx["correct"],
                       live_trace={"chosen": fx["chosen"], "margin": 0})

    r = retest(corr, _build_pilot("mega_starmie")[0])
    assert r["fixed"] is True              # picks an (equally-valid) Riolu — reconciled by body


def _turn_correction(*, correct, span):
    """A Turn Correction whose Span carries per-Decision `obs` — the shape retest_span re-drives."""
    d = Decision(episode_id="t", frame=0, seat=0, turn=4, select_context="Main",
                 select_type="Main", options=span[0]["obs"]["select"]["option"], chosen=[0],
                 current=span[0]["obs"]["current"], obs=span[0]["obs"])
    return build_correction(d, source="own", agent="x", correct=correct,
                            category="sequencing_error", rationale="develop first",
                            scope="turn", span=span)


def _span_obs():
    return make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=MAIN,
                       current=state(hand=[111, 222]))


def _span():
    return [{"frame": 0, "chosen": [0], "chosen_label": "Play A", "obs": _span_obs()},
            {"frame": 1, "chosen": [0], "chosen_label": "Play B", "obs": _span_obs()}]


def _pilot(boost_weight=None):
    boost = Hypothesis("boost", "", when=lambda c: c.card_id == 222, weight=0)
    overrides = {"boost": boost_weight} if boost_weight is not None else None
    return Pilot(Strategy(hypotheses=[boost]), deck=[1] * 60, overrides=overrides)


def test_retest_fixed_is_unknown_when_the_correction_names_no_correct_option():
    """ADR-0049: a prose-only scoped Correction asserts nothing to check. `all([])` is True, so the
    old expression would have reported every one of them vacuously FIXED — it must be None."""
    prose = _turn_correction(correct=[], span=_span())
    assert retest(prose, _pilot())["fixed"] is None

    prescribed = _turn_correction(correct=[1], span=_span())     # Anchor prescription -> assertable
    assert retest(prescribed, _pilot())["fixed"] is False
    assert retest(prescribed, _pilot(boost_weight=50.0))["fixed"] is True


def test_retest_span_re_drives_the_turn_and_stops_at_the_first_divergence():
    """ADR-0049: the Span is re-driven Decision by Decision. Once the candidate Pilot diverges, every
    later `obs` was produced by the OLD line — off-policy — so its verdict is meaningless and is
    never computed. An agreeing Pilot walks the whole turn with no divergence."""
    corr = _turn_correction(correct=[1], span=_span())

    agrees = retest_span(corr, _pilot())
    assert agrees["first_divergence"] is None
    assert [s["chosen_after"] for s in agrees["steps"]] == [[0], [0]]
    assert not any(s["off_policy"] for s in agrees["steps"])

    diverges = retest_span(corr, _pilot(boost_weight=50.0))
    assert diverges["first_divergence"] == {"frame": 0, "chosen_before": [0], "chosen_after": [1]}
    assert diverges["steps"][0]["diverged"] is True
    assert diverges["steps"][1] == {"frame": 1, "chosen_before": [0], "chosen_after": None,
                                    "diverged": False, "off_policy": True}


def test_retest_span_of_a_match_correction_is_empty_because_it_carries_no_obs():
    """A Match Correction is doctrine (`seed-ladder`), not a re-drivable line: its per-Turn headers
    hold no `obs`, so there is nothing to re-drive and the walker says so rather than guessing."""
    d = Decision(episode_id="t", frame=0, seat=0, turn=4, select_context="Main",
                 select_type="Main", options=_span_obs()["select"]["option"], chosen=[0],
                 current={}, obs=_span_obs())
    match = build_correction(d, source="own", agent="x", correct=[], category="slow_setup",
                             rationale="never set up", scope="match",
                             span=[{"turn": 1, "seat": 0, "chosen_labels": ["Play A"]}])
    walked = retest_span(match, _pilot())
    assert walked["steps"] == [] and walked["first_divergence"] is None
    assert walked["scope"] == "match" and walked["span_len"] == 1
