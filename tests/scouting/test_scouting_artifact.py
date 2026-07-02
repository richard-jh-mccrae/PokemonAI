"""Artifact JSON loader: round-trip + fail-safe (docs/scouting.md)."""
import json

import pytest

from common.scouting.artifact import Artifact, load_artifact
from meta_tracker.compile_scouting import compile_artifact

NOW = "2026-06-23T00:00:00"


def _ep(a0, d0, a1, d1):
    return {"arch0": a0, "deck0": d0, "arch1": a1, "deck1": d1,
            "band": "Mid", "end_time": "2026-06-20T00:00:00"}


@pytest.mark.req("REQ-SCOUT-0007")
def test_load_artifact_roundtrips_and_intifies_keys(tmp_path):
    art_dict = compile_artifact([_ep("A", [1, 2], "A", [1, 2]), _ep("A", [1, 2], "B", [3])],
                                cards={}, now=NOW)
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps(art_dict), encoding="utf-8")

    art = load_artifact(p)

    assert isinstance(art, Artifact)
    assert "A" in art.priors
    assert all(isinstance(k, int) for k in art.background)              # JSON keys re-int'd
    assert all(isinstance(k, int) for k in art.card_inclusion["A"])     # lifted out of the dossier


@pytest.mark.req("REQ-SCOUT-0007")
def test_load_artifact_failsafe_on_missing_file(tmp_path):
    art = load_artifact(tmp_path / "nope.json")
    assert art.priors == {} and art.card_inclusion == {} and art.dossiers == {}
