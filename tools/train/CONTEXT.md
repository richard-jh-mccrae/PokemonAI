# Bellman training evidence

Training no longer tunes weighted hypotheses. The retained tools preserve human Corrections and use
them as Bellman acceptance evidence.

- `blunder/`: correction schema, replay decisions, labels, provenance, telemetry joins, and storage.
- `bellman_corpus.py`: reruns Mega Starmie Corrections through the Bellman teacher (`brain="bellman"` path).
- `bellman_adjudicate.py`: classifies the unfiltered corpus against written rationales.
- `ledger_corpus.py`: the Ledger's training dashboard — every deck's Corrections through the live
  runtime; per-deck agreement, the generality floor, misses with their rationales, gap census,
  regressions vs a prior baseline (ADR-0145).

Deck behavior changes in shared Bellman code or declarative deck Roles, not generated `tuned.json`.
