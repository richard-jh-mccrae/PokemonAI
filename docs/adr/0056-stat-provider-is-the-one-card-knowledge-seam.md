# ADR-0056: The Stat Provider is the one card-knowledge seam; records answer single-card questions

<!-- Renumbered 0051 → 0056 (2026-07-13): ADR-0051 was taken by the MatchupPlan
target-priority spine on main; this branch's Stat Provider ADR moved to the next free slot. -->

**Status.** Accepted (2026-07-13) and **BUILT** — merged to main: the Stat Provider is the one
card-knowledge seam, the Pilot's seven attack-fact constructor arguments and the legacy synth fallback
are retired, and `EngineCardStatProvider.warm()` runs in `runtime.build_pilot`'s pregame window.
Neutrality proven by score-diff (315 frames × 3 agents, 0 divergent).

**Context.** Attack facts reached the Pilot through SEVEN constructor arguments — five
per-mechanic legacy dicts (`attacks`, `attack_costs`, `recoil`, `bench_snipe`,
`bench_spread`), a narrow `ignores_active_effects` feed, and the modern `attack_stats`
table (ADR-0032) — each rebuilt by every agent's `main.py`, the test fixture, `tune.py`
and `lethal_probe.py`. The same card text was parsed twice at import (the dict builds
beside `build_attack_stats`), the same fact lived in two shapes, and the copies drifted:
`tune.py`'s "mirror main.py EXACTLY" builder was missing four switches and the retest
featurized a different Pilot than the one that shipped. Around `CardStat`, 60+ call
sites re-derived the same interpretations from raw fields (the ex/Mega-ex prize ladder,
`cardType` comparisons, the `(minAttackCost or 99)` affordability idiom) — the
interpretation had no home. The 2026-07-12 architecture review named this the root of
the 30-argument Pilot constructor.

**Decision.**
- The **Stat Provider** is the ONE card-knowledge seam: `get(card_id) → CardStat`,
  `attack(attack_id) → AttackStat` (audit-overridden, built inside the engine adapter's
  single lazy build site), and the cross-card queries (forward-evolution, name
  resolution). Two adapters share the record classes: `EngineCardStatProvider` (runtime;
  `warm()` forces the build in the pregame window — each agent calls it at import) and
  `DictCardStatProvider` (lib-free; takes `attacks=`).
- **Records answer single-card questions about themselves**: `CardStat.is_ex_body` /
  `prize_value` / `is_pokemon` / `is_item` / `is_tool` / `is_supporter` / `is_energy` /
  `is_basic_energy` / `is_typed_basic_energy` / `can_pay_cheapest(energy)`;
  `AttackStat.is_deterministic`. Byte-faithful ports of the call-site idioms — a
  hand-built record in a test answers exactly like the engine path.
- **Site-specific defaults stay at the call site.** `(minAttackCost or 99)` vs `or 0`
  are opposite epistemics by design (my-side affordability fails CLOSED; an
  opponent-threat read fails WORST-CASE) — that is judgment, not interpretation, and is
  not folded into the records.
- The Pilot's seven attack-fact constructor arguments and the legacy synth fallback are
  **retired**; `Pilot._attack_stat` resolves through `stats.attack()`. The wiring test
  pins the retirement (no legacy kwargs in any `main.py`, `warm()` present).

**Considered options.** Keeping `attack_stats=` as the Pilot's one attack argument
(rejected: agents/tools keep an eager-build block that can drift — the exact bug class
this removes). Questions on the provider instead of the records (rejected: every call
needs a provider in hand + an unknown-id guard; a bare record in a test couldn't
answer). A ctor-time normalization shim for the legacy kwargs (rejected: the legacy
vocabulary would stay legal forever).

**Consequences.** A Pilot needs `stats=` for any attack knowledge (stat-blind ⇒
attack-blind, fail-open as before). `main.py` loses its whole eager dict-build block —
`_provider.warm()` keeps the pregame build; `score_diff`/`tune` ride the same builder so
the retest can no longer drift from the runtime. Neutrality was proven per step
(score-diff `scores` mode, 315 frames × 3 agents, 0 divergent) and the one surfaced
table-truthiness gate (`_grab_enabler_lethal`) was relaxed to per-record resolution.
Card-tier interpretation now has exactly one home; new questions go on the records, not
into call sites.
