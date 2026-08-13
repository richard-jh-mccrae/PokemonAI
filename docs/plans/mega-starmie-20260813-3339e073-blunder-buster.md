# Mega Starmie correction pass: 2026-08-13 3339e073

Source: `data/corrections/mega_starmie_20260813_3339e073/` (20 records).

## Classification

- New machinery:
  - `d39f2e524f36`: free pregame draw-count dominance.
  - `8c69ecaccafa`: nonlinear KO pressure in damage progress.
  - `8d91984d4430`, `91cea0a2fa6d`, `da39bb37b166`, `baede6accfac`,
    `79767ab416a7`: useful attached-Energy saturation, survival, and persistence.
- Tuning of existing state machinery:
  - `e02e699ced1d`: recovery cards have no accessible-hand value on a full-health board.
  - `dfc26070178c`, `c7fd0670fb3e`, `feafb8ef77c5`, `3c2afa3f1f28`: resolved by the
    shared repairs and retained Bellman continuation.
- Reclassified after full-turn review:
  - `92e27180b008`: deterministic evolution is worth `0.12`; the labelled Pokégear gamble
    is worth `0.09913` and does not dominate.
  - `5ee5f49312b2`, `da72e53929f0`: the analytic hidden-refresh commitment is negative; it
    cannot plan a hypothetical post-refresh hand or append an attack after that hidden boundary.
  - `76e7d6d7539e`: retreat reaches a stronger full-turn line than healing into a one-Energy
    attack; the three returned basic Energy cannot all be reattached this turn.
  - `c8ee8ab3e82b`: the record has no expected index; its written plan begins with Hilda, which
    is the runtime choice.
  - `188cceda7001`: Buddy-Buddy Poffin creates a valid Turbo Flare recipient before the attack.
  - `496a7657096f`: exhausting a deterministic dead search before shuffling it back is superior.
  - `baede6accfac`: the bounded full-turn search ties redundant pre-attack actions and currently
    chooses the attachment; preventing it requires an action cost not justified by retained gates.
  - `cb70b1405932`: Ignition Energy is forced to discard at End, so retreat does not sacrifice a
    durable resource and has the stronger continuation.

No named-card function, correction recognizer, or deck-local tactical branch was added.

## Bellman equations

- `DrawCount(s) = argmax offered numeric count` for cost-free mulligan draws.
- `damage_progress = damage / 200 + 1e-6 * prizes * (damage / max_hp)^2`.
- During isolated selections, useful Energy is survival-weighted and capped by the largest
  reachable attack cost for every attacker, including Basics. Basic lines receive increasing
  marginal value until the Active covers an immediate KO, then diminishing marginal value
  preserves optionality across attackers. Attached Energy does not consume hand capacity there.
- Recovery hand Worth is zero when no own body is damaged.

## Validation

- Focused adjudicated batch: 20/20 passed.
- Full correction suite: 41/41 passed.
- Bellman suite: 122/122 passed after updating corpus-size pins to 320 records / 1,915 semantic
  actions / 2,321 covered selection indices.
- Repository suite: `python -m pytest tests -q` exceeded the 10-minute command limit without
  emitting a failure; the process was terminated by the harness.
- A shortened 15-second mirror diagnostic was discarded because it terminated nine games and
  therefore was not a valid ten-game timing sample. A correct serial run using the 600-second
  default was started with `python tools/sim/mirror_gate.py mega_starmie --games 10 --workers 1`,
  but remains pending because the possible 100-minute wall time exceeds this publication pass.
