# ADR-0051 — Matchup Target Priority is one spine the targeting decisions read

Status: Accepted (Phase 1 built 2026-07-12)
Related: ADR-0026 (the Read / γ), ADR-0027 (Matchup Briefs), ADR-0038 (γ-gated Brief levers — superseded here), ADR-0044 (opponent-choice snipe reads), ADR-0047 (Opponent Model facade)

## Context

Recognition works — the Scout produces a confident Read (γ→1 as cards reveal) and `/matchup-genie`
authors correct Briefs. But the Pilot *consumed* that knowledge as a faint tie-break: the Brief
`fragile_preevo` role flipped one +30 positional rung, `engine` was kill-switched off, and
`prize_liability` had **no consumer at all**. Meanwhile the generic fallback threat model inverts on
real boards — `forward_max_damage` is name-keyed, so a phantom `Dudunsparce ex` (150) inflated a draw
engine's line while a hand-size wincon (Alakazam, printed 0) read as harmless. Net effect the user
observed on mega_starmie: the agent sniped draw engines over win-condition lines. The knowledge was
present; it simply did not bind the target pick.

## Decision

Introduce **one spine — `MatchupPlan`** (`src/common/scouting/matchup_plan.py`) that assigns every
opponent body a single `(role, priority)`, and make the targeting decisions read it as a **strong,
γ-scaled positional signal that sits below KO/lethal and is silent at γ=0**.

### Composition — three tiers, most-general first, most-specific wins per body

| Tier | Source | γ-scaled? |
|---|---|---|
| general card-fact | the `draw` Function Tag → `avoid` (a draw ENGINE — Dudunsparce/Budew class — is a poor target in *every* deck) | no — a card fact, applies even unrecognized |
| Read-Intel | `Read.targets` Intel (observed roles always; dossier-predicted once confident) | yes |
| curated Brief | `/matchup-genie` `targets` roles, resolved to ids | yes |

The Pilot resolves the raw inputs (`self.functions` → draw-engine ids, `resolve_brief_cards` → Brief
roles, `Read.targets` → Intel roles); the plan is a pure composition + scale.

### Role → priority seed (`_ROLE_PRIORITY`, ladder-tunable)

`prize_liability` 100 · `fragile_preevo` 90 · `disruption_target` 60 · `engine` 0 (neutral — a plain
accelerant is a poor target; `disruption_target` is the *explicit* "hunt an engine" role) · `avoid` −80.
Magnitudes sit above the positional snipe rungs (Σ≲150) but below `KO_SCORE` (1000): scaled into the
tactical band by `_MATCHUP_PRIORITY_SCALE` (×5) at the consumer.

### Vocabulary expansion

`brief.schema.json` role enum gains **`avoid`** (matchup-specific decoy) and **`disruption_target`**
(their key supporter/enabler to remove). Generic draw engines are NOT authored per-Brief — the general
`draw`-tag tier covers them matchup-agnostically (Dudunsparce is an Engine Pokémon across many decks;
CONTEXT.md glossary).

### Consumption (Phase 1: bench snipe)

`Pilot._snipe_matchup_tactical` adds `matchup_plan.priority(target) × 5` to a bench-DAMAGE option's
tactical score. Guards, in order:
- stands down when a **snipe-KO is available** (`board.snipe_ko_available`) — defer to the KO logic, exactly as the positional rungs do, so a free prize always wins;
- a **positive** boost stands down on an ADR-0044 `target_prize_redundant` / `target_promotion_mirage` body — don't chip a body I mean to gust around / that isn't who they promote (test_107). The positional `snipe-the-evolving-threat` rung still fires on a genuine on-path pre-evo, so the wincon line is not abandoned;
- a **negative** (`avoid`) priority always applies — de-prioritizing a draw engine is safe regardless.

### Kill-switch + anti-regression

`Pilot(matchup_targeting=True)` (default ON, ship-and-refine). Off → an empty plan (every priority 0),
byte-identical. γ=0 ⇒ the matchup tiers contribute nothing (neutral/unrecognized matchups untouched by
construction — invariant test); only the general card-fact tier remains. Validated by ladder + user
feedback, not gauntlet A/B.

## Consequences

- The three flagged mega_starmie blunders stay fixed; the draw-engine-over-wincon inversion is now
  overridden by recognition rather than relying on the generic (still name-keyed) `forward_max_damage`.
- **Supersedes** the ADR-0038 scattered Brief levers (`_BRIEF_PREEVO_SNIPE_BOOST` in `_body_threat_rank`,
  `_gust_brief_denial`). Those remain in place, harmless (same direction), until retired in the review
  pass — the `brief_preevo` end-to-end test now toggles `matchup_targeting`.

## Phasing

- **Phase 1 (built): spine + bench-snipe consumption + role-enum expansion.** ← this ADR
- Phase 2 (next): **gust** target selection reads the same plan (as a sub-prize tie-break, NOT the ×5
  snipe override — gust is primarily prize/KO value); then retire the old scattered levers.
- Phase 3: proactive disruption (hold hand-disruption for the engine's swing turn; gust-to-KO priority).
- Phase 4: build/fetch priors biased by the anticipated opponent.

Open follow-ups: the general tier flags only *direct* `draw`-tag bodies; a draw-engine *pre-evo*
(Dunsparce→Dudunsparce) is disambiguated by the Read/dossier tier, not the general tier. `matchup-genie`
prompt + existing Briefs to adopt `avoid`/`disruption_target` where curated (schema already allows it).
