"""Tier 5 trainer package (ADR-0042): mine labelled states from replays and fit the Automatic Value Model.

``extract`` walks replay films into ``(features, won)`` rows via the shipped Pilot's ``_board`` +
``common.value.features``; ``logistic`` is a pure-Python (dependency-free) L2-regularized trainer;
``train`` glues them and writes ``src/common/value/value_model.json``. Kept out of ``src`` because
it never ships to the grader — only the artifact does.
"""
