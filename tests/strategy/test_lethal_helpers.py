"""ADR-0050 Phase 2(D) — the reusable end-to-end lethal gate ``engine_confirms(fixture, pilot)``.

It drives a seeded correction fixture's win line through the real engine cascade
(``pilot._engine_confirms_win``) and returns the engine's verdict, so a multi-step lethal proposal is
gated on 'real play completes the line', not just closed-form recognition. Skips cleanly when the
native lib is absent, and is a no-op (None) on a fixture with no seed — the offline suite stays green.
"""
import json
from pathlib import Path

import pytest

from lethal_helpers import engine_confirms, require_cg

REPO = Path(__file__).resolve().parents[2]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _pilot(agent="mega_starmie"):
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    deck = [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider's audit-overridden table (ADR-0051)
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY, stats=EngineCardStatProvider(),
                 functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_returns_none_without_a_seed():
    """The gate is a no-op on an unseeded fixture — returns None (keep the closed-form verdict), never
    raises and never needs the native lib. This is what keeps the offline suite green cross-platform."""
    fx = {"obs": {"current": {"yourIndex": 0, "players": [{}, {}]}}, "correct": [0]}
    assert engine_confirms(fx, pilot=None) is None


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_a_shipped_lethal_wins_end_to_end():
    """Proof-of-life: the applied recover-energy lethal f110 (seeded) drives to a real engine WIN
    verdict through the cascade — the gate's positive case, independent of any new steering hook."""
    require_cg()
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    assert engine_confirms(fx, _pilot("mega_starmie")) is True


# f24's full win line (ADR-0050 DoD#3): attach {F}->Solrock, play 2x Premium Power Pro (+30 each to
# {F} attacks), retreat Lunatone (its {F} pays the cost), promote Solrock, Cosmic Beam 70+60=130 OHKOs
# Duraludon 130 — opp bench empty -> a bench-empty win. Explicit per-select picks through the attack;
# decide() then handles the trailing prize cascade. See docs/adr/0050-*, [[lethal-verification-tool-grill]].
_F24_WIN_LINE = [[5], [1], [1], [2], [0], [0], [2]]


# The verdict of ONE `engine_confirms` drive is not a fact about the agent — it is a sample. The
# native engine's RNG stream is process-global and unseedable, so each drive shuffles the seeded
# hidden zones afresh and the cascade's draws differ; on ml f24 the [correct]-only form refutes on
# essentially every stream but confirms on a rare lucky one (measured 1-in-150 in suite context,
# and it is what turned this test red on CI twice). So both directions below are stated as claims
# over K INDEPENDENT streams instead of over one:
#
#   * the target win is REAL          -> confirmed on at least one stream (an existence claim; one
#                                        engine verdict of True is a proof, and a stray None/False
#                                        on another stream cannot unprove it),
#   * decide() cannot COMPOSE it      -> refuted on at least one stream (the capability is unbuilt;
#                                        a lucky confirm is engine noise, not a shipped hook).
#
# The gate the docstring below promises is preserved and made sharper: once the Phase-3 steering
# hooks ship, the [correct] form confirms on EVERY stream, no refute survives, and this test goes
# red — which is exactly the signal the fix is meant to trip.
_F24_STREAMS = 5


def _verdicts(fx, agent, line=None, k=_F24_STREAMS):
    """``engine_confirms`` sampled over ``k`` independent engine RNG streams (each drive advances the
    process-global stream, so repeated calls are genuinely different samples)."""
    return [engine_confirms(fx, _pilot(agent), line=line) for _ in range(k)]


@pytest.mark.req("REQ-LETHAL-SEED-0005")
def test_engine_confirms_multi_step_line_proves_a_real_missed_win():
    """The multi-step gate (proof-of-target for a capability-gap): ml f24 is a REAL bench-empty win when
    the whole retreat/promote/tool line is driven explicitly, but its [correct]-only form REFUTES because
    decide()'s follow-up steering hooks are unbuilt (it never composes the line). This pins the target the
    `capability-gap-damage-boost-item-lethal` proposal builds toward; once its hooks ship, the [correct]
    form goes green on its own — that is the fix's gate."""
    require_cg()
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    driven = _verdicts(fx, "mega_lucario", line=_F24_WIN_LINE)
    assert True in driven, f"the explicitly driven win line never confirmed: {driven}"
    composed = _verdicts(fx, "mega_lucario")
    assert False in composed, (
        f"[correct]+decide() confirmed the win on every stream ({composed}) — the follow-up steering "
        f"hooks now compose the line, so this capability-gap gate has been met and should be retired")
