# Prize-economy fetch broadens the Line concept behind a role-gated win-condition set

**Status.** Accepted (grilled 2026-07-10) and BUILT — `prize_economy_fetch` is `PROFILE=True` (default
ON, kill-switched), verified Score-Diff-neutral across decks and shipped ladder-refine rather than
A/B-gated.

The fetch grab comparator (ADR-0023) should prefer developing a cheap **1-prize attacker
layer** over a redundant **high-prize** body once the win-condition is online — forcing the
opponent onto an eight-prizes-of-work path for a six-prize game (odd-prizing; the FETCH-seam
mirror of the promote-seam Interpose trio and the bench-seam `_bench_shortens_their_path`). The
motivating case is base-vs-base — Riolu vs Makuhita, **both 1-prize** — so the card's own
`card_prize_value` cannot distinguish them, and `prefer-wincon-line-piece` (+18) credits only the
declared win-condition Line's pre-evolution, leaving the secondary attacker uncredited.

**Decision.** (1) Recognize a deck's cheap-attacker line as a first-class **non-win-condition
`Line`** (`role="secondary_attacker"`). (2) Score a grab by its **forward-payoff prize value**
(`_forward_card_ids` + `_prize_value`: Riolu→Mega = 3, Makuhita→Hariyama = 1), not the card's own
prize value. (3) Add a small, **positive**, `wincon_in_play`-gated fetch tie-break
(`develop-the-cheap-prize-wall-line`) that, among recognized **attacker** lines, prefers the
cheaper-forward one once the multi-prize win-condition is in play.

**Containment (why this is safe).** The win-condition pre-evo set (`_line_preevo_set`) is
load-bearing — it feeds `wincon_base_deployable`, `_evolve_to_ready_wincon_available` and the
hold/undeployable machinery — so it stays **narrow** (win-condition lines only). A **separate**
recognized-line set (`_recognized_line_preevo_set` / `card_is_recognized_line_preevo`) carries the
broadened set and is read **only** by the preference rungs. `_wincon_set()` is **role-gated** so a
secondary Line's payoff (Hariyama) is never mislabeled a win-condition — behavior-neutral for every
existing deck, all of whose lines are `win_condition`. The tie-break is scoped to **attacker**
lines, so engine-line sequencing (Dunsparce→Dudunsparce) stays owned by the engine rungs
(`fetch-the-support`, `dont-strand-the-evolving-engine`) and `fetch_priority`, never dictated here.

## Considered Options

- **Gate the over-eager rung** — add a stand-down to `prefer-wincon-line-piece` when the grab is a
  redundant line pre-evo. Rejected: subtracts to fix, less legible, and doesn't recognize the cheap
  line as a real development target.
- **New competing positive at ~+18** — a rung heavy enough to out-score the existing line-piece
  credit. Rejected: a dominating weight, not a tie-break; two rungs pushing opposite ways on the
  same pick, hard to reason about.
- **Broaden line recognition (chosen)** — makes the term a genuine *small* tie-break by first
  equalizing line-piece credit across the win-condition and secondary lines, then tipping on prize
  economy.

## Consequences

- Solrock's `dont-fetch-the-redundant-piece` **Riolu-half** can fold (deck-align) — the general
  term now covers the redundant-wincon-base case, including "Mega online, no benched Riolu, 2nd
  Riolu vs Makuhita," which the deck rule's `card_is_redundant` gate misses. Its **engine-half**
  (one-of-each *functional* redundancy — a 2nd Solrock) is not prize economy and stays.
- **Flexibility** is inherent: the tie-break is dominated by every real need; the `wincon_in_play`
  gate is board state, not a deck constant; a deck overrides the order via `fetch_priority` (+40) or
  disables/retunes via `weight_overrides` (ADR-0035). Deck- and board/hand-dependent by construction.
- Ships **default-on, kill-switched**, with blunder-buster telemetry; verified by Score-Diff
  neutrality across decks (ADR-0034) + the solrock fixtures still landing, and ladder-validated
  (the gauntlet is invalid-for-gain).
