"""Teacher-runtime shell behavior: planner construction and epoch failure cleanup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from deprecated.bellman import build_teacher_runtime
from deprecated.bellman.card_worth import role_value
from deprecated.bellman.runtime import resolve_scouted_role_worth
from deprecated.bellman.scouting import LegacyRead
from common.scouting.artifact import Artifact
from observation_helpers import engine_opt


REPO = Path(__file__).resolve().parents[3]


def _strategy(name: str = "mega_starmie"):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_teacher_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


def _teacher():
    strategy = _strategy()
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    return build_teacher_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])


def _menu(options, *, min_count=1, max_count=1, context=0, turn=2):
    def player(*, own):
        return {
            "hand": [] if own else None, "handCount": 0, "active": [], "bench": [],
            "benchMax": 3, "deckCount": 0, "discard": [], "prize": [],
            "poisoned": False, "burned": False, "asleep": False,
            "paralyzed": False, "confused": False,
        }

    return {
        "select": {"context": context, "minCount": min_count, "maxCount": max_count,
                   "option": list(options)},
        "current": {
            "turn": turn, "yourIndex": 0, "firstPlayer": 0,
            "supporterPlayed": False, "stadiumPlayed": False,
            "energyAttached": False, "retreated": False, "result": None,
            "stadium": [], "looking": None, "players": [player(own=True), player(own=False)]},
        "logs": [],
    }


def test_planner_setup_survives_a_facedown_opponent_active():
    runtime = _teacher()
    observation = _menu([engine_opt(type=14)], turn=1)
    observation["current"]["players"][1]["active"] = [None]

    assert runtime._planner(observation) is not None


def test_a_planner_failure_still_closes_the_retained_native_session():
    runtime = _teacher()

    class BoomPlanner:
        discarded = False

        def _epoch_seconds(self, _request):
            return 1.0

        def prove(self, _request):
            raise RuntimeError("boom mid-epoch")

        def discard_precheck(self):
            self.discarded = True

    planner = BoomPlanner()
    runtime._planner = lambda _observation: planner
    observation = _menu([engine_opt(type=3, area=2, index=0), engine_opt(type=14)])

    decision = runtime.decide(observation)

    assert planner.discarded
    assert decision.chosen == (1,)
    assert decision.diagnostics["backend"] == "bellman-fallback"
    assert decision.diagnostics["fallback"]["cause"] == "exception:RuntimeError"


def test_quarantined_role_worth_resolver_preserves_dossier_weighting():
    artifact = Artifact({}, {}, {}, dossiers={
        "candidate": {"targets": [{"cardId": 7, "role": "primary_attacker"}]}})

    resolved = resolve_scouted_role_worth(
        LegacyRead([("candidate", 0.25)], 0.75), artifact, None)

    assert resolved == {7: 0.25 * role_value(("primary_attacker",))}
