# Attack Effects & the Damage Oracle

Per-attack effect facts (ADR-0032 **Attack Effect**) and the ONE closed-form damage computation
every Tier-0 estimate routes through. The card-level model couldn't say "*this* attack ignores the
defender's Ability" — so vs Crustle (`prevent_ex_damage`) the agent zeroed **every** Mega Starmie ex
attack, including Nebula Beam (which pierces and lands 210), and threw away Jetting Blow's
still-landing 50 bench snipe. Decision: [ADR-0032](adr/0032-card-knowledge-is-an-engine-audited-effect-compendium.md);
terms (*Attack Effect*, *Damage Formula*, *Effect Clause*) in
[src/common/CONTEXT.md](../src/common/CONTEXT.md).

## The two new pieces

- **`AttackStat`** (`common/scouting/provider.py`) — the attack-keyed record beside the card-keyed
  `CardStat`: printed damage, energy cost, the rider amounts (recoil / bench-snipe / hand-size),
  and the **ignore flags** `ignoresWeakness` / `ignoresResistance` / `ignoresEffects`. Flags are
  seeded by `parse_attack_ignores` — the whole-sentence "This attack's damage isn't affected by …"
  family (26 attacks in this pool; Conkeldurr's cost-scoped "ignore all Energy" correctly excluded)
  — and corrected via `build_attack_stats(attacks, overrides)` (audit-generated or hand-authored;
  an override beats a parse, never invents an attack).
- **The damage oracle** — pure `compute_active_damage(attack, attacker, defender, defender_tags)`
  (`common/strategy/damage.py`): printed damage, then unless the attack's own flag pierces it —
  damage-prevention (`prevent_ex_damage` vs an ex/Mega attacker → 0), Weakness (×2), Resistance
  (−30, floored at 0), in rules order (rules.md §5). Fail-open: missing stats never invent a
  modifier. The Pilot wrapper `predicted_damage(attacker_id, attack_id, defender)` resolves ids →
  stats/tags; without a wired `attack_stats` table it synthesizes a flagless record from the legacy
  dicts, reproducing pre-oracle behavior exactly.

## Per-target semantics

The oracle computes damage to the defending **Active** only. A bench-snipe rider
(`AttackStat.benchSnipe`) is a separate path — ignores Weakness/Resistance by rule and is NOT
stopped by the Active's prevention: Jetting Blow vs Crustle deals 0 to the Active while its 50
still KOs a benched 40-HP Dreepy (a banked prize the old early-return hid).

## Routed call sites (all of Tier-0)

`Pilot._tactical` (attack scoring), `LethalMixin._attack_wins`, `_best_affordable_ko_value`
(retreat/evolve-to-lethal), `_attach_lethal_tactical.best_affordable`, `_can_ko` (cheapest-attack
oracle; legacy card-level fallback for stats-only callers), `_active_can_ko`, gust
`_gust_snipe_synergy`; and every **Incoming** estimate via `_predicted_max_damage` (per-attack max
when every record resolves — a partially-known table never shrinks a worst case — else card-level
`maxDamage` × W/R): `_incoming_active_damage`, planner `_incoming_worst`, gust
`_gust_target_denial`, tool `_opp_best_attack_vs`. Incoming is now per-attack too: an opponent's
ignore-flag attack prices full vs my resist body, and my own `prevent_ex_damage` wall fears only
what pierces it.

## Verification

Text is the **seed**, the simulator is the **authority** (CLAUDE.md): the audit harness
(`tools/sim/audit_attacks.py`) drives the engine over a fixed defender panel (vanilla / Weak /
Resistant / Crustle) plus single-variable sweeps and coin forks (`search_begin(manual_coin=True)`),
and `tools/sim/diff_attack_audit.py` diffs every measurement against `compute_active_damage` —
coin records against their own bound, a conditional's live outcome against its [min, max]. The
generator (`tools/sim/generate_attack_overrides.py`) turns fork bounds / constant effect damage /
exact sweep fits into the shipped `common/attack_overrides.json` (117 attacks, engine-derived).
**Pool-wide status (2026-07-02, all 1556 attacks, 11.8k measurements): 9211/9539 = 96.6% verified;
over-predictions ZERO — every residual gap under-predicts, the safe direction (a Lethal never
banks on damage the engine won't deal). 328 gap-records remain (unfitted scaler variants and
conditional bonuses), all on the classified ledger.** Layers:

| ID | Requirement |
|---|---|
| REQ-DMG-0001 | `parse_attack_ignores`: the ignore-family phrases → (W, R, effects); damage-scoped only (cost-scoped "ignore" excluded). |
| REQ-DMG-0002 | `build_attack_stats` folds damage / cost / riders / ignore flags into `{attackId: AttackStat}`; tolerates missing text. |
| REQ-DMG-0003 | Overrides beat parsed values field-by-field; unknown attack ids are ignored. |
| REQ-DMG-0004 | Prevention: `prevent_ex_damage` zeroes an ex/Mega attacker's damage unless the attack `ignoresEffects` (Nebula 210 / Jetting 0 vs Crustle). |
| REQ-DMG-0005 | Weakness ×2 / Resistance −30 each pierced by its flag; W-then-R order; damage never negative. |
| REQ-DMG-0006 | Fail-open degradation + per-target semantics: missing stats → printed damage; a prevented Active hit never hides the bench-snipe credit. |

## Provenance — how each override was established (ADR-0108)

`reports/attack_audit/` is gitignored and the capture that produced the shipped table no longer
exists anywhere, so an override used to be *re-derivable* but never *checkable*. That is how 274
(Skeledirge, Torcherto) shipped an exact-looking `atk_hand`/5 fit for an attack that scales on the
combined bench: bench was the one variable the harness neither swept nor recorded, so hand size was
the only thing the fitter could see, and nobody could look.

`common/attack_overrides.provenance.json` is the committed sidecar, emitted by the generator in the
**same pass** as the table so the two cannot describe different derivations. One row per `attackId`:

| method | means | carries |
|---|---|---|
| `engine_fit` | derived from engine measurements | the fitted rows **and the rejected/flat axes** — a flat hand axis is what proves hand size was measured rather than missing |
| `text_verified` | a human read one card's printed sentence | an `owner` (the issue that owes the measurement) + the text and why the harness cannot fit it |
| `unaudited` | shipped before provenance was required; the capture is gone | nothing, and that *is* the claim |

At bootstrap (2026-08-02): **111 `unaudited`, 4 `text_verified`** (Issue #225's scalers, owed by
Issue #275), **2 `engine_fit`** (274 and 371, transcribed from Issue #224's preserved measurements).

| ID | Requirement |
|---|---|
| REQ-PROV-0001 | Table and sidecar cover exactly the same attacks; every row's `method` is in the closed vocabulary. |
| REQ-PROV-0002 | An `engine_fit` row carries the records that establish it — the rejected/flat axes and the modifier-panel points included; a non-fit row carries none. |
| REQ-PROV-0003 | A row's recorded `fields` equal the shipped table entry exactly — the freeze. |
| REQ-PROV-0004 | The unaudited debt may only SHRINK — both the id set and the counts. Backfilling needs no test edit; growing either class fails. |
| REQ-PROV-0005 | A `text_verified` row names the issue that owes its measurement. |
| REQ-PROV-0006 | Table and sidecar are emitted in one pass; a regenerate over an empty measurement set reproduces both byte-for-byte. |
| REQ-PROV-0007 | The generator may retract what it authored (a fit that no longer holds is dropped); never what a human ruled (`--prune` opts in). |
| REQ-PROV-0008 | A fit that CONTRADICTS a `text_verified` ruling is not written: the ruling is kept, both readings are named on stdout, and the run exits non-zero (`--rule` opts in). |

**A contradiction halts; it is not recorded** (REQ-PROV-0008, Issue #355). REQ-PROV-0007's protective
`KEPT`/`--prune` branch sits in `merge_provenance`'s *second* loop, behind `if aid in entries:
continue` — so it could never see an attack the run had derived something for, which is exactly the
case where a ruling is under threat. Measured on two shipped entries: the audit panel's vanilla
defender is a *Mega Pokémon ex* and holds no Energy, so `def_ex_in_play` is collinear with
`def_bench` (425) and `both_active_energy` with `atk_active_energy` (120), and both rulings were
being overwritten with a wrong variable that flows into `state_value`'s `threat`/`survival` terms.
The refused fit leaves **no row in the sidecar**, on the same ruling `_apply_rules` already makes for
a refused coin bound: that file's evidence justifies what SHIPPED, and a measurement that established
nothing belongs on `diff_attack_audit.py`'s gap ledger. The non-zero exit is what makes it impossible
to absorb silently — ADR-0032 records 96.6 % of 9.5 k measurements predicting exactly, so a
disagreement is roughly 1 in 30 and worth a human reading the card again.

**A measured coin bound is board-scoped** (REQ-AUDIT-0014, ADR-0083 Amendment A). `--sweep` leaves
several vanilla `coin="max"` records — one per board — so the fork pairs are grouped by the
**physical** board they were measured on (`sweep`/`step` excluded: they are provenance labels, and
the panel point and the `atk_bench` step-1 point are the same board). One board, or several that
agree, emits the bound (corroboration, per ADR-0083 §3's flat-axis argument); boards that disagree
emit nothing, because the bound is then a function of the board (879 *"flip a coin for each {D}
Pokémon you have in play"*) and the table has no form that says so; and one board answering twice
emits nothing, because a measurement that does not reproduce is not a fact.

A bound also never ships for an attack that **has** a scaler — parser-named or fitted. The bound
REPLACES the base term and the scaling term is added on top, so the pair double-counts the scaling
contribution: an over-prediction, the class `ci_audit_gate.py` fails on. A refused bound leaves no
trace in the provenance sidecar by design — that file records what shipped; a measurement that
established nothing belongs on `diff_attack_audit.py`'s gap ledger.

The sidecar is documentation wearing a `.json` extension — the runtime loads only
`attack_overrides.json` — so `tools/submit/package.py` excludes it from the Kaggle bundle.

Tests: `tests/test_attack_stats.py`, `tests/test_damage_oracle.py`, the behavior goldens in
`tests/test_posture_cardfacts.py`, and — for the provenance tier —
`tests/sim/test_attack_override_provenance.py` together with
`tests/sim/test_generate_attack_overrides.py`. Related: [card-functions.md](card-functions.md)
(the card-level behavioral tags this tier complements).

## REQ-AUDIT — what the attack-measurement harness is required to do

`@pytest.mark.req` markers across `tests/sim/` cite these ids, so they need a home outside the
modules they grade. Owners: `tools/sim/audit_attacks.py` (the harness), `diff_attack_audit.py` (the
oracle diff), `generate_attack_overrides.py` (the emitter). Reasoning: ADR-0032, ADR-0083, ADR-0108.

| id | requirement |
|---|---|
| 0001 | Panel selection from card data: vanilla/weak/resist by the attacker's type (basic, no ability, non-Tera, highest HP); `prevent_ex` = Crustle 345 for ex/megaEx attackers only; an unmatchable scenario yields None, never a guess. |
| 0002 | Side decks are legal 60-card: 4× each chain card + basic-Energy fill mapped from the attack's cost (colorless → a real Energy card). |
| 0003 | Evolution chains resolve basic-first by walking `evolvesFrom` names. |
| 0004 | Dealt damage is extracted from the attack log window (ATTACK → turn boundary): split active/bench/self by serial, KO censoring flagged, coins counted, heals never counted as damage. |
| 0005 | Records carry attackId / attackerCardId / scenario / printed / dealtActive / dealtBench / defenderCardId / attackerEnergies / myHandSize / coin (+ hp, koed, self). |
| 0006 | An unmeasurable attack × scenario is an explicit `{"error": …}` ledger entry — never a silent skip. |
| 0007 | Re-runs merge by record key: a new measurement wins, but an error never clobbers an existing success (accumulative, like `card_functions`). |
| 0008 | Sweep planning varies exactly ONE state variable (attached energy, my hand size via delayed attack, or one seat's bench) across 2–3 points, only when requested. |
| 0009 | Coin fork: fork the pre-attack position via `search_begin(manual_coin=True)`, walk both outcomes of every coin select, record min and max dealt. |
| 0010 | Engine smokes reproduce the known goldens: Resistance −30, Weakness ×2, Nebula Beam 1488 = 210 vs Crustle, Jetting Blow 1487 = 0 active + 50 bench. |
| 0011 | Each successful measurement diffs against the oracle — a coin-fork record against its own bound (min/max), a sweep/panel record with the attacker-side scaling context off the record; match iff equal. |
| 0012 | Error-ledger, live-coin (random outcome, no fork) and unknown-attack records are classified SKIPS — counted, never silently dropped. |
| 0013 | A gap carries ids, scenario, printed/dealt/predicted and a coarse class: `scaler` (printed 0, dealt > 0), `over_prediction` (dealt 0, predicted > 0), else `modifier`. |
| 0014 | Coin bounds come from vanilla-panel fork pairs only — a fork on the weak or resist panel has the modifier baked into the dealt number, so its bounds are not the attack's own. A measured coin bound is board-scoped (ADR-0083 Amendment A). |
| 0015 | A printed-0 attack dealing one CONSTANT across ≥ 2 modifier scenarios yields a fixed effect damage; anything varying does not. |
| 0016 | Sweep points must fit an EXACT integer linear model, or the attack stays on the gap ledger. |
| 0017 | Never emit a field the parser already got right — overrides are DELTAS. |
| 0018 | Per-seat bench counts are CONTROLLED (both seats driven to a target within bench patience) and RECORDED on every measurement. Uncontrolled bench was free to co-vary with the swept variable, which is how a combined-bench scaler shipped an exact-looking `atk_hand` fit (274 Torcherto). |
| 0019 | A scaler's VARIABLE is named by measurement, never guessed: the bench family needs TWO joined single-variable sweeps, because one sweep gives the same slope for an attacker-bench and a combined-bench scaler. A fit may only claim a variable the harness actually controls. |
| 0020 | The DEFENDER's attached Energy is a swept axis — the defender attaches to a per-plan target while the attacker's count stays pinned, and every record carries `defenderEnergies`. Without it `atk_active_energy` and `both_active_energy` are numerically identical at every producible point (Issue #275). |
| 0021 | The defender seat's RULE-BOX composition is controlled and recorded: each defender-bench sweep is PAIRED with a matched non-ex control at the same bench count, and records carry `defenderExInPlay` / `attackerBenchStage2`. The default panel is ex-SATURATED, so without the control `def_ex_in_play` is perfectly collinear with `def_bench` (Issue #275). |
