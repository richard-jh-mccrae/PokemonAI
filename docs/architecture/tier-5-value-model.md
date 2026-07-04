# Tier 5 — Value Model

**Status: ~5% complete** (2026-07-05). The single learned seam (ADR-0007), re-scoped by this
grilling: its **features are the T3/T4 primitives**, not raw board encodings. Built **last** — its
inputs are the other tiers' outputs; building it earlier starves it.
**Upstream:** mined replays + self-play corpus (labelled states); T3/T4 primitives as features.
**Downstream:** leaf-eval wherever a leaf is valued — T1 line ranking, T2 branch valuation,
prize-path tiebreaks; Score-layer tiebreaker.

## Final design

- **One supervised model**, LightGBM-class, `state → P(win)`; label = eventual winner. This is NOT
  the rejected "brute-force W/L training": config-level W/L assigns one noisy bit per agent;
  state-level supervision assigns it to thousands of states per match and the noise averages into
  calibrated probability. W/L is a fine *label for states* even though it is a poor *teacher of
  rules*.
- **Features = objective primitives** (the ADR-0007 "feature encoding is the highest-leverage
  surface" question, resolved by architecture): both Prize-Path feasibilities, KO-Race
  turns-ahead/behind, Path-Denial margin, favorability + γ, development, hand/energy/prize counts.
  The symbolic tiers do the credit assignment a raw-board model would have to learn from scratch —
  less data needed, and the fitted weights stay narratable ("race deficit dominates").
- **Consumption rules**: refines *judgment* only — ranks within/between heuristic goals, values
  gamble branches, breaks path ties. **Never overrides sound rungs** (a miscalibrated model
  vetoing a proven Lethal is the self-inflicted loss the sound layer exists to prevent). Closed-form
  leaf stays the fallback when the model is absent; inference is trees — trivially inside budget.
- Build order general → matchup-conditioned → per-deck, as data volume justifies (ADR-0007).

## Built (the 5%)

Data-engine beginnings: self-play corpus with per-frame agent `obs`
(`tools/sim/selfplay.py`, ADR-0022); Battle Results store (`data/battles.jsonl`); replay
mining/meta pipeline; correction featurize path in the tuner (a feature-extraction precedent, not
the trainer).

## Gap to final (the 95%)

1. **Labelled-state extractor** — replays + self-play → `(state features, winner)` rows; seat/deck
   metadata for the conditioned tiers.
2. **Feature builder** — the T3/T4 primitive vector (blocked on T3; the reason this tier is last).
3. **Trainer** (`tools/train/value/`) + calibration report; **loader** (`src/common/value/`), load
   once at import.
4. Leaf seams in T1/T2 + fallback wiring; A/B value-on vs heuristic-only.

## Acceptance

Calibration on held-out replays; M1 A/B value-on ≥ heuristic-only; inference within per-move
budget; clean fallback with the model file absent; sound-rung immunity fixtures.
