"""Test fixture: imports a sibling module (like a real agent's strategy.py).

Verifies the playability stage puts the agent's own dir on sys.path, as the grader does.
"""
import random

from helper import OK  # sibling module in this agent dir

SAMPLE_DECK = [
    721, 721, 722, 722, 722, 722, 723, 723, 723, 723,
    1092, 1121, 1121, 1145, 1145, 1163, 1163,
    1219, 1219, 1219, 1219, 1227, 1227, 1227, 1227, 1262, 1262,
] + [3] * 33


def agent(obs):
    assert OK
    if obs.get("select") is None:
        return SAMPLE_DECK
    return random.sample(range(len(obs["select"]["option"])), obs["select"]["maxCount"])
