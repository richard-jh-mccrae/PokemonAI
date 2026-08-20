# Training evidence and the Ledger's rounds

Human Corrections are the evidence base. The Bellman-era tools preserve them as acceptance
evidence; the Ledger's manual training rounds (plan §7, ADR-0147/0148) tune its weight vector
against them.

- `blunder/`: correction schema, replay decisions, labels, provenance, telemetry joins, and storage.
- `bellman_corpus.py`: reruns Mega Starmie Corrections through the Bellman teacher (`brain="bellman"` path).
- `bellman_adjudicate.py`: classifies the unfiltered corpus against written rationales.
- `ledger_corpus.py`: the Ledger's training dashboard — every deck's Corrections through the live
  runtime; per-deck agreement, the generality floor, misses with their rationales, gap census,
  regressions vs a prior baseline (ADR-0145); prize-anchor stamping + retired rulings (ADR-0147).
- `ledger_tune.py`: the §7 nudge / keep-best / adoption-gate loop over the Ledger's general
  weight vector; every trial lands in `docs/tuning/runs/`.

Deck behavior changes in shared Bellman code or declarative deck Roles, not generated `tuned.json`.
