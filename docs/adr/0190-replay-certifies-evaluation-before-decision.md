# ADR-0190 — Replay certifies evaluation before decision

Offline replay always certifies legal actions and decomposed root and successor evaluations under
recorded identities. Full-choice reproduction is a separate stronger certificate available only
when behavior identity and deterministic stopping conditions resolve, avoiding false failures from
wall-clock search termination.
