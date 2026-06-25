"""Test fixture: returns a legal deck, then crashes on the first real decision.

Self-contained (no cg/common imports) so check_playability can run it with an empty
syspath. The deck is the cabt env's known-legal sample deck.
"""
SAMPLE_DECK = [
    721, 721, 722, 722, 722, 722, 723, 723, 723, 723,
    1092, 1121, 1121, 1145, 1145, 1163, 1163,
    1219, 1219, 1219, 1219, 1227, 1227, 1227, 1227, 1262, 1262,
] + [3] * 33  # 27 + 33 = 60


def agent(obs):
    if obs.get("select") is None:
        return SAMPLE_DECK
    raise RuntimeError("intentional crash")
