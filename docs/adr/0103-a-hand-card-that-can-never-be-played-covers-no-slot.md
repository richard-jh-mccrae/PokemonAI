# ADR-0103 — A hand card that can never be played covers no slot: backward line topology is one oracle

**Status:** Accepted (built 2026-08-02, `/implement` on
[Issue #288](https://github.com/richard-jh-mccrae/PokemonAI/issues/288), T3.5/10 of the Value System
POC).
**Implements** the term-sufficiency audit's finding **F12** (`docs/plans/term-sufficiency-audit.md`).
**Applies [ADR-0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)** (the
deadline gate is a factor of the one equation) and **[ADR-0006](0006-function-tags-single-source-of-structural-facts.md)**
(a behavioural claim about a card is a Function Tag).
**Narrows nothing and supersedes nothing** — `gate_library.deploy_odds` keeps its job, it just stops
answering a question it was never shaped to answer.

**Context issues:** Issue #288 (this build), Issue #278 (the T3.5 parent track), Issue #262 (T3, whose
`state_value.hand` term is the second consumer this fix serves in advance), Issue #149 (which
nominates `slowking` as the validation deck).

## Context

`development.line_topology` cancels the evolve credit for a line whose **forward** form is
unreachable. Nothing asked the mirror question — whether a hand card's own **pre-evolution** can still
reach the board — and the audit found the consequence sitting in a committed decklist.

`slowking` runs 2× **Metagross** — Stage 2, `evolvesFrom` **Metang**, 170 HP (verified at
`data/EN_Card_Data.csv` id 276) — and the list contains **no Metang and no Beldum**. Both copies are
dead cards for the entire match. Structurally the same state arrives transiently in every deck the
moment a line's base is prized or discarded out; `slowking` merely makes it permanent.

Two shipped guards exist for exactly this class — `fetch-base-before-stranded-payoff` and
`dont-strand-the-evolving-engine`, the latter built after a **measured** priority inversion where the
fetch doctrine preferred tutoring a dead Stage 1 over the Basic that enables it (`dragapult_ex`
STRATEGY.md §6). Replacing the rung layer with differencing drops both unless the needs assignment
learns the question.

### What was measured, not recalled (2026-08-02)

The partial answer already shipped, and measuring it changed the fix. `planner._deploy_odds` computes
a `deploy` factor that already zeroes a provably-undeployable evolution, and `_resolve_needs`
consumes it — so `worth × deploy > 0` already suppressed the slots keyed on the card **itself**
(`line`, `general`). The gap was elsewhere, and it was worse than a missing discount.

On `grimmsnarl_ex`, with all three Snorunt in the discard and a Froslass (role `engine`) in hand
beside a real draw Supporter:

| | before | after |
|---|---|---|
| Froslass covers the `draw_engine` slot | **yes** | no |
| that slot's value | **12.0** (the engine-BODY tier) | 8.0 (the engine-supporter band) |
| the live Supporter's `keep_v2` | **0.0** | 8.0 |

The dead body both **covered** the draw need — so the Supporter that actually fills it priced at zero
and shed for free — and **raised the price** of covering it, because the band reads off the slot's
eligible rows. `deploy` cannot reach either: it prices a card, and this is about which rows are
CANDIDATES.

## Decisions

**1. The gate lands on ELIGIBILITY, in `pilot._resolve_needs` — not on any slot's value, and not in
`state_value`.** An unplayable row supplies **no slot of any kind**. That is the honest home: both the
rung system and the differencing system read the same resolution, so one fix serves both, and
`MySide.needs` consumes whatever the resolver produced. It is enforced at the single `_emit` choke
point *and* on every leg's candidate list, because two legs derive their slot VALUE from the
candidates (the `draw_engine` band above, and the general-worth suppression set).

**2. The question is the CHAIN, not one hop.** The audit's cheapest-fix line describes a single
`evolvesFrom` resolved against three zones. That is the shallowest correct version: a Metang in hand
does not make a Metagross playable when every Beldum is gone, because the Metang cannot reach the
board either. The walk grounds out on a body already **in play** (nothing further is owed) or on a
Basic, and a name cycle terminates unplayable — the rule `_stranded_evolution_set` has always applied.

