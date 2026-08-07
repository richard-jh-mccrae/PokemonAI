"""Lethal-recover (ADR-0030) — the grab-enables-lethal tactical (`_grab_lethal_tactical`).

The win rung (plan_turn) is MAIN-only, so a lethal whose FIRST step is a resource GRAB at a `_TO_HAND`
search/recover select is expressed as a KO_SCORE-class tactical on the grab option instead. Grabbing a
reusable Basic Energy (direct) or a `tutor_energy` card the deck can cash — then attaching it onto the
Active or retreating into a benched attacker — that delivers a min-bound KO of the opponent's Active
scores KO_SCORE + prize, mirroring `_attach_lethal_tactical`. Two outright thrown WINS (f110, f24) + two
missed KOs (f26, f48) across mega_starmie + mega_lucario. Fixtured through the shipped, engine-backed
Pilot (`decide()`), the strict retest bar.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import param_for

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent):
    """The shipped Pilot, with the develop rung's ENGINE ROLLOUT pinned off.

    The rung ranks candidates on `_engine_leaf_value`, which sims through the native engine. That
    engine's RNG stream is process-global and unseedable, so the SAME sim of the SAME option returns
    a different value on every call — measured on ml f24 across 25 streams, option 3 came back 162
    (13×), 129 (4×) and a phantom 7000 "win" (8×); only one of the 13 options was stable. Whether the
    rung defers (a KO_SCORE-class leaf reads as an unsound rollout-win) or overrides the human's
    lethal-enabling attach therefore depends on the process's RNG position — the CI heisenbug
    `_develop_rollout_line`'s own docstring names, which the coin gate alone did not close (coin-FREE
    values are not stream-invariant either). Off: this fixture picks [5] 20/20; on: [3] ~1-in-20.

    These are lethal-recover CORRECTION RETESTS: they pin the win/tuned rungs' verdict on a captured
    state, and the develop rung is the bottom rung that only fires when those return None. Pinning it
    off keeps the bar strict on the layers under test instead of resampling engine noise. The rung's
    own stream-dependence is a live agent question (its override authority is specified as resting on
    a reproducible end-board), NOT something these tests can settle — tracked in issue #160.
    """
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    pilot.develop_rollout = False
    return pilot


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


_AREA_ZONE = {4: "active", 5: "bench"}          # engine area code → the obs player zone


def _target_body_id(obs: dict, opt: dict):
    """The card id of the Pokémon an ATTACH option targets (via inPlayArea/inPlayIndex → my zones),
    or None for a non-attach / unresolved target."""
    if opt.get("type") != 8:                    # 8 = Attach
        return None
    cur = obs.get("current") or {}
    players = cur.get("players") or []
    yi = cur.get("yourIndex", 0)
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    bodies = me.get(_AREA_ZONE.get(opt.get("inPlayArea")) or "") or []
    i = opt.get("inPlayIndex")
    return bodies[i].get("id") if (isinstance(i, int) and 0 <= i < len(bodies)) else None


def _equivalent(obs: dict, chosen_idx: int, correct_idx: int) -> bool:
    """Two option indices are interchangeable iff they achieve the SAME lethal-enabling step. For an
    ATTACH that means the same energy card onto a body with the same card id — so attaching {F} to
    EITHER of two identical benched Solrock is the same enabler (ml f24 has two Solrock; the fixture
    pins one arbitrarily). Non-attach steps compare by exact index."""
    opts = obs["select"]["option"]
    a, b = opts[chosen_idx], opts[correct_idx]
    if a.get("type") != b.get("type"):
        return False
    if a.get("type") == 8:
        tid = _target_body_id(obs, b)
        return (a.get("cardName") == b.get("cardName") and tid is not None
                and _target_body_id(obs, a) == tid)
    return chosen_idx == correct_idx


@pytest.mark.req("REQ-PLAN-0030")
@pytest.mark.parametrize("agent,fixture", [
    ("mega_starmie", "ms_lethal_recover_energy_to_win_f110.json"),   # grab the {W} that wins (active)
    param_for("ml_lethal_retreat_boost_to_ko_f24",                # attach {F} to Solrock (boost line)
              "mega_lucario", "ml_lethal_retreat_boost_to_ko_f24.json",
              id="mega_lucario-ml_lethal_retreat_boost_to_ko_f24.json"),
    ("mega_lucario", "ml_lethal_recover_energy_retreat_ko_f26.json"),  # fetch {F}, retreat-into-Mega KO
    ("mega_lucario", "ml_lethal_recover_energy_via_gong_f48.json"),  # grab Fighting Gong (energy tutor)
])
def test_lethal_recover_takes_the_enabling_step(agent, fixture):
    """On each captured state the shipped Pilot takes the lethal-enabling grab/attach the human wanted,
    not the develop it took live (the recover-the-energy-that-wins line is now seen). The human's
    `correct` index is matched up to INTERCHANGEABILITY (`_equivalent`) — attaching the {F} to either
    of two identical Solrock is the same enabler, so the assertion doesn't over-pin one of two equal
    targets (ml f24)."""
    fx = _fx(fixture)
    obs = fx["obs"]
    chosen = _shipped_pilot(agent).explain(obs).chosen
    assert all(any(_equivalent(obs, ch, c) for ch in chosen) for c in fx["correct"]), (
        f"{fixture}: chose {chosen}, expected the lethal-enabling {fx['correct']} ({fx.get('correct_label')})")


@pytest.mark.req("REQ-PLAN-0030")
def test_the_retest_bar_is_stream_invariant():
    """The guard on the bar above: a retest verdict must be a FACT about the agent, not a sample.

    Every drive of the native engine shuffles the seeded hidden zones off a process-global,
    unseedable RNG stream, so any layer that ranks on a simmed board decides differently run to run.
    ml f24 is the marginal state that exposes it — with the develop rung's rollout live it picked the
    lethal-enabling attach ~19-in-20 and the rollout's own candidate otherwise, which is precisely how
    this suite went red on CI without a code change. Re-running the same decision here pins that the
    retest pilot has no such sampling left in it: same state, same answer, every time.

    Two checks, deliberately of different kinds. The first is exact: the one rung KNOWN to rank on a
    simmed board stays off the retest path. The second is a sampling TRIPWIRE for a rung nobody has
    written yet — sized to stay cheap (12 drives ≈ 1.5s), so it is a smoke alarm, not a proof: it
    catches f24's old ~1-in-20 flip about half the time on any given run, and a noisier rung sooner.
    Either way the answer is to decide whether the RUNG should be made reproducible — the authority to
    override the tuned scoring is specified as resting on a reproducible end-board — rather than to
    let CI rot into a coin flip."""
    fx = _fx("ml_lethal_retreat_boost_to_ko_f24.json")
    obs = fx["obs"]
    assert _shipped_pilot("mega_lucario").develop_rollout is False, (
        "the develop rung's engine rollout is back on the retest path; its leaf values are not "
        "reproducible across engine RNG streams, so the retest bar becomes a sample")
    picks = {tuple(_shipped_pilot("mega_lucario").explain(obs).chosen) for _ in range(12)}
    assert len(picks) == 1, f"the retest decision is stream-dependent — got {sorted(picks)} across 12 drives"
