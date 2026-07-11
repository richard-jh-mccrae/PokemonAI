# CGGame — cgpy standalone-engine build: handoff index (ADR-0050)

**Project:** reverse the native `src/cg` engine into `src/cgpy/` — a pure-Python twin at exact
parity — for DLL-free local play AND a clone/seed/step verification engine.
**Worktree:** `.claude/worktrees/strategy-ingest-item-lock-152c58`, branch
`claude/cggame-engine-reverse-engineer-bd04cf`. Milestone commit: `a509725`.
**Plan of record:** [ADR-0050](../../../docs/adr/0050-cgpy-is-a-trace-verified-python-twin-of-the-native-engine.md)
+ [src/cgpy/CONTEXT.md](../../../src/cgpy/CONTEXT.md) +
[docs/pyeng/determinism.md](../../../docs/pyeng/determinism.md).

| Step | Doc | Status |
|---|---|---|
| M0 — DSL vocabulary, table snapshots, determinism pins | [01-m0-vocabulary-and-pins.md](01-m0-vocabulary-and-pins.md) | ✅ done |
| M1 — trace harness + vanilla game loop | [02-m1-harness-vanilla-loop.md](02-m1-harness-vanilla-loop.md) | ✅ done (12/12 vanilla traces green) |
| M2 — chain interpreter + 50-union burn-down + CI gate | [03-m2-union-burndown.md](03-m2-union-burndown.md) | ✅ done (41/41 traces green, 29 committed fixtures, goldens in) |
| M3 — verification API + `CG_ENGINE=py` selection | [04-m3-verification-api.md](04-m3-verification-api.md) | ✅ done (42-game drop-in gate 0 crashes; verdict agreement 4/4 + f110 True-on-both; clone-safety all traces; DLL-free lethal harness) |
| M4 — pool-wide fan-out + coverage ledger | [05-m4-pool-fanout.md](05-m4-pool-fanout.md) | 🟢 core done 2026-07-11 (all 8 items built) — burn-down batches 1-4 done: **1238/1556 attacks live (batch 4 = reveal-hand family + ALL 25 shuffle-deck stragglers + 29/30 multi-clause coins + Rare Candy/Hand Trimmer/Levincia incl. the stadium-ability machinery), 293 traces green (26321 frames), op conformance 92/92 (UNPINNED empty), cross-engine audits 0 divergent, cabt match-replay 4/60→34/60**; the tail continues through the built loop (next: the ability tail — card 269 is named by the match-replay divergence; 528 attack-copy; energy-bounce + switch-variant attack stragglers) |

## Cold-start resume protocol (any session, this worktree)

```bash
# 1. sanity: everything committed so far still green (DLL-free, <1s)
python -m pytest tests/parity -q

# 2. the corpus: data/parity/ is GITIGNORED (regenerable). If the worktree was cleaned:
python tools/parity/capture_match.py --decks mega_starmie mega_starmie -n 3 --seed 1000 --prefix ms_mirror
python tools/parity/capture_match.py --decks mega_lucario dragapult_ex -n 2 --seed 2000 --prefix ml_dx
# (identical seeds ≠ identical games — native is unseeded; any fresh traces work the same)

# 3. the live burn-down loop (M2):
python tools/parity/replay_diff.py --all        # first divergence per trace = the next work item
```

**Ground rules that hold everywhere:** never modify `src/cg/`; cgpy never imports `cg` (it
loads the DLL); every native-behavior claim comes from a probe or a trace divergence — never
from memory (CLAUDE.md mandate); all option building/ordering lives in `src/cgpy/options.py`;
a def-less card exercised at runtime must raise `UnsupportedCard`, never guess.

**The method (works — keep it):** capture native games → replay through cgpy → the differ
reports the first divergence with a JSON path → implement exactly that → repeat. Divergences
are the specification. When a rule seems ambiguous across traces, capture more traces before
theorizing (they're free); trust live-obs traces over visualize-frame decodes.
