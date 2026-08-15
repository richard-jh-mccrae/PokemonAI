from pathlib import Path
from collections import Counter
import json

import pytest

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
ROWS = tuple(c for c in load_corrections(REPO / "data" / "corrections")
             if c.agent == "mega_starmie")


def _correction(episode, frame):
    return next(c for c in ROWS
                if c.episode_id == episode and int(c.decision.get("frame", -1)) == frame)


@pytest.mark.parametrize(("episode", "frame", "expected"), (
    (82522698, 62, [15]),       # direct game win dominates setup
    (82749168, 88, [8]),        # direct game win dominates information
    (85163079, 30, [0]),        # loaded future win condition is the gust target
    (83116081, 21, [0]),        # Turbo Flare concentrates on the developed line
    (82224509, 56, [1]),        # Scouting ranks the real snipe threat
    (82523811, 61, [3]),        # future three-prize line outranks filler
    (82752604, 62, [0]),        # loaded Drakloak outranks the wall
    (82753102, 85, [0]),        # Kadabra line outranks Dunsparce
    (83966968, 79, [1]),        # damaged multi-prize gust target
    (84897262, 110, [1]),       # fetched Water unlocks the game win
    (82749168, 21, [2]),        # attach is a commutative prefix to Hammer on the energized Bench
    (82228017, 4, [2]),         # Cape is a commutative free prefix to the ruled Water attach
    (82752604, 16, [2]),        # redundant Mega Signal loses to the resolving attack
    (82717711, 18, [1]),        # a legal beneficial attack beats exact-zero End
    (83116081, 76, [5]),        # heal then reattach then KO survives bounded search
    (83456015, 35, [3]),        # exposed Active is healed before the typed KO line
    (81785223, 39, [2]),        # visible Energy makes Clefairy the immediate snipe threat
    (81785223, 45, [2]),        # the same threat rule survives a different Bench ordering
    (82225138, 46, [0]),        # current Scouting overrides the stale Dwebble target label
    (92102433, 41, [1]),        # resolving Jetting Blow removes the live opposing line
    (92102433, 44, [0]),        # reachable stage-two line outranks a lower-value draw body
    (92102433, 89, [0]),        # Cinderace preserves the attach -> Turbo -> Nebula line
    (92104376, 86, [0]),        # promotion keeps the deliberate seven-prize route available
))
def test_rationale_led_hard_gates(episode, frame, expected):
    chosen = runtime().decide(_correction(episode, frame).obs).chosen
    if (episode, frame) == (83116081, 76):
        assert chosen in {(5,), (9,)}  # retreat commutes with the ruled heal-and-reattach line
    else:
        assert chosen == tuple(expected)


def test_heal_targets_the_exposed_active_not_the_loaded_safe_bench():
    assert runtime().decide(_correction(None, 100).obs).chosen == (0,)


def test_20260812_sequence_and_target_corrections():
    records = [json.loads(line) for line in (
        REPO / "data" / "corrections" / "mega_starmie_20260812_1a37dbb5" /
        "corrections.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = {
        "9e502ba97ac7": [0],       # live Mega Signal thins its target before Pokégear
        "e4fae85fcf63": [0],       # free deterministic search, then the ruled attack over End
        "fa978d4e6fe4": [0],       # damage the scouted evolving win condition
        "0a482197b23f": [0],       # either identical Salvatore copy of corrected option 2
        "995549cd76ee": [0],       # evolve the loaded Staryu
        "03fae5aa66e0": [5],       # Ultra Ball begins the proved same-turn game win
        "71cf48e4701c": [6],       # Strategy establishes Staryu; Pokégear is a free prefix
        "4eaf233ccb54": [0, 1],    # discard duplicate tutor access; retain live Hammer
        "5972e5096b0c": [0],       # damage the scouted Alakazam win condition
    }
    for record in records:
        observation = record["obs"]
        if record["id"] == "03fae5aa66e0":
            observation = dict(observation)
            prizes = record["decision"]["current"]["players"][0]["prize"]
            observation["own_prizes"] = dict(Counter(str(card["id"]) for card in prizes))
        chosen = runtime().decide(observation).chosen
        if record["id"] == "9e502ba97ac7":
            assert chosen in {(0,), (1,)}
        elif record["id"] == "0a482197b23f":
            assert chosen in {(0,), (1,)}
        elif record["id"] == "71cf48e4701c":
            assert chosen in {(2,), (6,)}
        else:
            assert chosen == tuple(expected[record["id"]]), record["id"]
