"""The automatic blunder labeler (ADR-0053 WP3; design: docs/plans/ml/ml-training-design-s3a.md).

Turns self-play corpus films into machine Corrections by grading each own decision against a value
net: the labeler IS the disagreement detector (S3b unifies WP3+WP4). This package owns the shared
detector; S3b consumes it through files only (the machine store, ``thresholds.json``, the CLI) —
never a build-time import.

Modules:
- ``vread``   — the shared per-decision P(win) reader (also feeds S2b's AIVAT stub; §D5).
- ``triage``  — consecutive-decision Φ-deltas that RANK fork budget but never emit (§D2).
- ``expert``  — one-step engine-fork value lookahead over the option menu (s3b §D1).
- ``detect``  — θ-disagreement → machine Corrections; the ``recorded``/``replayed`` choice knob.
- ``emit``    — the machine-store writer + run manifest (§D4).
- ``report``  — the played-well-lost view over lost games (§D6).
- ``run``     — the CLI (review vs emit, the ``thresholds.json`` gate).
"""
