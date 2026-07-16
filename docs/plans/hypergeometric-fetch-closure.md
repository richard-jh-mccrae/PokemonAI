# Hypergeometric odds must model FETCH-CHAIN closure + hand expansion (grill later)

**Status:** OPEN — a concern to grill/build later, NOT started. Placeholder so it isn't lost.
**Owner concern (user, 2026-07-16):** the naive "P(draw the energy)" hypergeometric **undercounts** the
true probability of *assembling* what you need, because the outs are not just literal target cards — they
include **tutor/fetch chains** and **hand-expanding draws**. This biases every downstream consumer
(win-odds, lethal, and especially the 2-ply opponent worst-case / survival term) toward thinking a player
CAN'T get there when they often can.

## The thesis
`P(target in the drawn window)` over "copies of the literal card ÷ deck" is a **lower bound**, sometimes a
badly loose one. The real question is: **P(there exists a legal play sequence this turn that ENDS with the
target assembled)** — a reachability query over the tutor graph, gated by resource limits, not a
single-card hypergeometric.

## Failure mode A — fetch-chain closure (multi-hop tutors)
The "outs" for *an Energy* are the transitive closure of everything that can *reach* an Energy, e.g.:

- `Fighting Gong` (id 1142, Item, tags `search`/`tutor_energy`) → **Energy** — one hop.
- `Team Rocket's Petrel` (id 1219, Supporter, tags `search`/`tutor_trainer`) → **Fighting Gong** → **Energy** — two hops.

So "P(they draw energy)" must become "P(they draw **Energy OR a card whose tutor-closure reaches Energy**)".
The closure is computable from **Function Tags** (`tutor_energy`, `tutor_trainer`, `search`, draw tags) —
build the reachability graph `card → what it can fetch → …` down to the target class. **Enumerate the
graph from card data / `card_functions.json`, never from memory** (CLAUDE.md verify-at-source; the two
anchors above ARE verified from `card_functions.json`).

## Failure mode B — hand expansion multiplies the window
"Opponent hand size 1, needs 1 energy to win" → naive P ≈ P(that one card is Energy), tiny. But if that one
card is a **draw/tutor** (`tutor_trainer`, a draw Supporter, Judge/Lillie-class refill), they play it and
**hand goes 1 → 4–8 cards**, each a fresh energy chance. The probability must be computed over the
**post-expansion** window, conditioned on spending the draw card — and iterated if the expansion itself
draws more enablers. A one-card hand is NOT a one-card sample when one of its cards is a shovel.

## Why it matters (both directions are dangerous)
- **Opponent worst-case (survival / the 2-ply):** undercount → "they can't get the 2nd energy, we're safe"
  → we develop (Lillie's) when we should defend (Wally's) and lose. See the develop-rung handoff's 2-ply
  discussion — the opponent-KO reachability is only honest if its energy odds include the fetch closure.
- **Our own win-odds / lethal race:** undercount our OWN reach → we pass on a win we could assemble, or
  misjudge a race. (Mirror of `dont-search-a-probable-whiff`, ADR-0029, which is the single-hop version.)

## What "correct" probably looks like (to grill)
Not a bigger closed form — a small **reachability/DP over the tutor graph** for "can I assemble N of class C
this turn," then a probability that the *entry points* to that graph are in the drawn/hand window:

1. **Outs = tutor-closure**, computed from Function Tags, terminating at the target class (Energy / a body / a piece).
2. **Sequential, without replacement** — each fetch thins the deck and consumes a card; odds are conditional, not one hypergeometric draw (compose per hop).
3. **Resource limits are load-bearing** — one Supporter per turn (Petrel is a Supporter; Fighting Gong is an Item, free), one manual Energy attach per turn (so "energy in hand" ≠ "energy on the body THIS turn"), Ultra-Ball-class discard costs, hand-size/bench caps.
4. **Hidden-info split** — hand vs deck (hypergeometric split, ADR-0029); use the **exact deck tracker** when a search has revealed contents (sound), hypergeometric only when just counts are known ([sound-deck-emptiness-oracle]).
5. **Prizes remove outs** — a prized copy is unavailable; the prize-exact split matters for tight counts.
6. **Horizon** — "this turn" reachability vs "by their next attack" (their draw step adds one card + any draw they play). Decide the horizon per consumer.

## Grill checklist (the "verify that…" this note is for)
- [ ] The energy-odds function counts **tutor-closure outs**, not just literal Energy cards.
- [ ] It models **hand-expansion** (a draw/tutor grows the sample before the target is checked).
- [ ] It respects **1 Supporter / turn** and **1 attach / turn** when deciding what's assemblable THIS turn.
- [ ] It thins the deck **sequentially** across a multi-hop chain (conditional odds), not one flat draw.
- [ ] It uses the **exact tracker** when the deck is revealed, hypergeometric only on counts.
- [ ] The tutor graph is **enumerated from card data / Function Tags**, re-verified against the set, not recalled.

## Anchors (verified 2026-07-16 from card data / `card_functions.json`)
| id | card | cat | tags | role in the example |
|---|---|---|---|---|
| 1142 | Fighting Gong | Item | `search`, `tutor_energy` | fetches Energy (1 hop) |
| 1219 | Team Rocket's Petrel | Supporter | `search`, `tutor_trainer` | fetches Fighting Gong (→ Energy, 2 hops) |

## Where it plugs in
Deck-Content Odds (ADR-0029, the single-hop probable-whiff veto is the seed to generalise), the win-odds /
lethal reasoning, and the develop-rung 2-ply opponent worst-case (`docs/plans/develop-rung-handoff.md`).
Function Tags are the canonical signal for the tutor graph (`src/common/card_functions.json`).
