# ADR-TEMP-584 — Post-pregame decisions have one coordinator entry

Every post-pregame legal menu enters the Decision Coordinator exactly once: a forced Candidate
Roster returns complete with zero Decision Delta and no preview, while failures remain in the same
contract and are chosen by the typed Fail-safe Policy. Direct runtime selection, effect latching,
and a second crash selector were rejected because each hides a game decision from replay and
training; only the engine's deck-submission protocol request bypasses game-decision coordination.
