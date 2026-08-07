"""System tests (ISTQB system level) for the whole blunder-busting feature, end to end on the
REAL agent — strategy, engine-backed Pilot, the tuner CLI's own Pilot builder, and the packaged
bundle run in a subprocess (cwd = bundle, like the Kaggle grader).

The journey, one test per stage:
  ST-1  identify a blunder + author a Correction WITH A NOTE  -> real inspector data spine
  ST-2  the noted Correction becomes a new-Hypothesis proposal -> real engine tune() (H route)
  ST-3  a Correction becomes a weight change                   -> real engine tune() (W route)
  ST-4  the packaged agent APPLIES the tune in a real decision -> real bundle, subprocess
  ST-5  the packaged agent USES a newly committed Hypothesis   -> real bundle, subprocess

ST-1..3 load the native engine in-process (fast, offline); ST-4..5 run the real shipped bundle.
All skip cleanly if the engine/agent is unavailable, so the lib-free fast suite is unaffected.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from meta_tracker.parse import load_replay  # noqa: E402
from submit.package import package  # noqa: E402
from pilot_helpers import (ATTACH, CARD, MAIN, NO, PLAY, TO_HAND, make_select, opt, poke,  # noqa: E402
                           state)
from train.blunder.correction import build_correction  # noqa: E402
from train.blunder.decisions import Decision, iter_decisions  # noqa: E402
from train.blunder.provenance import build_identity  # noqa: E402
from train.blunder.service import record_correction  # noqa: E402
from train.blunder.store import load_corrections  # noqa: E402
from train.tuner.io import sparse_overrides  # noqa: E402
from train.tuner.run import tune  # noqa: E402

AGENT = "mega_starmie"
# committed own-game replay (our agent-0 game) under the build-identity dir layout
REAL_REPLAY = (REPO / "tests" / "fixtures" / "replays" / "mega_starmie_20260625_bde590c"
               / "episode-81903490-replay.json.gz")
OWN_SEAT = 0                       # episode-81903490 is our agent-0 game
STARYU, CINDERACE = 1030, 666
MEGA_STARMIE, POFFIN = 1031, 1086   # the W-route grab pair: win-condition vs bench-fill

pytestmark = pytest.mark.skipif(
    not (REPO / "src" / "agents" / AGENT / "main.py").exists(),
    reason="real agent src/agents/mega_starmie not present",
)


@pytest.fixture(scope="module")
def real_pilot():
    """The exact engine-backed Pilot + seed weights the tuner uses (tune._build_pilot)."""
    try:
        from train.tune import _build_pilot
        return _build_pilot(AGENT)
    except Exception as exc:                       # native engine unavailable this env
        pytest.skip(f"engine-backed Pilot unavailable: {exc}")


def _taggable(replay, *, frame=None):
    """A real Decision (>=2 options, chosen in range) — at ``frame`` if given, else the first."""
    for d in iter_decisions(replay):
        if frame is not None and d.frame != frame:
            continue
        if len(d.options) >= 2 and all(0 <= c < len(d.options) for c in d.chosen):
            return d
    raise AssertionError("no suitable taggable Decision found")


def _other_index(d) -> list[int]:
    return [next(i for i in range(len(d.options)) if i not in d.chosen)]


def _run_agent(bundle: Path, obs: dict) -> list[int]:
    """Run the bundled agent's decide() on ``obs`` in a clean subprocess (cwd = bundle)."""
    (bundle / "probe_obs.json").write_text(json.dumps(obs), encoding="utf-8")
    probe = ("import json, main\n"
             "obs = json.load(open('probe_obs.json', encoding='utf-8'))\n"
             "print('RESULT' + json.dumps(main.agent(obs)))\n")
    env = {**os.environ, "PYTHONPATH": str(bundle)}
    proc = subprocess.run([sys.executable, "-c", probe], cwd=bundle, env=env,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"bundle run failed:\n{proc.stderr}"
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT"))
    return json.loads(line[len("RESULT"):])


# --- ST-1: identify a blunder, author a Correction with a note ---------------------------------

def test_tag_blunder_with_note_is_stored(tmp_path):
    """REQ-TUNER-0013: tagging a real Decision through the inspector spine stores a Correction
    with the human note, an auto-captured obs, decoded labels, and the build that played it."""
    if not REAL_REPLAY.exists():
        pytest.skip("committed own-game replay absent")
    replay = load_replay(REAL_REPLAY)
    d = _taggable(replay)
    bid = build_identity(REAL_REPLAY)
    note = "snipe the highest-threat benched attacker, not the wall"
    store = tmp_path / "corrections.jsonl"

    record_correction(replay, frame=d.frame, correct=_other_index(d), category="bad_target",
                      rationale=note, source="own", agent=AGENT, store_path=store,
                      agent_build=bid["agent_build"], agent_version=bid["agent_version"],
                      built_at=bid["built_at"])

    [stored] = load_corrections(store)
    assert stored.rationale == note               # note preserved verbatim
    assert stored.obs is not None                 # obs auto-captured from film (no manual entry)
    assert stored.correct_label                   # option decoded to a human label
    assert stored.agent_build == bid["agent_build"] and bid["agent_build"]   # build traceability


# --- ST-2: noted Correction translates to a new-Hypothesis proposal (H route) -------------------

def test_correction_with_note_becomes_a_hypothesis_proposal(real_pilot):
    """REQ-TUNER-0013: a Correction the agent is *blind* to (chosen & correct fire identical
    Hypotheses) becomes a missing_hypothesis proposal carrying the note as its authoring spec."""
    if not REAL_REPLAY.exists():
        pytest.skip("committed own-game replay absent")
    pilot, seeds = real_pilot
    replay = load_replay(REAL_REPLAY)
    note = "should snipe the higher-threat benched attacker with energy attached"

    proposal = None                               # find any own-seat decision routing H
    for d in iter_decisions(replay):
        if d.seat != OWN_SEAT or len(d.options) < 2 or not all(0 <= c < len(d.options) for c in d.chosen):
            continue
        corr = build_correction(d, source="own", agent=AGENT, correct=_other_index(d),
                                category="bad_target", rationale=note)
        res = tune([corr], pilot, seeds)
        if res.proposals:                         # identical fired sets -> no rule discriminates
            proposal = res.proposals[0]
            break

    assert proposal is not None, "expected at least one missing_hypothesis frame in the replay"
    assert proposal.rationale == note             # note IS the authoring spec


# --- ST-3: Correction translates to a weight change (W route) -----------------------------------

def test_correction_translates_to_a_weight_change(real_pilot):
    """Uses a responsive ``reg``: the production ``fit.DEFAULT_REG`` deliberately will not let one
    correction overturn a strong doctrine weight, which would hide the W-route mechanism."""
    pilot, seeds = real_pilot
    # A TO_HAND grab of two revealed deck cards, deliberately a SAME-TIER select: a Main-phase
    # play-vs-attach pair cannot exercise the W route, because TIER decides it before score does.
    grab_mega = {"type": CARD, "area": 1, "index": 0, "playerIndex": 0}
    grab_poffin = {"type": CARD, "area": 1, "index": 1, "playerIndex": 0}
    obs = make_select([grab_mega, grab_poffin], context=TO_HAND,
                      deck=[{"id": MEGA_STARMIE}, {"id": POFFIN}],
                      current=state(active=poke(STARYU, hp=70), bench=[poke(STARYU, hp=70)]))
    d = Decision(episode_id="synthetic", frame=0, seat=0, turn=2, select_context="ToHand",
                 select_type="ToHand", options=[grab_mega, grab_poffin], chosen=[0],
                 current=obs["current"], obs=obs)
    corr = build_correction(d, source="own", agent=AGENT, correct=[1], category="wasted_resource",
                            rationale="take the bench-fill, not a second Mega")

    # reg responsive enough to overturn the chosen option's weight — ``fit.DEFAULT_REG`` is
    # deliberately conservative. This is the W-route mechanism, not doctrine.
    res = tune([corr], pilot, seeds, reg=0.08)

    changed = sparse_overrides(res.overrides, seeds)
    assert res.fit_adopted                       # fit satisfied the correction, so it ships
    assert changed                               # a real Hypothesis weight moved (W route)
    assert set(changed) <= set(seeds)            # every changed key is a real Hypothesis id


# --- ST-4: packaged agent APPLIES the tune in a real decision -----------------------------------

def test_packaged_agent_applies_tuned_weight_in_a_decision(tmp_path):
    """REQ-TUNER-0013: the shipped bundle loads tuned.json and the weight changes which move it
    picks — an extreme override flips the choice an empty file would have made."""
    package(AGENT, tmp_path)
    bundle = tmp_path / AGENT
    # `power-up-attacker` is DELETED (ADR-0069 §7); the plumbing claim runs on the Active-preference
    # prior instead, which still drives an ATTACH and needs the option to name its TARGET.
    obs = make_select([opt(type=ATTACH, area=2, index=0, inPlayArea=4, inPlayIndex=0), opt(type=NO)],
                      context=MAIN, current=state(active=poke(CINDERACE, hp=70)))

    (bundle / "tuned.json").write_text("{}", encoding="utf-8")
    assert _run_agent(bundle, obs) == [0]         # ATTACH preferred

    (bundle / "tuned.json").write_text(json.dumps({"prefer-active-attach-in-setup": -100000.0}),
                                       encoding="utf-8")
    assert _run_agent(bundle, obs) == [1]         # tune flips the decision


# --- ST-5: packaged agent USES a newly committed Hypothesis -------------------------------------

def test_packaged_agent_uses_a_newly_committed_hypothesis(tmp_path):
    """REQ-TUNER-0013: once a human commits a new when() to the deck Strategy, the shipped agent
    fires it — here a rule favouring 'play' options flips the decision the base agent would make."""
    package(AGENT, tmp_path)
    bundle = tmp_path / AGENT
    (bundle / "tuned.json").write_text("{}", encoding="utf-8")
    obs = make_select([opt(type=NO), opt(type=PLAY)], context=MAIN, current=state())

    assert _run_agent(bundle, obs) == [0]         # baseline: nothing prefers 'play' option

    strat = bundle / "strategy.py"
    strat.write_text(
        strat.read_text(encoding="utf-8")
        + "\nfrom common.strategy import Hypothesis as _H\n"
        + "STRATEGY.hypotheses.append(_H('st-new-rule', '', "
        + "when=lambda c: c.option_type == 7, weight=999.0))\n",
        encoding="utf-8",
    )
    assert _run_agent(bundle, obs) == [1]         # agent now fires the committed Hypothesis
