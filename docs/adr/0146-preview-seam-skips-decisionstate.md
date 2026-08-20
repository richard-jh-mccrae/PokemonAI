# ADR-0146 — The preview seam: Ledger successors skip the DecisionState build

Status: Accepted (2026-08-20); BUILT. Follows ADR-0145.

## Context

Paired decomposition on real frames showed ~0.3–0.5 ms of every ~0.8 ms Ledger preview node was
`DecisionState.with_observation` (the canonical walk) plus `semantic_key` (the hash walk),
computed INSIDE the transition providers solely to key their engine maps. The Ledger's preview
consumes only the raw successor printout (for `BoardState.advance`), the seat, and the menu —
and the preview walk never merges transpositions, so semantic keys buy it nothing.

## Decision

Both providers gain two behavior-neutral hooks — `_bind(state, observation)` (successor
construction, default `with_observation`) and `_key(state)` (map key, default `semantic_key`).
`common/ledger/seam.py` overrides them: successors become `PreviewState` (raw printout, seat,
lazily-enumerated menu via the same `enumerate_legal_actions`) keyed by free per-successor
identity tokens — and the ROOT is a `PreviewState` too, carrying the deck knowledge the
provider constructors determinize from (`deck`, `deck_counts`, `prize_counts`) sourced from
BoardState, so a live Ledger decision constructs ZERO DecisionStates
(`test_the_ledger_path_constructs_no_decisionstate` pins the boundary). The offline variant
lives in `engine.py` (bundle-excluded) and self-registers into the seam's variant table, so no
shipped file names the offline engine — the packager token-scan gates pinned this.
`preview_provider_factory` maps a runtime-configured factory (partials unwrapped) to its
preview variant, passing unknown factories through unchanged. Identity keys mean the native
multi-world grouping stops merging semantically-equal branches — equal expected value, and the
Ledger runs `world_count=1`. Bellman's own path keeps DecisionState successors through the same
hooks, untouched.

## Measured

Same frames, two identical battery runs: one transition 0.53–0.80 ms → 0.24–0.27 ms. Whole
decisions over the 80-frame corpus replay: p50 13→9 ms, p90 139→78 ms, max 355→190 ms, total
−41%. Zero of 80 frames changed their chosen action; `tests/ledger/test_seam.py` pins
price-identical decisions on real frames and menu-enumeration equality.

## Consequences

The preview path now pays engine step + `BoardState.advance` + the Ledger read (~0.45 ms/node
vs Bellman's ~0.95). Custom test factories keep working (they just carry DecisionStates). A
provider subclass must key every internal map through `_key` — a new map keyed directly on
`semantic_key` would silently exclude preview states.
