# Handoff — Complete the Posturing Pipeline: make the Pilot **act** on the Matchup Brief

**Date:** 2026-07-04 · **Branch:** `claude/focused-haslett-ed534d` (worktree; changes uncommitted) · **Suite:** green (1227 passed, 1 skipped)
**Start the next session with `/grill-with-docs`** (see Suggested skills). This doc is the briefing, **not** the plan — the grill produces the plan.

---

## 1. Mission (one sentence)

The Brief **loading → routing → Board-surface** is fully built and **behavior-neutral**; the remaining work is the **consumption layer** — the γ-gated, A/B-measured **Hypotheses (levers)** that read the Board's Brief accessors and actually **change the Pilot's play** when a recognized opponent's Brief is on the Board.

Concretely: today, when our agent faces Lucario, the Brief **is loaded onto `board.brief`** and its threats/targets are resolved to ids — but **no rule scores off it**, so play is unchanged. Close that gap.

---

## 2. What is ALREADY built — do NOT rebuild (reference, don't duplicate)

The standard, data-driven interface is done and reviewed. **Adding a posture = one JSON, zero code.** Full pipeline + assessment: see the review in this conversation; canonical references:

- **Pipeline & routing:** [`docs/scouting.md`](../docs/scouting.md) §"Matchup Briefs (consumer bridge)" and [`docs/adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md`](../docs/adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md). Stages: author `src/common/scouting/briefs/<slug>.json` (self-declares `covers`) → `load_briefs()` globs the dir → agent `main.py` passes `briefs=` into `Pilot` → `match_brief(self.briefs, read)` routes `read.candidates[0]` by `covers` → lands on `Board.brief` (γ-gated).
- **Consumer SURFACE (built last turn, TDD, behavior-neutral):**
  - `Board.opp_property(key, default)`, `Board.brief_target_role(id)`, `Board.brief_is_threat(id)`, `Board.brief_target_ids(role=None)` — [`src/common/pilot.py`](../src/common/pilot.py) (fields `brief_threat_ids`, `brief_target_roles`; resolution wired in `_board()` ~line 1796).
  - `briefs.resolve_brief_cards(brief, ids_for_name)` (name→id, pure) — [`src/common/scouting/briefs.py`](../src/common/scouting/briefs.py).
  - `provider.ids_for_name(name)` + pure `_name_index` on both providers — [`src/common/scouting/provider.py`](../src/common/scouting/provider.py).
  - Tests: [`tests/strategy/test_posture_read.py`](../tests/strategy/test_posture_read.py) (`REQ-POSTURE-0005`, incl. the behavior-neutrality guard `test_resolving_the_brief_changes_no_decision_or_score`), plus `tests/scouting/test_scouting_briefs.py`, `tests/scouting/test_scouting_provider.py`.
- **The shipped Brief (the worked example):** `src/common/scouting/briefs/hariyama_mega_lucario_ex_solrock.json` (covers BOTH Lucario variants) + doctrine `docs/matchups/hariyama_mega_lucario_ex_solrock.md`. It asserts **`opp_tempo: "midrange"` only** (`opp_is_engine_dependent` and `opp_donk_vulnerable` were judged FALSE → omitted; assert-true-only). Threats: Mega Lucario ex, Hariyama. Targets: Riolu + Makuhita (`fragile_preevo`), Mega Lucario ex (`prize_liability`), Solrock + Lunatone (`engine`).
- **The lever registry:** [`.claude/skills/matchup-genie/assets/opponent_properties.json`](../.claude/skills/matchup-genie/assets/opponent_properties.json) — 3 keys, **all `consumer: "unwired"`**, each with a `note` naming the lever it *should* drive:
  - `opp_tempo` (enum fast/midrange/slow) → "race a slow deck; stabilise-then-grind against a fast one."
  - `opp_is_engine_dependent` (bool) → "raise disruption value against its `engine` target."
  - `opp_donk_vulnerable` (bool) → "raise early aggression / prioritise the `fragile_preevo` snipe."

---

## 3. The precedent to mirror (how a Board signal becomes a play-changing lever)

**Two ADR-0026 Read-levers are already shipped and are the exact template** — the grill/build should follow their shape, not invent a new mechanism:

- **Lever A (favorability):** [`src/common/strategy/baseline/baseline_disruption.py`](../src/common/strategy/baseline/baseline_disruption.py) — Hypotheses (`disrupt-when-unfavored`, `dont-gift-a-refresh-when-favored`) read `c.board.favorability` / `c.board.matchup_coverage`, up/down-weight an *already-useful* disruption, **γ-gated, coverage-gated, never override a KO.**
- **Lever C (accurate-dev / snipe rank):** `Pilot._target_threat_rank` reads the Read's `evolution_paths` → modulates the bench-snipe threat rank, **γ-scaled by `board.posture_confidence`.** Tests in `test_posture_read.py` (`REQ-POSTURE-0003/0004/0006`).

**Shape of every new Brief lever:** a `Hypothesis(id=…, when=lambda c: … c.board.<brief accessor> …, weight=…, status="testing")`, γ-scaled, weight-bounded (positional nudge, **never** overrides a KO), behind a **kill-switch param**, **A/B'd** before default-ON.

---

## 4. Design questions the grill MUST resolve (the meat — this is why `/grill-with-docs`)

