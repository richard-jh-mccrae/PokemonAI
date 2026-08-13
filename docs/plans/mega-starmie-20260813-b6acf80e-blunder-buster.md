# Mega Starmie correction pass: 2026-08-13 b6acf80e

Source: `data/corrections/mega_starmie_20260813_b6acf80e/` (7 records).

## Classification

- New machinery:
  - `d11d625a6db3`, `c070b8acd261`: End must resolve forced turn-boundary changes, including
    expiring attached resources, instead of always presenting a zero-value snapshot.
  - `8dfa2f8ef65d`: attack readiness distinguishes immediate Active access from discounted Bench
    access.
  - `dbf1ff1d6fef`: completed Bench evolution has explicit prize-scaled development value.
- Reclassified after Bellman review:
  - `9fb08842a8df`: Salvatore is already spent at this decision boundary. Its cost is sunk, and the
    current-state continuation prefers declining; encoding the prior intent as a decline penalty
    would be an action rule rather than Bellman value.
  - Prior batch `9e502ba97ac7`: the rebased need-aware evaluator prefers Pokégear before the now
    redundant deterministic Mega search. The same stale expectation fails on rebased `main`.
- Existing machinery confirmed:
  - `670360dc929a`: opponent role pressure selects the developed Bench attacker as the snipe target.
  - `3e893829feb9`: Bellman continuation uses energy denial before hand disruption.

No correction-specific or named-card branch was added. Evolution value is derived from the offered
body's portable Worth and prize liability; readiness is derived from board location.

## Bellman equations

- `End(s) = V(T_end(s)) - V(s)` when the provider can resolve the real turn boundary; abstract test
  providers retain the exact-zero lower bound.
- `own_readiness = max(active_attack_value, 0.5 * best_bench_attack_value)`.
- `development = 0.04 * sum(prize_value(body))` over evolved own Bench bodies.
- No action-specific evolution penalty is used.

## Validation

- Focused correction batch: 7/7 pass, including the reviewed `9fb08842a8df` reclassification.
- Bellman suite after rebase: 120/120 pass.
- Full correction suite: 21/21 pass.
- Packaged deployability: pass.
- Serial ten-game packaged mirror command:
  `python tools/sim/mirror_gate.py mega_starmie --games 10 --max-match-seconds 600`.
  Match 1 exceeded 600 seconds and the harness cleanup hung, so the outer run was terminated; no
  valid match or callback timing sample was produced.
