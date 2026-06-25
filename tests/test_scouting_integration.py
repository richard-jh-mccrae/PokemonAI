"""End-to-end: real replay decks -> compile -> load -> Scout recognizes.

Exercises the whole lib-free pipeline against the committed sample replay.
"""
import json
from pathlib import Path

import pytest

from common.scouting import Scout, load_artifact
from meta_tracker.archetype import classify
from meta_tracker.cards import load_cards
from meta_tracker.compile_scouting import compile_artifact
from meta_tracker.parse import extract_decks, load_replay

REPLAY = Path(__file__).resolve().parent / "fixtures" / "episode-81364540-replay.json.gz"
NOW = "2026-06-23T00:00:00"


def _ep(a0, d0, a1, d1):
    return {"arch0": a0, "deck0": d0, "arch1": a1, "deck1": d1,
            "band": "Mid", "end_time": "2026-06-22T00:00:00"}


def _obs_revealing(card_ids, *, your_index=0, turn=2):
    opp = 1 - your_index
    players = [None, None]
    players[your_index] = {"active": [{"id": 700}], "bench": [], "discard": []}
    players[opp] = {"active": [], "bench": [], "discard": [{"id": c} for c in card_ids]}
    return {"select": {"context": 0}, "logs": [],
            "current": {"turn": turn, "yourIndex": your_index, "players": players}}


@pytest.mark.req("REQ-SCOUT-0001")
def test_real_replay_decks_compile_and_recognize(tmp_path):
    cards = load_cards()
    d0, d1 = extract_decks(load_replay(REPLAY))
    a0, a1 = classify(d0, cards).name, classify(d1, cards).name

    art_dict = compile_artifact([_ep(a0, d0, a1, d1)] * 3, cards, now=NOW)
    p = tmp_path / "artifact.json"
    p.write_text(json.dumps(art_dict), encoding="utf-8")
    artifact = load_artifact(p)

    # Revealing side 1's whole deck should pin side 1's archetype.
    read = Scout(artifact).observe(_obs_revealing(sorted(set(d1))))
    assert read.candidates and read.candidates[0][0] == a1

    # Reset across matches: a prior match's reveal must not bleed into the next.
    scout = Scout(artifact)
    scout.observe(_obs_revealing(sorted(set(d0)), turn=9))
    read2 = scout.observe(_obs_revealing(sorted(set(d1)), turn=1))
    assert read2.candidates[0][0] == a1