1. **Per-property new levers vs. *sharpening* existing generic levers.** The highest-leverage insight: the Brief's threats/targets may not need net-new Hypotheses — they may feed intel into levers that already exist.
   - `fragile_preevo` target → a new "snipe-the-briefed-preevo" rule, **or** feed the exact preevo id into the existing snipe threat rank (Lever C machinery: `Board.strongest_threat_rank` / `_target_threat_rank`)? (Lean: sharpen the existing generic forward-evo snipe with the Brief's exact target.)
   - `engine` target + `opp_is_engine_dependent` → this is the **engine-removal lever ADR-0026 explicitly declined to make generic and ADR-0027 says "lives here."** Gust+KO the engine — but **gate on `opp_is_engine_dependent == True`** (for Lucario it is FALSE → the lever must NOT fire; disruption is a tempo hit, not a kill). See `docs/matchups/hariyama_mega_lucario_ex_solrock.md` §Seam 5.
   - `prize_liability` target → deny-prizes / force-Active / prioritize-KO; reconcile with existing promote/interpose logic (memory: `interpose-cheap-attacker-promote`).
   - `opp_tempo` → race vs stabilize aggression modulation. **Reconcile with Lever A (favorability)** — both are "how aggressive should I be" signals; the grill must prevent double-counting.
2. **General vs deck placement** (the expand-vs-override rule; [ADR-0034](../docs/adr/0034-deck-strategy-folds-into-general-when-covered.md), memory `fold-policy-deck-rules-general`). Briefs are **objective/shared** → levers default to the **general** layer; each agent **relativizes** (e.g. mega_starmie's Psychic attacker OHKOs the Lucario line — deck-specific value). Which levers are general Hypotheses vs deck Hypotheses?
3. **Weakness is ALREADY handled — don't re-invent it.** The lethal/KO oracle already applies weakness ×2 (`docs/rules.md` damage-calc order), so "OHKO the Psychic-weak Mega" is covered by the generic lethal machinery. The Brief levers cover the **gameplan** (snipe preevo / disrupt engine / tempo / prize denial), **not** weakness. Confirm this in the grill so the plan doesn't duplicate combat math.
4. **Invariants to hold:** γ-scale every lever by `board.posture_confidence`; **never override a KO** (memories `forgo-ko-corrections-are-refuted`, `attack-is-turn-ender-develop-first`); each lever behind a kill-switch param, A/B-measured, default-ON only after it clears.

---

## 5. Build & measurement discipline (once the plan is locked)

- **Kill-switch per lever**, threaded from `Strategy.params` in each agent's `main.py` (mirror `lethal_verify` / `planner_*` in [`src/agents/mega_starmie/main.py`](../src/agents/mega_starmie/main.py)). ⚠️ **`src/agents/mega_lucario/main.py` is missing the existing kill-switches** (memory `new-deck-wiring-and-general-gaps`) — when you add new params, wire them into **all** agents or they silently default OFF.
- **A/B via `battle.py`** (~1000 games/min; recipe in memory `wiring-pass-built`). Behavior-neutral wire → A/B → default-ON. This is the completion gate for each lever.
- **Test each lever** test-first (mirror `test_posture_read.py`): fires when recognized + trigger met; stands down when unrecognized / γ=0 / trigger absent; never overrides a KO.

---

## 6. Adjacent hardening (flagged in the review; OPTIONAL, not the core mission)

Decide in the grill whether to fold these in or defer:
1. **Silent `covers`-collision** — `match_brief` returns the alphabetically-first covering Brief; `validate_brief.py` checks a Brief's own cards but not cross-Brief `covers` overlap. Add a guard once the dir has many files.
2. **`briefs=` footgun** — a new agent's `main.py` must pass `briefs=_briefs` or it silently gets **zero** postures (default `None→[]`). Add a test asserting every agent wires briefs.
3. **Doc drift** — `docs/scouting.md` §"Matchup Briefs" predates the consumer surface (lists only `load_briefs`/`match_brief`; "nothing scores off it yet" now means "no Hypothesis," since the accessors + `resolve_brief_cards` now exist). Refresh when the consumption layer lands.

---

## 7. Key memories (auto-loaded; the load-bearing ones for this work)

`m2-posture-plan` (the staircase + ADR-0026/0027 split) · `wiring-pass-built` (battle.py A/B recipe, kill-switch pattern) · `matchup-brief-first-shipped` (the surface just built + the two gotchas) · `card-fact-posture` (what "posture" already ships via card facts) · `fold-policy-deck-rules-general` (expand-vs-override) · `forgo-ko-corrections-are-refuted` + `attack-is-turn-ender-develop-first` (never let a positional lever beat a KO) · `interpose-cheap-attacker-promote` (prize-denial precedent) · `new-deck-wiring-and-general-gaps` (the main.py kill-switch footgun).

---

## 8. Suggested skills (in order)

1. **`/grill-with-docs`** — PRIMARY. Design the consumption levers against the domain model (Read / Posture / Brief / Hypothesis / lever / γ), sharpen terminology, and author the governing ADR — likely a **new ADR "Brief consumption is γ-gated Hypotheses"** (or an extension of ADR-0027 / ADR-0026). It updates `CONTEXT.md` + ADRs inline as decisions crystallize. Feed it this doc.
2. **`/tdd`** — build each lever test-first once the plan is locked (Hypothesis trigger + neutrality-until-γ + fires-when-recognized), mirroring `test_posture_read.py`. Then A/B via `battle.py`.
3. **`/deck-align`** (later) — relativize the general Brief levers per existing deck where the expand-vs-override rule says a deck should specialize (e.g. mega_starmie's Psychic-OHKO value vs Lucario).

**Not** `/matchup-genie` (Briefs are authored; the Lucario one is shipped) and **not** `/blunder-buster` (this is architecture, not correction-driven tuning).
