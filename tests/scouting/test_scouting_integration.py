"""Real replay decks compile into the Opponent Model and remain recognizable."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.opponent import OpponentEvidence, OpponentKnowledgeBase, OpponentModel
from common.scouting.artifact import load_artifact
from common.scouting.provider import EngineCardStatProvider
from meta_tracker.archetype import classify
from meta_tracker.cards import load_cards
from meta_tracker.compile_scouting import compile_artifact
from meta_tracker.parse import extract_decks, load_replay
from scouting_helpers import make_obs


REPLAY = Path(__file__).resolve().parents[1] / "fixtures" / "episode-81364540-replay.json.gz"
ARTIFACT = Path(__file__).resolve().parents[2] / "src" / "common" / "scouting" / "artifact.json"
NOW = "2026-06-23T00:00:00"


def _episode(a0, d0, a1, d1):
    return {"arch0": a0, "deck0": d0, "arch1": a1, "deck1": d1,
            "band": "Mid", "end_time": "2026-06-22T00:00:00"}


def test_real_replay_decks_compile_and_recognize(tmp_path):
    cards = load_cards()
    first, second = extract_decks(load_replay(REPLAY))
    a0, a1 = classify(first, cards).name, classify(second, cards).name
    payload = compile_artifact([_episode(a0, first, a1, second)] * 3, cards, now=NOW)
    source = tmp_path / "artifact.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    provider = EngineCardStatProvider()
    provider.warm()
    knowledge = OpponentKnowledgeBase.compile(load_artifact(source, strict=True), (), provider)
    model = OpponentModel(knowledge, provider=provider)
    evidence = OpponentEvidence.from_state(make_obs(opp_discard=sorted(set(second))))

    snapshot = model.update(evidence)

    assert snapshot.candidates[0].archetype == a1


def test_strict_artifact_loader_rejects_an_empty_schema(tmp_path):
    source = tmp_path / "artifact.json"
    source.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="top-level schema"):
        load_artifact(source, strict=True)


def test_strict_artifact_loader_rejects_dossier_schema_drift(tmp_path):
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    next(iter(payload["dossiers"].values()))["unknown"] = True
    source = tmp_path / "artifact.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="dossier"):
        load_artifact(source, strict=True)
