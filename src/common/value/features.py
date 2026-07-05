"""The Base Value Model's feature vector (ADR-0042): the Tier-3/Tier-4 objective primitives read off
a :class:`~common.pilot.Board`, in a FIXED, named order shared by the trainer and the runtime.

The bet (ADR-0007): a raw board encoding would force the model to re-learn prize math and race
judgment from scratch; feeding it the ALREADY-COMPUTED objective primitives means the logistic only
has to learn their *relative weights* — less data, and the fitted weights stay narratable ("the race
deficit dominates"). Pure and lib-free; ``None`` path-turns collapse to a documented sentinel so an
early board (paths unknown) is a valid, in-distribution row rather than a hole.
"""
from __future__ import annotations

# Unknown path-turns (a path running through not-yet-fielded bodies) read as "far" — a large but
# finite horizon, so the feature is monotone and standardizable rather than a NaN hole.
_UNKNOWN_TURNS = 12.0

# The FIXED feature order. Appending is safe (retrain); reordering/removing breaks a shipped model —
# the loader pins to this list's length + names via the model's own `features` field.
FEATURE_NAMES = (
    "bias",                    # constant 1.0 — the intercept rides in the weight vector
    "race_ahead",              # their_path_turns − my_path_turns (turns; + = I'm ahead)
    "my_path_turns",           # my cheapest acquisition path length (sentinel when unknown)
    "their_path_turns",        # their cheapest path over my board (the denial side)
    "my_prizes_remaining",     # prizes I still need
    "opp_prizes_remaining",    # prizes they still need
    "prize_diff",              # opp_prizes − my_prizes (+ = I'm ahead on the count)
    "favorability",            # compiled matchup win-rate vs the Read's candidates (0.5 neutral)
    "posture_confidence",      # γ — the Read's recognition strength
    "my_bench",                # my benched body count (development)
    "opp_bench",               # their benched body count
    "my_active_hp",            # my Active's remaining HP
    "my_active_energy",        # Energy on my Active
    "incoming_active_damage",  # closed-form worst incoming vs my Active
    "active_doomed",           # 1.0 if they can KO my Active next turn
    "line_ready",              # 1.0 once a win-condition payoff is online (SETUP→RACE)
    "in_play_bodies",          # my total bodies in play (Active + Bench)
)


def features_from_board(board) -> list[float]:
    """The feature vector for ``board`` in :data:`FEATURE_NAMES` order — pure, total, never raises.
    Booleans map to 0.0/1.0; a ``None`` path-turn reads as :data:`_UNKNOWN_TURNS`; a missing field
    reads as 0.0 (the null-model-safe default)."""
    my_turns = board.my_path_turns if board.my_path_turns is not None else _UNKNOWN_TURNS
    their_turns = board.their_path_turns if board.their_path_turns is not None else _UNKNOWN_TURNS
    race = board.race_ahead if board.race_ahead is not None else (their_turns - my_turns)
    my_pz = float(board.my_prizes_remaining)
    opp_pz = float(board.opp_prizes_remaining)
    return [
        1.0,
        float(race),
        float(my_turns),
        float(their_turns),
        my_pz,
        opp_pz,
        opp_pz - my_pz,
        float(board.favorability),
        float(board.posture_confidence),
        float(board.my_bench),
        float(len(board.opp_bench)),
        float(board.my_active_hp),
        float(board.my_active_energy),
        float(board.incoming_active_damage),
        1.0 if board.active_doomed else 0.0,
        1.0 if board.line_ready else 0.0,
        float(len(board.in_play_ids)),
    ]
