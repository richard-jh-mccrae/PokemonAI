# ADR-0052: Combat math is one KO-oracle module with explicit dependencies

**Status.** Accepted (2026-07-13) and **BUILT** — `CombatMath` ships as `src/common/strategy/combat.py`
and is merged to main; the card-level KO fallback and the duplicate W/R + ex-prevention implementation
are deleted (`damage.py` is the one home). Neutrality proven per step by score-diff (`scores` mode, 315
frames × 3 agents, 0 divergent). No PROFILE flag — it is a structural refactor, always on.

**Context.** The 2026-07-12 architecture review's highest-leverage finding: the closed-form
"can X KO Y / what is that KO worth / how fast does either side fell a body" computation was
the most duplicated thing in the decision core — six sibling `*_tactical` scorers sharing a
copy-pasted frame (re-fetch the opp Active, re-loop attacks under an affordability cap,
re-test `dmg >= hp`, return the `KO_SCORE + prize` band), a ~12-method KO cluster on the
Pilot, turns-to-KO copies in the objectives/planner mixins, and a SECOND Weakness/Resistance
+ ex-prevention implementation (`_wr_adjusted` / `_ability_prevents_damage`) kept in sync
with `damage.py` by hand. All of it ran on the Pilot's god-namespace: nothing was testable
without a fully wired Pilot.

**Decision.**
- **`CombatMath`** (`strategy/combat.py`) is the ONE closed-form home for combat judgment:
  the damage core (`predicted_damage`, `predicted_max_damage`), reachability
  (`can_ko_cheapest` / `can_ko_affordable` / `can_damage` / `maxed_kos`), the shared KO
  valuation band (`best_affordable_ko_value` — retreat/gust/promote/attach/boost lookaheads
  all price hypothetical attackers on it), bench-rider prize math, typed affordability, the
  worst-case Incoming family (`incoming_active_damage` / `forward_incoming_damage` /
  `active_doomed`), and `turns_to_ko`. It composes the pure `damage.py` seam.
- **Explicit dependencies, no Pilot**: constructed from the knowledge seams — the Stat
  Provider (ADR-0056), `CardFunctions`, the match-scoped `TransientTracker` — with
  per-decision facts (the damage context, the opponent's bench snapshot) as call arguments.
  Standalone-testable; the injectable combat primitive a future doctrine-DI step needs.
- The Pilot builds one oracle in its constructor and **delegates** through thin wrappers, so
  the planner/objectives/doctrine mixins' `self._*` call sites are untouched.
- The **card-level KO fallback is retired**: `_can_ko`'s `minCostDamage` branch,
  `_ability_prevents_damage`, and the Pilot's `_wr_adjusted` are deleted. `damage.py` is the
  one W/R + prevention home (`wr_adjust` exported for the attack-blind worst-case fallback,
  beside the attack-gated `compute_active_damage`). No record, no claim.
- **Deliberately NOT unified**: the six tactical scorers' remaining per-scorer gating
  (necessity, marginality, retreat legality, requiresBench, boost stacking) and their band
  variants — their shared frames died into the oracle, and one more forced abstraction would
  either shift scores or be a parameter-per-difference shallow wrapper. Likewise the
  Incoming-affordability stance is UNCHANGED (worst-case by design;
  `ADR-0064`) and the γ/forward-forms orchestration stays with the
  objectives that own it.

**Considered options.** Growing `damage.py` with free functions (rejected: callers keep
assembling stats/context — the pure-function-dump shape). Concentrating the methods on the
Pilot without a new seam (rejected: stays a view over the god-namespace; the deletion test
still fails). Full six-scorer band unification (declined above, on the record).

**Consequences.** Combat judgment has one home with one test surface
(`tests/strategy/test_combat.py` — worked-example literals, no Pilot). Neutrality proven per
step (score-diff `scores` mode, 315 frames × 3 agents, 0 divergent at every commit); the
retired fallback surfaced 15 fallback-born tests, completed with real cheapest-attack
records rather than weakened. New combat mechanics land in `CombatMath` (or `damage.py` for
per-attack modifiers), never in a Pilot method or a scorer.
