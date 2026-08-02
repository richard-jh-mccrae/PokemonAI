"""BASELINE cluster: PHASES — the derived advisory phase's band weights (ADR-0040).

**The ONE file allowed to read ``c.board.phase``** (the gate-ban lint guard whitelists it): a phase
is ADVISORY by contract — a legibility label plus these SMALL band nudges, never an eligibility gate
on other behaviors. A wrong phase read costs a few biased points for a turn, structurally incapable
of silencing a rule family. The phase-ablation A/B (an overlay zeroing these weights +
``objectives_phases`` off) must land within noise, permanently — a phase that moves win-rate has
become load-bearing, which is a design violation, not a tuning target.
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="phase-stabilize-prefer-heal",
        rationale="STABILIZE band (ADR-0040): derived only when clearly behind in the KO Race with a "
                  "doomed Active — nudge heal/recovery plays up a little so the denial turn actually "
                  "denies. A band, not a gate: the existing heal rules carry the real logic; this "
                  "leans the tie their way while the race says survive-first.",
        when=lambda c: c.board.phase == Plan.STABILIZE and c.option_type == _PLAY
        and "heal" in c.tags,
        weight=8, status="testing"),
    Hypothesis(
        id="phase-close-stop-developing",
        rationale="CLOSE band (ADR-0040): payoff online and ≤2 prizes left — long-horizon development "
                  "(benching fresh bodies) stops paying before the match ends, so lean those plays "
                  "down slightly and let the finishing lines win ties. A band, not a gate: "
                  "`Pilot._empty_bench_forced` is a FILTER above every score, so it still "
                  "dominates an empty-bench emergency, and any real KO/lethal is KO_SCORE-class "
                  "regardless.",
        when=lambda c: c.board.phase == Plan.CLOSE and c.option_type == _PLAY
        and getattr(c.stat, "hp", 0) > 0,
        weight=-6, status="testing"),
]
