# Tier 4 — Opponent Model (Read · Posture · Briefs)

**Status: ~50% complete** (2026-07-05). The γ-gated overlay that lets match objectives see the
opponent that *isn't on board yet* — "avoid the second Mega Lucario" is decided before that Lucario
exists.
**Upstream:** Scout (revealed-card evidence → Read), shipped artifact (dossiers), Matchup Briefs.
**Downstream:** T3's their-side (predicted bodies/attackers into Prize Path + KO Race), M2 levers
(favorability → phase/weight bands; accurate-dev on forward-evo), deck Hypotheses via Board
opponent-property fields.

## Final design (ADR-0026/0027 + this grilling's extension)

- **Two layers, γ-gated** (γ = Read confidence): a **visible-board floor** (what their current
  board provably threatens — Incoming-class epistemics, always on) plus a **predicted overlay**
  (the dossier's expected attackers/evolution paths and the Brief's authored corrections), weighted
  by γ. Unknown opponent → γ→0 → floor only → structurally no regression.
- **Net-new in the final architecture**: the overlay feeds **T3's their-side** — predicted
  not-yet-benched bodies join their Prize-Path body set and KO-Race attacker set (γ-weighted
  feasibility), so denial and path choice act *before* the threat lands.
- **M2 levers stand**: **A** favorability (coverage-gated aggression↔disruption band — now also an
  input to T3's phase derivation) and **C** accurate development (γ-gated modulator on the
  forward-evo snipe signal).
- **Matchup Briefs** (ADR-0027): hand-authored objective counterplay per archetype, `covers:`-routed
  variants, produced by `/matchup-genie`, walked down the meta ranking at user cadence; the
  un-Brief'd tail gets the generic core alone.

## Built (the 50%)

Scouting runtime (`scout.py`/`read.py`/`scorer.py`/`matchup.py`); **artifact compiled + committed**
(`src/common/scouting/artifact.json`) and **wired in `main.py`** (Scout instantiated with provider —
M2.0 done); Briefs loader + first Brief shipped (Mega Lucario ex / Solrock, both variants);
**Brief consumption v1** (ADR-0038: Brief facts sharpen the owning Tactical signal — `brief_preevo`
default ON; `brief_engine` wired, arms via the first true-asserting Brief's A/B); card-fact Posture
(prevent_ex_damage, hand-size attacker, defensive forward-doom); M0 forward-evo threat signal
(ADR-0020); IS_FIRST go-second election (`baseline_opening.py` — the old roadmap decision-log gap
is FIXED); meta tracker + deck export feeding `/matchup-genie`.

## Gap to final (the 50%)

1. **M2.1a** — Scout merges dossier `threats`/`targets` into the Read (predicted layer complete,
   zero decisions change).
2. **M2.1b levers A + C** (first behavior change; M1 A/B-gated: recognized ≥ off, unknown = no
   regression).
3. **The T3 overlay** (net-new): γ-weighted predicted bodies into Prize Path/KO Race their-side;
   Brief fields (e.g. engine-removal priorities) as path-feasibility corrections.
4. **Brief coverage** — walk the meta head (~8 core strategies) via `/matchup-genie`.
5. Favorability → phase-derivation input (with T3).

## Acceptance

γ→0 non-regression is structural (fixtures: unknown opponent ⇒ identical decisions); recognized-
opponent A/B ≥ off; overlay fixtures (predicted 2nd Mega shifts the chosen path/denial before it is
benched); trace prints the Read + which overlay facts moved the objective.
