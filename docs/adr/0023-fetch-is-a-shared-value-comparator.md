# ADR-0023: Fetch decisions are one shared closed-form value comparator (importance × gap × availability), board-only, Read-deferred

**Status.** Accepted (grilled 2026-06-29); **core implemented 2026-06-29** test-first
(`tests/strategy/test_fetch_doctrine.py`, REQ-GEN-0035..0040). **Shipped this build** — the need-gated grab/discard
rungs `fetch-a-starter`, `fetch-the-support`, `fetch-deck-priority` (Tier-3 `Strategy.fetch_priority`),
`discard-the-redundant`, `prefer-good-in-discard` (the `discard_fodder` Role), **greedy multi-pick**
(`_greedy_grab`: gap-update + take-fewer, after verifying multi-fetches are single `maxCount>1` selects),
and the **whether-to-play** positive endorsement `fetch-when-it-fills-a-need` (the `_grab_value_of` /
`_fetch_fills_a_need` PLAY-node lookahead that scores the best grab over the reachable deck set with the
same grab rungs), with their `Context`/`Board` gap signals. The additive scored sum of these *is* `fetch_value` (no
monolithic function — the ADR-0008 idiom). **Shipped earlier** (the partial implementation this
generalises): `fetch-the-wincon`, `prefer-wincon-line-piece`, `fetch-energy-when-starved`,
`prefer-bench-fill-first`, `dont-search-an-empty-deck`, `dont-tutor-the-held-wincon`,
`keep-key-cards-at-discard`, plus the deck-knowledge substrate (`Board.deck_definitely_empty_of` /
`deck_definitely_has`, the `_FETCH_FILTERS` / `_search_signals` path, the `OwnCardModel` deck tracker).
**Still deferred:** decision (A)'s **cost-netting** (subtract the shed cards' keep-value from a
`cost_discard` fetch + Supporter-economy opportunity cost) and **Plan-scaled bar** — the positive
endorsement is shipped, the common stand-down cases are covered by the whiff / redundant /
`cost_discard`-sequencing rules; plus Read-conditioned fetching and prized-wincon urgency.

**Context.** A **fetch** — a card that presents a *choose-from-deck* select (Ultra Ball, Nest Ball, Mega
Signal, Buddy-Buddy Poffin; the `search`/`dig`/`bench_fill`/`tutor_*` tag family, **not** raw draw) —
appears in nearly every deck and is misplayed in three distinct ways: playing it at the wrong time,
grabbing the wrong card, and (when it costs a discard) pitching the wrong card. It belongs in the
**General Strategy** ([ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md)), the deck-agnostic
counterpart to the **Gust** doctrine ([ADR-0022](0022-gust-is-closed-form-lethal-lookahead.md)). The
registry already held **seven** fetch Hypotheses authored reactively to individual blunders, each with
its own ad-hoc gap test (`fetch-the-wincon` already gates on `not wincon_in_play`,
`fetch-energy-when-starved` on `my_active_energy == 0`). Recent work added a **sound** deck-knowledge
substrate — `deck_definitely_empty_of` (certain, never probabilistic — a copy hideable in the 6 face-down
prizes keeps the signal silent) and the exact `OwnCardModel` prize/deck tracker giving
`deck_definitely_has`. The scattered rules and the new substrate wanted a single coherent shape.

**Decision.**

