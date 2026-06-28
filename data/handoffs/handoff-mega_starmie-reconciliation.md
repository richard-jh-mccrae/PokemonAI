# Handoff — continue grilling: mega_starmie STRATEGY.md reconciliation

**Date:** 2026-06-28 · **Repo:** `C:\Users\Richard\Projects\PokemonAI` · **Branch:** `main` (HEAD `577f603`)

## What the next session is picking up

A `grill-with-docs` session reconciling [src/agents/mega_starmie/STRATEGY.md](../../../../../Projects/PokemonAI/src/agents/mega_starmie/STRATEGY.md)
(the deck's playing doctrine, authored earlier by the `deck-genie` skill) against two recent commits:
`577f603` (the **forward-evolution index** general strategy, ADR-0020) and the **blunder round** in
it + `05222ec`. The reconciliation is **partially done**; resume by grilling the OPEN items.

**The single source of truth for status is [STRATEGY.md §9](../../../../../Projects/PokemonAI/src/agents/mega_starmie/STRATEGY.md)**
("Reconciliation log + open items") — read it first. Don't duplicate it here; the open items live there.

## Orientation the doc doesn't give you

- **Why so much was already covered:** several new General-Strategy hypotheses in
  `src/common/general_strategy.py` were authored straight off **mega_starmie blunders** (rationales
  name Cinderace/Staryu/Mega Starmie). So the deck's former "deferred/draft" items mostly became
  *covered-by-general*. Read the current `general_strategy.py` in full before grilling.
- **New Pilot Context fields now exist** (were the doc's "needed infra"): `bench_wincon_ready`,
  `wincon_in_hand`, `line_preevo_in_play`, `active_is_wincon`, `card_is_wincon`, `card_is_line_preevo`,
  `attach_target_needs`, `target_forward_damage` — see `src/common/pilot.py`. Provider primitive
  `forward_max_damage` is in `src/common/scouting/provider.py` (ADR-0020).
- **`build-before-attack` / `dont-chip-with-a-doomed-active` were REMOVED** — "attack last" is now
  structural in the Pilot (`_finish_turn_last`), not a weight. §9 open-item #3 flags the doc wording fix.
- **Hard rule (project CLAUDE.md):** never recall card facts/rules from memory — verify at
  `data/EN_Card_Data.csv`, the engine (`dump_deck.py`), `docs/rules.md`, `docs/rulebook.txt`. One
  pending verify: "Tools transfer on evolution" (assumed standard; confirm in `rulebook.txt`).
- **Comms conventions:** caveman-lite chat by default; end every reply with a status line. While
  `grill-with-docs` is active use its status lines (`Done - Still grilling`, etc.) per `~/.claude/CLAUDE.md`.

## Uncommitted working-tree changes from this session (review before committing)

- `src/agents/mega_starmie/STRATEGY.md` — extensive reconciliation edits + new **§9**.
- `.claude/skills/deck-genie/` — skill improvements made mid-session: `scripts/dump_deck.py` now
  surfaces **`[ACE SPEC]`**; `SKILL.md` (mechanics-first + research legality-check); `references/grilling-playbook.md` (finite-resource + ACE SPEC notes).

## Background workflow outputs (already synthesized into the doc — raw available if needed)

- Archetype research → STRATEGY.md §2. ACE SPEC / Hero's Cape design → §3 + §9. Raw result of the
  ACE SPEC run: `...\tasks\w796k3n7z.output` (this session's `\tasks\` dir). Key verdict already in
  the doc: **no standalone general ace-spec rule** — WHERE = `save-tool-for-the-attacker`, WHEN =
  HP-breakpoint model (general, not-built), scarcity = optional `aceSpec` weight bump.

## Where to start (grill these, in roughly this order)

1. **§9 open-item #2** — `never-fetch-cinderace` (deck) vs general `prefer-wincon-line-piece`: keep the
   hard deck rule or rely on the soft preference? (Cinderace can ONLY enter via Explosiveness at game
   start → fetching it is strictly dead, not just lower-priority.)
2. **§9 open-item #3** — apply the structural folds to the doc (attack-last, gating refinements, the
   new promote rules covering promote-after-KO with Cinderace as the staller).
3. **§9 open-item #1** — confirm the two real residual deck hypotheses (`conserve-ignition-prefer-water`,
   `prefer-going-second`); these are the Phase-B authoring targets.
4. Then the user wants two **general** efforts (separate, after reconciliation): a comprehensive
   **Boss's Orders** strategy and the **HP-breakpoint model** (+ per-tool-aware `save-tool-for-the-attacker`).

## Suggested skills

- **`/grill-with-docs`** — to continue this reconciliation grill (one decision at a time, recommend-then-confirm, update the doc inline).
- **`/deck-genie mega_starmie`** — when ready to author the gated executable `strategy.py` (Phase B) from the locked doctrine.
- **`/blunder-buster`** — if a further round of corrections needs busting into hypotheses (the blunder→hypothesis path this reconciliation is downstream of).
- **`/verify`** or a quick engine/rulebook check — for the open "Tools transfer on evolution" fact and any new card-mechanics claims.
