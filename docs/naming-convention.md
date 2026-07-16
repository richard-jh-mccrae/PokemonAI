# Naming Convention — the one map (PROPOSAL, not yet applied)

> **STATUS: PROPOSAL under grill.** This is the agreed-naming artifact we are locking BEFORE the
> repo-wide rewrite. Nothing outside this file has been renamed yet. Once locked, the "rewrite
> everything" pass (user-chosen scope) retrofits every doc + code label to match.

## Why this exists

The project grew several label families that all draw from the same tiny pool of indices — `2` alone
meant Tier 2, Session 2, Work Package 2, Milestone 2, Phase 2, Contract 2. And the word *tier* was
reused in code for an unrelated ladder. This doc makes **one unified map**: the runtime architecture
is the spine, and every ML/build item is shown **where it fits on that spine, spelled out, with a
status tag** — no acronyms to decode.

---

## Rule 1 — "Tier" means a runtime decision layer, nothing else

A **Tier** is a layer that makes an *in-match decision*. Notation: `T<n>` and dotted sub-tiers
`T<n>.<m>`. Written out, a reference always expands the names:
`T4 - Opponent Model` · `T4.2 - Opponent Model, Posture`.

The word "tier" is **reserved** for these. Two former abusers are renamed (Rule 5).

## Rule 2 — Every tier/sub-tier carries a status tag

Mandatory on anything not shipped-and-on. Vocabulary:

| Tag | Meaning |
|---|---|
| `built` | shipped, default-ON (the live agent) |
| `built (N%)` | shipped + ON but the tier doc marks remaining work |
| `built, gated:off` | code exists, kill-switched OFF (flips at a named Gate) |
| `grilled, unbuilt` | design locked, not yet built |
| `scoped, unbuilt` | scope written, not yet grilled |
| `unbuilt` | planned; no design (research-only if noted) |

A sub-tier that would exist once an ML feature ships is written with its target number **and** the
tag, e.g. `T4.4 - Opponent Model, Learned Matchup Weights — grilled, unbuilt`.

## Rule 3 — Spell out the build scaffolding (no acronyms)

The build/project axis is **written in words**, never hidden behind `WP`/`S`/`G`:

| Old acronym | Spelled-out form |
|---|---|
| WP1 … WP6 | **Work Package 1 … 6** (name it: "Work Package 1 (Value Net)") |
| S1, S2a, S3b-1 | **Build Session 1 / 2a / 3b-1** |
| G1 | **Value-Net Gate** |
| G2 | **Adoption Gate** |
| P2a (session alias) | *deleted* — sessions are only "Build Session …" |
| M0 … M4 | **retired** — these were superseded milestones; the rewrite converts each to its tier reference + "(historical milestone)" |

ADR-`<n>` stays (it is a filename-backed identifier, already unambiguous).

## Rule 4 — ML work is placed on the tier map where it runs

- **Runs in-match ⇒ gets a tier slot + status.** The value net *is* `T5`; learned matchup weights
  *are* `T4.4`; a future value-net-backed search *would be* a `T6.x`.
- **Offline factory ⇒ shown as the tier's trainer, spelled out, no tier number.** The blunder
  labeler, eval harness, expert-iteration tuner mechanics, and league never pick an in-match move —
  they build/tune/measure the tiers. They appear as "trained/evaluated by: …" attached to the tier
  they serve.

## Rule 5 — Renames + the always-prefix rule

- Never write a **bare index** — always the prefix (`T2`, `Work Package 2`), never a lone "2".
- `pilot.py` lowercase `tier 0..4` (within-turn play order, free-dev→attack-last) → **`sequence band 0..4`**.
- Deck `STRATEGY.md` prime notation `T2'…T9'` (per-deck build tasks) → **`B2…B9` (build step)**.

---

## The one map

Runtime spine (default-ON agent = T0–T4), with ML/build items placed where they run and tagged:

| Tier | Sub-tiers | Status | Built / trained by |
|---|---|---|---|
| **T0 - Rules & Tuned Scoring** | *(flat)* | `built (90%)` | weights retuned offline by the **expert-iteration tuner** (Work Package 4) |
| **T1 - Turn Planner** (the Goal Ladder, rungs top-down) | **T1.1** Win Rung (Lethal Solver — sound/locking) · **T1.2** KO the Key Threat · **T1.3** KO for Prizes · **T1.4** Stabilize-then-KO · **T1.5** Develop | `built (88%)` | hand-built; the T2 Gamble family joins as a candidate rung below T1.1; leaf-eval seam consumes T5 |
| **T2 - Chance & EV** | *(flat)* | `built (70%)` | hand-built (closed-form expectimax) |
| **T3 - Match Objectives** | **T3.1** Prize Path (+ Denial) · **T3.2** KO Race · **T3.3** Derived Phases | `built (75%)` | hand-built |
| **T4 - Opponent Model** | **T4.1** Read · **T4.2** Posture · **T4.3** Matchup Briefs · **T4.4** Learned Matchup Weights | T4.1–3 `built (70%)`; **T4.4 `grilled, unbuilt`** (flips at Adoption Gate) | T4.4 built by the **expert-iteration tuner** (Work Package 4 / Build Session 3b-2) |
| **T5 - Automatic Value Model** | *(flat)* | `built, gated:off` → flips at **Adoption Gate**; being rebuilt → `grilled, unbuilt` (v2) | the **value net** (Work Package 1 / Build Session 2a), trained on the self-play corpus |
| **T6 - Escalation Search** | **T6.1** current two-ply search · *(**T6.2** sampled-belief search — `unbuilt`, research)* | T6.1 `built, gated:off`; T6.2 `unbuilt` | T6.2 would consume T5's value net |

**Offline factory (no tier number — these never make an in-match move):** the **eval harness**
(Work Package 2) measures every tier; the **blunder labeler** (Work Package 3) produces the
corrections that tune T0; the **league / exploiter probe** (Work Package 5) hardens every tier.
These are the "trained/evaluated by" entries above, not tiers.

---

## Locked decisions (this grill)

1. **T1 granularity** = each Goal-Ladder rung numbered (T1.1–T1.5, top-down).
2. **Offline-only ML tools carry no tier number** (Rule 4) — shown as each tier's trainer, spelled out.
3. Notation = dotted `T<n>.<m>`; renames = `sequence band` + `B<n> build step`; build scaffolding
   spelled out (no `WP/S/G`); status tags mandatory; historical docs get the full rewrite.

## Rewrite scope (the apply phase, after this locks)

"Rewrite everything" touches, at minimum: `docs/architecture/tiers.md` + the seven `tier-*.md`;
`docs/plans/ml/*` (acronyms → spelled-out); `docs/adr/*` cross-refs; the superseded
`roadmap-search-posture-learning.md` + `audit-remediation.md` (M/WP histories → tier refs +
"(historical)"); code comments in `pilot.py` (sequence band) + deck `STRATEGY.md` (B-steps). Done as
its own commit/PR after sign-off.