- **One doctrine, three decisions, one primitive.** A fetch is *(A) whether to play now*, *(B) what to
  grab*, *(C) what to discard*, all reading **`fetch_value(card, board) = importance × still-lacking ×
  available`**. The whether-to-play value *is* the best grab value, so play-reason, grab, and discard
  agree by construction (the shared-oracle invariant from ADR-0022's `gust_ko`). Closed-form off
  `CardStat` / Lines / Tags — no Search, consistent with the Tier-0 contract.
- **Additive need-gated scoring, not a lexicographic ladder.** A candidate scores *what it is × whether
  I lack it*, summed in the existing weighted-Hypothesis idiom (loss-prevention rungs carry
  near-imperative weight, real trade-offs survive). The shift from the old rules is the universal **gap
  gate**: an importance rung fires only while the piece is genuinely missing from hand+play.
- **Importance is derived, then overridden sparsely — no exhaustive per-card table.** Tier 1 derives it
  from `Strategy.lines` + Function Tags + `CardStat`/forward-evolution index (a zero-label deck plays
  competently); Tier 2 is the sparse `roles` overlay mapped to tunable fetch-weights (the existing
  `_weight` by-id override); Tier 3 is a rare explicit per-card priority list for combo decks. Trainers
  use the same model (importance from tag + board-need).
- **Gap = per-category satisfaction; "have" = hand + in-play only.** The win-condition is the per-Line
  exception (specific). Satisfy-count defaults to 1 (so a redundant second copy falls to ~0 with no
  special guard), overridable for needs that want count (energy, basics).
- **Deck-knowledge is an availability *gate*, never a fetch *forcer*.** `deck_definitely_empty_of`
  filters dead candidates; `deck_definitely_has` informs but does not push a fetch — the over-play risk
  of a positive "the deck has it, so grab it" endorsement is deliberately excluded from v1 (gap drives).
- **Discard reuses the primitive inverted.** Keep-value = `fetch_value` read as "want it in hand"; shed
  the lowest-keep N. A deck-overridable `good-in-discard` term lets a recursion/discard-fed deck redirect
  the pitch toward cards it *wants* in the bin.
- **Multi-pick is greedy-sequential with gap-update** (pick → mark satisfied → re-score), so a Poffin's
  second basic fills the next unmet need rather than doubling up.
- **Whether-to-play nets cost by economy.** Free Item fetch fires on any positive grab; a `cost_discard`
  fetch subtracts the shed keep-value (and is delayed until the discard is cheap); a Supporter fetch must
  beat the best alternative Supporter. The worth-it bar is **Plan-scaled**.
- **Scope.** v1 is board-only (the Read/Scouting is not wired into the Pilot); Read-conditioned fetching
  and prized-wincon urgency are deferred behind designed-in seams.

**Considered options.**

- **A strict lexicographic priority ladder** (always satisfy rung 1 before rung 2) — rejected as
  brittle: a trivial high-rung need would always beat a large low-rung need, and it can't express
  trade-offs. Additive need-gated scoring keeps the rest of the architecture's idiom and defers genuine
  ties to the Base Value Model ([ADR-0007](0007-learning-is-one-offline-value-model.md)).
- **An exhaustive per-card importance table per deck** — rejected: brittle, doesn't scale across decks,
  and duplicates what `Strategy.lines` / Function Tags / `CardStat` already encode. Derive-then-override
  matches [ADR-0006](0006-function-tags-single-source-of-structural-facts.md).
- **A separate value function for discard** — rejected: reusing `fetch_value` inverted gives the free
  "never pitch what you'd fetch back" invariant; a second function could contradict the first.
- **Independent top-N for multi-pick** — rejected: it would grab two of the same basic off one Poffin
  even after the first satisfies the need. Greedy gap-update falls straight out of the satisfy-count.
- **Wiring `deck_definitely_has` to a positive "play the fetch" endorsement** — rejected for v1: an
  over-play risk (grabbing because you *can*, not because you *lack*) that needs the value layer; the
  oracle stays an availability gate.
- **Read-conditioned fetching in v1** — deferred (matching ADR-0022): board-only stays closed-form and
  fully testable, and the deck-Role weight-bump seam adds it later without reshaping the comparator.

**Consequences.** The seven shipped fetch Hypotheses become **partial instances** of the comparator
(each one importance rung or one gap/availability gate); a future reader who sees them scattered should
read this ADR for the unifying shape. The build adds a shared `fetch_value(card, board)` primitive
consumed at the `_TO_HAND`/`_TO_BENCH`/`_DISCARD` selects and as a whether-to-play Board signal, new
importance rungs beyond wincon/energy/bench (a derived `starter`/`support` need), a keep-value discard
ranking generalising `keep-key-cards-at-discard`, the satisfy-count gap model, the Tier-3 priority list,
and the `good-in-discard` deck override. v1 plays board-only; Read-conditioned and prized-wincon urgency
arrive once the Read/Posture is wired. Documented in
[general-strategy.md](../general-strategy.md#fetch-search-doctrine--designed-adr-0023); the glossary
term **Fetch** is in [src/common/CONTEXT.md](../../src/common/CONTEXT.md).
