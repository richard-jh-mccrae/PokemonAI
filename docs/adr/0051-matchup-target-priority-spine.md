# ADR-0051 — Matchup Target Priority is one spine the targeting decisions read

Status: Accepted (Phases 1–3b built 2026-07-12/13)
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
- **Replaces** the ADR-0038 scattered Brief levers. Both the gust lever (`_gust_brief_denial`, Phase 2)
  and the snipe levers (`_BRIEF_PREEVO_SNIPE_BOOST` / `_BRIEF_ENGINE_SNIPE_BOOST` in `_body_threat_rank`
  plus the `brief_preevo` / `brief_engine` kill-switches and their main.py wiring) are now RETIRED
  (Phase 2/3). `matchup_targeting` is the single kill-switch; `opp_is_engine_dependent` is unwired again
  (a Brief hunts an engine via the explicit `disruption_target` role, no property gate).

## Phasing

- **Phase 1 (built): spine + bench-snipe consumption + role-enum expansion.**
- **Phase 2 (built): gust** target selection reads the same plan as a **sub-prize tie-break**
  (`_gust_matchup_priority`, `_MATCHUP_GUST_SCALE`), NOT the ×5 snipe override — gust is primarily
  prize/KO value, so the plan only breaks ties among equal-value KO-able bodies and never overrides a
  prize difference. Only positive priorities apply (a KO-able draw engine is still worth its prize).
  **Retires** the old `_gust_brief_denial` / `_BRIEF_GUST_DENIAL` (ADR-0038); the old engine+dependence
  gate is replaced by the explicit `disruption_target` role (a plain `engine` is now neutral).
- **Phase 3a (built): retired the snipe-side old levers** — `_BRIEF_PREEVO_SNIPE_BOOST` /
  `_BRIEF_ENGINE_SNIPE_BOOST` in `_body_threat_rank`, the `brief_preevo`/`brief_engine` ctor params +
  storage + all four main.py wirings, and the dead `brief_roles`/`engine_dependent` params threaded
  through `_target_threat_rank`/`_strongest_threat_rank`/planner. `_body_threat_rank` is now the pure
  generic (card-fact + Read-modulated) threat order; brief consumption is 100% via the spine.
- **Phase 3b (built): proactive disruption**, two slices.
  - *Hold hand-disruption for the engine's swing turn* — `strip-the-stacked-engine-hand`
    (`baseline_disruption.py`, +22): play a `hand_disruption` Supporter when a `draw`-tagged engine is
    in play (`opp_draw_engine_in_play`), the opponent's hand has stacked to `_STACKED_HAND` (6)+ cards
    (`opp_hand_size`, sound off `handCount`), AND it exceeds mine (`my_hand_size` — the don't-gift-a-
    refresh guard). Below the threshold the rule is silent — that *is* the hold. Scoped to draw-engine
    decks (a hand-size attacker stays the separate `play-harlequin-vs-hand-size` trigger). Only 3 of 18
    `hand_disruption` cards (Judge / Iono / Harlequin) also carry `shuffle_hand`, so for those the
    `hold-wincon-dont-shuffle` guard binds; the other 15 are *one-sided* (strip the opponent only, don't
    touch my hand), where the don't-gift guard is merely conservative — relaxing it for one-sided
    disruption (pure upside) is a follow-up.
  - *Gust-to-KO toward the wincon* — `_gust_wincon_denial` (`doctrine_gust.py`, `_WINCON_DENIAL_PRIZES`
    1.5 × γ): a `fragile_preevo` / `prize_liability` gust target is worth ~1.5 extra effective prizes,
    so the gust drags the 1-prize crib wincon up over a bigger INERT body (a fragile-wincon matchup is
    won by denying the line, not prize count — the user's call). A moderate small-integer-band bump, NOT
    the ×5 snipe override: it sits above a plain prize gap but below the live-threat denial term
    (`_gust_target_denial`, a full prize) and any lethal KO. γ=0 ⇒ silent (prize-first restored).
- Phase 4: build/fetch priors biased by the anticipated opponent.

Open follow-ups: the general tier flags only *direct* `draw`-tag bodies; a draw-engine *pre-evo*
(Dunsparce→Dudunsparce) is disambiguated by the Read/dossier tier, not the general tier. `matchup-genie`
prompt + existing Briefs to adopt `avoid`/`disruption_target` where curated (schema already allows it).
