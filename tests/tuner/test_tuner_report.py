"""The per-run tuning report (Markdown) — the human-readable/showcase artifact each tune writes."""
from types import SimpleNamespace

from train.tuner.fit import Constraint
from train.tuner.propose import ProposedHypothesis
from train.tuner.report_md import render_run_report
from train.tuner.run import TuneResult


def _corr(**kw):
    base = dict(episode_id=1, decision={"frame": 5}, category="misattachment",
                chosen_label="Attach Ignition → Cinderace", correct_label="Attach Basic {W} → Cinderace",
                rationale="never attach ignition to cinderace when basic available", agent_build="b")
    base.update(kw)
    return SimpleNamespace(**base)


def _proposal():
    return ProposedHypothesis(id="missed-win-1", rationale="evolve to the wincon", seed_weight=20.0,
                              trigger_sketch="prefer 'Evolve' over 'Attack'", category="missed_win",
                              episode_id=2, frame=7)


def test_report_explains_an_adopted_weight_change_with_driver_and_magnitude():
    """REQ-TUNER-0014: an adopted weight change is shown with seed→new, the signed delta, the band,
    and at least one driving correction's rationale (the 'why')."""
    corr = _corr()
    result = TuneResult(overrides={"accel-into-main": 1.97}, proposals=[_proposal()], skipped=[],
                        n_constraints=2, unsatisfied=[_corr(episode_id=9)], base_satisfied=1,
                        fit_adopted=True, w_items=[(corr, Constraint(deltas={"accel-into-main": -1}, tactical_delta=0))])
    md = render_run_report("mega_starmie", result, seeds={"accel-into-main": 30}, changed={"accel-into-main": 1.97},
                           reg=0.15, when_iso="2026-01-01T00:00:00", build="mega_starmie_x", n_corrections=3)

    assert "fit **adopted**" in md
    assert "`accel-into-main`: 30 → 1.97" in md and "-28.03" in md      # by how much
    assert "never attach ignition to cinderace" in md                  # the why (driver rationale)
    assert "missed_win" in md and "→" in md                            # proposal + unsatisfied move
    assert "methodology.md" in md                                       # links math explainer


def test_report_explains_when_seeds_are_kept():
    """REQ-TUNER-0014: when the fit ships nothing, the report says why (didn't beat the seeds) and
    points the leverage at the proposals/unsatisfied list — not a silent empty section."""
    result = TuneResult(overrides={}, proposals=[_proposal()], skipped=[], n_constraints=3,
                        unsatisfied=[_corr()], base_satisfied=3, fit_adopted=False, w_items=[])
    md = render_run_report("mega_starmie", result, seeds={}, changed={}, reg=0.25,
                           when_iso="2026-01-01T00:00:00", build=None, n_corrections=5)

    assert "kept" in md and "strictly more" in md
    assert "## Weights tuned" in md and "_None._" in md
    assert "need a rule, not a weight" in md


def test_run_report_locates_a_scoped_proposal_by_its_subject():
    """ADR-0049: `ep <id> f<frame>` is the wrong locator for a Turn/Match blunder — the Anchor frame
    is context, not identity. The report must name the scope's subject so a reader can find it."""
    from train.blunder.correction import build_correction
    from train.blunder.decisions import Decision
    from train.tuner.propose import propose_hypothesis
    from train.tuner.report_md import _where

    dec = Decision(episode_id=42, frame=28, seat=1, turn=12, select_context="Main",
                   select_type="Main", options=[{"type": 7}, {"type": 13}], chosen=[0], current={})
    turn = build_correction(dec, source="own", agent="a", correct=[], category="sequencing_error",
                            rationale="r", scope="turn", span=[{"chosen_label": "x"}])
    match = build_correction(dec, source="own", agent="a", correct=[], category="slow_setup",
                             rationale="r", scope="match", span=[])
    decision = build_correction(dec, source="own", agent="a", correct=[1], category="bad_target",
                                rationale="r")

    assert _where(propose_hypothesis(turn)) == "ep 42 turn 12 (seat 1)"
    assert _where(propose_hypothesis(match)) == "ep 42 whole match (seat 1)"
    assert _where(propose_hypothesis(decision)) == "ep 42 f28"