**3. Rare Candy is part of the question, not an extension of it.** *"Choose 1 of your Basic Pokémon in
play. If you have a Stage 2 card in your hand that evolves from that Pokémon, put that card onto the
Basic Pokémon to evolve it, skipping the Stage 1"* (card text, `data/EN_Card_Data.csv` id 1079). A
missing Stage 1 therefore does **not** prove a Stage 2 dead. This is not hypothetical generality:
`grimmsnarl_ex` runs 1 Rare Candy and the full Marnie's Impidimp → Morgrem → Grimmsnarl ex line, so a
gate without the escape would strip that deck's **win condition** while the enabler sat in hand — a
worse error than the one being fixed, and a direct violation of decision 4.

**4. Fail OPEN — *unreadable is not unplayable*.** An unknown card, or one whose `evolvesFrom` names a
card the pool holds no printing of, makes no claim and keeps everything. Only a base **provably**
absent from all three zones takes anything away, and the deck zone is the sound *"not provably gone"*
read (`_unseen_deck_counts`), never *"seen"* — a base in the discard with a copy still unseen in deck
or a face-down prize is still reachable. The gate also fails open **as a whole**: with no stat
provider or no Function Tag table it does not run at all, because a gate that strips eligibility on
missing evidence sheds live cards, which is the fail direction the whole keep-value family forbids.

**5. One oracle, four callers — `common.playability`.** The question had three answers in the tree and
was about to have a fourth. They are now one module, and each caller states what it needs:

| caller | zones it passes | what changed |
|---|---|---|
| `pilot._resolve_needs` (the gate) | play · hand · unseen deck | **new** |
| `planner._deploy_odds` (the `keep_cost` factor) | play · hand · unseen deck | inlined one-hop walk **deleted** |
| `pilot._stranded_evolution_set` (deck-static) | the decklist, nothing in play | private copy of the recursion **deleted** |
| `gate_library.deploy_odds` | — | takes the resolved `playable` boolean; keeps only the arithmetic |

Two of those deletions were latent bugs, and both are provably silent on the four shipped decks —
which is exactly how the duplicates survived. `_stranded_evolution_set` had no Rare Candy escape (no
shipped deck holds both a Rare Candy and a stranded evolution); `_deploy_odds` had neither the chain
nor the escape.

**6. Rare Candy is found by a Function Tag, not a card id.** `planner._RARE_CANDY_ID` justified itself
in its own comment as *"no other consumer needs the tag"*. Issue #288 is the second consumer, and it
needs the fact about a card sitting in **hand or deck** — a question no option-id comparison can
answer. The constant is deleted; `rare_candy` is now a curated override
(`tools/meta_tracker/function_overrides.json`) shipped in `card_functions.json`, and
`planner._is_rare_candy` reads it, which also makes that method's docstring true again.

## Consequences

* **Measured 2026-08-02** — suite green; **both gates PASS with zero unruled flips**, and neither
  baseline re-captured (ADR-0094):
  * **Decision Gate** — 372 frames, `agree 250/346 → 250/346`, 4 picks moved. Two are **FIX**
    (`83038055|0|decision|40` `[5] → [0]`, `83665798|1|decision|39` `[3] → [4]` — both now the
    human's option); the other two are the held-out pair already owned by #262 / #272. **No new
    REGRESSION.**
  * **Discrimination Gate** — 268 frames, gated on 266, `agree 182/248 → 180/248`; the 2 moved
    frames are the pair held out onto #262 before this branch existed. **No new `OK → MISS`.**
  * So this sub-issue moves scoring, as Issue #278 predicted, and the move is **two frames toward
    the human and nothing away** — nothing needing a wave-3 verdict.
* A hand of provably-dead evolutions now prices at its **general** worth only — actually at nothing,
  since the general slot is keyed on the same card. That is the intent: the refresh/gamble shed
  digs past it instead of hoarding it.
* The `deploy` factor and the eligibility gate can no longer disagree about a card. They resolve one
  oracle over one `_unseen_deck_counts` read — itself newly extracted, having been three identical
  five-line walks (`_discard_equation_rows`, `_needs_hand_rows`, `_deploy_supplier_rows`) that this
  work would have made four.
* **Deliberately not addressed:** whether an unplayable card should still rank above outright fodder
  in *pitch order*. It does — the residual-worth tiebreak is untouched — and that is correct: a dead
  card is the first thing you discard, which is what shedding it for free means.
