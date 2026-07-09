<!-- Strategy Proposal — the FETCH-seam prize-economy term, grilled 2026-07-09 (/grill-with-docs on
data/handoffs/pokemonai-handoff-prize-economy-aware-fetch.md). Full design + rationale: ADR-0048.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## prize-economy-fetch
- id: prize-economy-fetch
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: forward-payoff prize value (`_forward_card_ids` + `_prize_value`); NEW `card_is_recognized_line_preevo` Context field + `_recognized_line_preevo_set()`; role-gated `_wincon_set()`; `board.wincon_in_play`; secondary `Line(role="secondary_attacker")` deck data
- verification_contract: seed-ladder
- provenance: data/handoffs/pokemonai-handoff-prize-economy-aware-fetch.md ; docs/adr/0048-prize-economy-fetch-broadens-the-line-concept.md ; data/strategy/proposals/learnthetcg-fundamentals.md#prize-value-board-shaping (its FETCH-seam gap) ; corrections ml_dont_fetch_redundant_solrock_f12 / _inert_f26 (deck-rule halves this subsumes)
- status: open

**Spec (authoring spec — thin fodder; full rationale + considered-options in ADR-0048):**

Make the FETCH grab prize-economy-aware: once my multi-prize win-condition is in play, prefer
developing a **cheap 1-prize attacker line** over a redundant high-prize line, so the opponent must
KO MORE, SMALLER bodies to reach six (force an 8-prizes-of-work path for a 6-prize game). The
FETCH-seam mirror of the promote-seam Interpose trio + the bench-seam `_bench_shortens_their_path`.

WHAT the term must do (a small **positive** tie-break in `doctrine_fetch.py`):
- Score a grab candidate by its **forward-payoff prize value** — the prize value of what the
  pre-evolution evolves INTO (`_forward_card_ids` → `_prize_value`; Riolu→Mega = 3, Makuhita→Hariyama
  = 1), max over {card} ∪ forward descendants. **NOT** the card's own `card_prize_value` (the
  handoff named that primitive, but it FAILS the motivating case — Riolu vs Makuhita are both
  1-prize pre-evos; `card_prize_value` can't tell them apart).
- Fire only when `board.wincon_in_play` (the multi-prize payoff is on board) and the candidate is a
  recognized **attacker** line pre-evo — prefer the cheaper-forward one. Below every real need
  (energy-starved +35 / fetch-wincon +30 / missing-piece +20 / engine +15) so it never starves the
  plan; the wincon LINE is still developed first while offline (its pre-evo keeps its line-piece credit).

WHY the +18 gap must be closed by **broadening line recognition** (chosen over gating the existing
rung or a competing +18 weight — see ADR-0048): today `prefer-wincon-line-piece` (+18) credits only
the declared win-condition Line's pre-evo (Riolu), not the secondary attacker (Makuhita, `evolution_base`),
so the cheap line loses by ~+18 and a small tie-break can't flip it. Broadening equalizes them to +18,
then the prize-economy tie-break tips it.

CONTAINMENT — the authoring MUST honor these or it silently corrupts load-bearing signals:
- Declare the cheap line as a **non-wincon** `Line(path=[MAKUHITA, HARIYAMA], payoff=HARIYAMA,
  role="secondary_attacker")` in `agents/mega_lucario/strategy.py`.
- **Keep `_line_preevo_set()` NARROW** (win-condition lines only) — it feeds `wincon_base_deployable`,
  `_evolve_to_ready_wincon_available`, `_wincon_in_hand_undeployable`. Broadening it globally makes a
  benched Makuhita read the *win-condition* as base-deployable → breaks
  `dont-fetch-an-unplayable-evolution-payoff` / `fetch-base-before-stranded-payoff` / hold-wincon.
- Add a SEPARATE `_recognized_line_preevo_set()` (all declared lines) + `card_is_recognized_line_preevo`,
  read only by the preference rungs (broaden `prefer-wincon-line-piece` → recognized attacker lines) and
  the new tie-break.
- **Role-gate `_wincon_set()`** (count only wincon-role lines) so the secondary Line's payoff (Hariyama)
  is not mislabeled a win-condition. Behavior-neutral for every existing deck (all declare only
  `win_condition` lines) — prove via Score-Diff.
- **Attacker-lines only**: engine lines (Dunsparce→Dudunsparce) are excluded — their dev sequencing
  stays with the engine rungs + `fetch_priority` (deck/board-dependent, the user's explicit flexibility ask).

FLEXIBILITY: dominated by needs (small weight), gated on board state (`wincon_in_play`), deck-overridable
via `fetch_priority` (+40) / `weight_overrides` (ADR-0035). No rigid deck constant.

VERIFY (seed-ladder + neutrality side-checks): ship `assumed`, **default-on, kill-switched**,
blunder-buster telemetry. Score-Diff **neutral across all decks** for the role-gate + containment (only
solrock's grabs may change, and only in the intended cheap-vs-redundant case); the **7 solrock fixtures
still land**; ladder-validate ([[gauntlet-invalid-ladder-only]] — the gauntlet is invalid-for-gain).

FOLD: lets solrock's `dont-fetch-the-redundant-piece` **Riolu-half** fold (deck-align) — the general
term now covers the redundant-wincon-base case, incl. "Mega online, no benched Riolu, 2nd Riolu vs
Makuhita" which the deck rule's `card_is_redundant` gate misses. Its **engine-half** (one-of-each
functional redundancy) is NOT prize economy — leave it.
