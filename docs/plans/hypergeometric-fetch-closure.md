# Hypergeometric odds must model FETCH-CHAIN closure + hand expansion

**Status:** GRILLED 2026-07-17 (session grill — every claim source-verified; design corrected and
re-scoped below). Build NOT started. Original note 2026-07-16.
**Owner concern (user, 2026-07-16):** the naive "P(draw the energy)" hypergeometric **undercounts** the
true probability of *assembling* what you need, because the outs are not just literal target cards — they
include **tutor/fetch chains** and **hand-expanding draws**. This biases every downstream consumer
toward thinking a player CAN'T get there when they often can.

## The thesis — VERIFIED, with a sharper decomposition

`P(target in the drawn window)` over "copies of the literal card ÷ deck" is a **lower bound**, sometimes a
badly loose one. The real question is: **P(there exists a legal play sequence this turn that ENDS with the
target assembled)** — a reachability query over the tutor graph, gated by resource limits.

**Grill correction (the good news):** the math is *simpler* than the original note feared, not harder.
Every tutor in this set is a **whole-deck search** ("Search your deck for …, then shuffle") — verified
across all 13 tutor-tagged cards (`data/EN_Card_Data.csv`, table below). A search's success is **not** a
draw hypergeometric and deck thinning between hops is irrelevant (the search sees the whole deck): once a
tutor is in hand, its fetch succeeds iff **≥1 target remains in the deck**, i.e. the prize-split question
`deck_odds.p_contains` (ADR-0029) already answers. So the composition is

> **P(assemble) = P(≥1 entry point in the drawn/hand window)  ×  P(the chain's targets are unprized)**

— a window hypergeometric on the *entry points* (literal targets ∪ tutors whose closure reaches the
target class), times prize-split factors, with every interior hop **deterministic given unprized**. The
original note's "compose a hypergeometric per hop, thinning the deck sequentially" is **REFUTED** for
search tutors; only genuine *draw* effects (draw N off the top: `draw`/`dig`/`shuffle_hand` tags) are
window draws needing the drawn-window math.

## Grill verdicts (2026-07-17, all at source)

**VERIFIED:**
- **Failure mode A is live in shipped code.** `_gamble_ko_classes`
  (`src/common/strategy/planner.py:1595`) counts a Gamble Line's outs as *literal Basic Energy copies*
  in `deck_known_counts` — a drawn Fighting Gong / Energy Search (Items: free, playable post-refresh,
  pre-attach) enables the same KO and is not counted. The module already self-documents a sibling
  undercount ("special Energy … under-counted, safe"). Per-class it errs safe; across the rung it makes
  honest gambles fire less than they should — we pass on wins we could assemble.
- **Resource limits verified** (`docs/rules.md` §3, rulebook L105-148): 1 Supporter/turn, 1 manual
  attach/turn, Items unlimited. Petrel (Supporter) → Fighting Gong (Item) → Energy is legal in one turn
  and consumes the Supporter slot.
- **Anchor tags verified** (`card_functions.json`): 1142 `search,tutor_energy`; 1219 `search,tutor_trainer`.
- **Prizes remove outs** — and the machinery is `p_contains` (ADR-0029), already built.

**REFUTED / CORRECTED:**
1. **"The closure is computable from Function Tags" — NO, tags alone build a WRONG graph.** The tags
   give edge *existence* only; the edge *predicate* lives in card text. Proof: Fighting Gong's tag is
   generic `tutor_energy` but its text is "Basic **{F}** Energy … or a Basic **{F}** Pokémon" —
   type-locked. A {W} deck counting Gong as an energy out is wrong. Likewise Ethan's Adventure /
   Firebreather = {R}-only; Colress's Tenacity / Hilda fetch "an Energy card" (**includes Special**);
   Crispin fetches 2 *different-typed* Basics **and attaches one directly**. The closure needs per-card
   predicates (target class, type lock, basic/special, count, destination, cost) — effect-text /
   ADR-0032-compendium territory, seeded from tags but never terminated at them.
2. **Per-hop hypergeometric composition — REFUTED** (see thesis correction above): searches are
   whole-deck; only the entry window and the prize split are probabilistic.
3. **The "2-ply opponent worst-case" consumer is STALE.** ADR-0064 (grilled 2026-07-16, built
   suite-green 2026-07-17) settled the threat direction *without* energy draw-odds: the survival read's
   worst-case ceiling **assumes the attach** (budget = attached + 1 + matched-Read burst), the 2-ply
   escalation is deprecated & removed (Decision 6), and "is it in their deck+hand" was ruled
   uncomputable (Decision 4 — existence for threat, matched Read fail-CLOSED for safety). So danger
   direction #1 below is currently covered by **pessimism, not probability** — the fetch closure is NOT
   needed there today. It becomes load-bearing only if the ceiling is ever relaxed probabilistically;
   any such relaxation MUST price the closure or it re-opens the "we're safe → we develop → we lose" hole.

**MISSING from the original note (grill additions):**
- **The recycle/discard branch.** 8 `recycle`-tagged cards (Night Stretcher 1097, Max Rod 1110, Energy
  Retrieval 1118, Sacred Ash 1129, Lana's Aid 1184, Tarragon 1238, Levincia 1254, Kyogre 721) recover
  Energy/Pokémon from the **discard — a fully visible pool**, so this closure branch is *deterministic
  given the recycler* (no prize split at all). Outs = deck-closure ∪ discard-closure. Corollary:
  ADR-0064's "visibly-exhausted copies" safety read is unsound against recycle decks — a discarded Mega
  copy can come back.
- **Attach-effect tutors bypass the 1-attach limit.** Crispin (1198) attaches a fetched Energy directly;
  the `energy_accel` class (16 cards) exists. The closure's terminal must distinguish target classes
  **"in hand"** vs **"attached this turn"** — original point 3's "energy in hand ≠ on the body" cuts
  both ways.
- **The prize pool re-enters on KO.** "Prized = unavailable" holds *this turn*, but on the survival
  horizon the opponent KOs me → immediately takes a prize → that prize may BE the missing piece. Prized
  outs are horizon-dependent, not gone.
- **Costs can consume the very outs being assembled.** Ultra Ball discards 2 from hand; Larry's Skill
  discards the whole hand before searching. A closure DP must charge costs against the assembled set,
  not just count edges.
- **Multi-target tutors assemble N in ONE hop** (Energy Search Pro: any number of different types;
  Firebreather: up to 7 {R}) — "assemble N of class C" mostly doesn't need deep chains.
- **The Supporter slot interacts with the SEED consumer itself.** 4 of 5 `shuffle_hand` refreshes
  (Lacey, Judge, Harlequin, Lillie's Determination) are Supporters — playing the refresh spends the
  slot, so inside the Gamble Line window the post-draw closure is **Items only** (Petrel is dead there);
  only after an Unfair Stamp (Item) refresh do drawn Supporter tutors stay live. Resource limits are
  load-bearing exactly as claimed — including on the note's own first consumer.

## Failure mode A — fetch-chain closure (multi-hop tutors) — stands, with the corrected math
The "outs" for *an Energy* are the transitive closure of everything that can *reach* an Energy:
`Fighting Gong` → {F} Energy (one hop, F-decks only); `Team Rocket's Petrel` → any Trainer → e.g.
Energy Search → any Basic Energy (two hops, Supporter slot). "P(they draw energy)" must become "P(they
draw Energy OR an entry point whose closure reaches Energy)" — entry points in the window, interior
hops deterministic-given-unprized. **Enumerate the graph from card TEXT (tags as the index, predicates
from text), never from memory** (CLAUDE.md verify-at-source).

## Failure mode B — hand expansion multiplies the window — stands
"Opponent hand size 1" is not a 1-card sample if that card is a draw/refresh: hand goes 1 → 4–8, each a
fresh chance, iterated if the expansion draws more enablers. Compute over the post-expansion window,
conditioned on spending the expander. (Our own side already gets the *first* expansion right — the
Gamble Line IS the refresh window — but counts no chained enablers inside it.)

## Why it matters — re-scoped after ADR-0064
- **Our own win-odds / gamble / lethal reach is the LIVE gap** (was danger #2, now priority #1):
  `_gamble_ko_classes` undercounts today, on **exact** tracker-anchored counts where the closure is pure
  counting + legality — no new probability model needed. Mirror of `dont-search-a-probable-whiff`
  (ADR-0029, the single-hop seed); `_is_energy_tutor` (planner.py:1644) is the existing one-hop precedent.
- **Opponent worst-case / survival** (was danger #1): owned by ADR-0064's pessimism today. The closure
  is the *precondition* for ever relaxing that ceiling probabilistically, and a sharpener for the
  matched-Read safety direction (`copies_left_odds` on evolution copies ignores recycle) — deferred
  behind ADR-0064's own follow-ups.

## What "correct" looks like (grilled design)
1. **Outs = closure entry points**, enumerated from card text with per-edge predicates
   (target class + type lock + basic/special + count + destination hand/attached + cost), indexed by
   tags (`tutor_*`, `search`, `recycle`, `energy_accel`, `draw`, `dig`), terminating at the target class.
2. **P(assemble) = window hypergeometric on entry points × prize-split (`p_contains`) per fetched
   target.** No per-hop draw composition — searches are whole-deck. Draw effects (not searches) expand
   the window instead.
3. **Resource limits are load-bearing** — 1 Supporter/turn (charge the chain; the refresh itself usually
   spends it), 1 manual attach/turn (unless the edge attaches directly, Crispin/`energy_accel`),
   discard costs charged against the assembled set, bench/hand caps.
4. **Hidden-info split** — exact tracker (`deck_known_counts`) when anchored: the closure is then
   deterministic counting. Hypergeometric (`p_contains`) only on unanchored counts.
5. **Prized outs**: removed this-turn, horizon-dependent across a KO (they take a prize when they KO).
6. **Horizon per consumer** — "this turn" vs "by their next attack" (+1 draw + their expansions).

### Staged build (re-grilled 2026-07-17 — user pushback: "why limit ourselves?")

**Stage 1 — the full ITEM closure (and it IS the full closure, not a truncation).** Closure outs in
`_gamble_ko_classes`: **Item-class** deck-tutors whose predicate matches the missing slot type AND whose
target remains in deck (both exact post-anchor), plus **recycle Items** whose target sits in the visible
discard. Under exact deck knowledge the fetch step is **deterministic** (whole-deck search / visible
discard), so "refresh → Item → Energy" is NOT a two-step probability — it is the SAME single window
hypergeometric with a bigger outs list. And in this set the Item-only graph has **depth 1 to Energy by
construction**: the only any-Trainer fetcher is Petrel (Supporter) and the only Supporter-fetcher is
Meowth ex's on-bench ability → a fetched Supporter is slot-dead in the refresh window anyway. So Stage 1
loses nothing to hop-depth — "one hop of Items" ≡ the reachable closure post-Supporter-refresh.
Supporter tutors join the outs only when the refresh was the Item (Unfair Stamp).

**Stage 2 — DRAW ENGINES: the genuinely probabilistic second stage (user, 2026-07-17).** The realistic
miss-chain is: refresh whiffs on Energy/Items but hits a **draw engine** — verified anchors: Drakloak
(120, ability *Recon Directive*: top 2, take 1, other to bottom; `dig,draw`) and Dudunsparce (66,
ability *Run Away Draw*: draw 3, then shuffle ITSELF + attached back into the deck; `draw,stall`) — and
the engine's extra draws are fresh Energy chances. This is failure mode B made concrete, and it has an
**exact Tier-0 closed form** (no simulation, plain `math.comb`), because conditioning on "no out among
the first n" leaves all O outs uniformly in the remaining pool:

> P(assemble) = P(≥1 out in n)
>             + [ P(no out in n) − P(no out AND no usable engine in n) ] × P(≥1 out in m | pool−n, O)

with n = refresh draws, m = the engine's window (Recon: 2 with take-1; Run Away Draw: 3). Both bracket
terms are single multivariate-hypergeometric ratios (outs and engines are disjoint card classes). One
engine stage, not infinite recursion — engine-finds-engine is cut off (bounded, always under-counting).

**Engine usability is a hard gate, checked exactly, before an engine copy counts:**
- **Evolution timing** (`rules.md` §4): a DRAWN Drakloak needs an eligible pre-evo already on board
  (in play since last turn, not either player's first turn). No eligible Dreepy → Drakloak copies are
  not engines this turn.
- **Already-on-board engines with the ability unused** are better than drawn ones: their window is
  **unconditional** — and sequencing matters (fire Recon BEFORE the refresh: hit → the deterministic
  attach line, no gamble needed; miss → the refresh is still live). The planner already sequences
  options; the odds function just has to price both orders.
- **Ability wording is per-card** ("Once during your turn" — engine-enforced), bench space for a drawn
  Basic engine, and Run Away Draw's cost: the body + attachments leave play (pool grows, board tempo
  paid — priced by the leaf, not the probability).
- **`energy_accel` abilities** (16 tagged) are a further deterministic edge class (attach from
  deck/discard, bypassing the manual attach) — same per-card text-predicate treatment, enumerated at
  build time, not from memory.

**The "exactly one short" gate becomes DERIVED, not hardcoded (user grill, 2026-07-17).** The existing
`cost != my_active_energy + 1` gate in `_gamble_ko_classes` is legality arithmetic (one manual attach ⇒
only a 1-slot shortfall is fillable this turn), NOT a value judgment — and it silently assumes attach
capacity = 1. Once the closure carries attach-adding edges (Crispin attaches a fetched Energy directly;
`energy_accel` abilities attach from deck/discard), a TWO-short KO becomes legitimately reachable. The
gate generalises to `shortfall ≤ 1 + reachable-accel-attaches` — computed from the same closure, per
slot type (an accel edge must match the missing slot's type predicate). Zero-short stays out (the KO is
deterministic — attack) and shortfalls beyond capacity stay out (no draw helps this turn).

**Cost side — ownership and the honest gap (user grill, 2026-07-17).** "What is my hand worth if I
shuffle it away?" splits per horizon. *This turn* is priced: the gamble must beat `det` (the best
deterministic line, including what the held hand already reaches), and ordinary non-KO refresh economics
are owned by ADR-0060's card-swing oracle (shed −8/card, flat +20 draw, strip/gift) under the ADR-0024
keep-value floors — the gamble rung never gatekeeps ordinary refreshes or attaches. *Next turn* is the
gap: keep-value exists only as BINARY vetoes (wincon / line pre-evo / irreplaceable ACE-SPEC Tool in
hand → stand down); every other held card is priced at zero keep-value, so six merely-good cards shuffle
away like dregs. That graded hand-quality read is the **explicitly parked** value-model problem
(ADR-0060 §Deferred "Hand QUALITY", ADR-0007/0042/0053) — the hand-tuned-scalar route was tried on the
develop-leaf `handCount` credit and overfit. Acceptable for the KO gamble (benefit ≈ KO_SCORE dwarfs
per-card shed; the error only matters near break-even), but any future NON-KO outcome class (ability
unlock, ACE-SPEC hunt — each needs its own crisp closed-form value) must not ship without a graded
keep-value term, or the flat +20 draw credit will systematically over-fire refreshes.

## Grill checklist → build checklist (verdicts as of 2026-07-17)
- [ ] Outs count **tutor-closure entry points** — FAILS today (`_gamble_ko_classes` literal-only; v1 above).
- [ ] Closure includes the **recycle/discard branch** — MISSING from code and from the original note.
- [ ] **Hand-expansion** chains modeled — not built (first expansion only, via the Gamble window itself).
- [ ] **1 Supporter / 1 attach / costs** charged along the chain — spec verified against rules.md §3.
- [ ] Entry-window × prize-split composition (NOT per-hop draws) — corrected spec, not built.
- [x] **Exact tracker when revealed, hypergeometric on counts** — already the codebase shape
      (`deck_known_counts` / `p_contains` collapse, ADR-0029 §3).
- [ ] Graph enumerated from **card text with predicates** (tags as index only) — Fighting Gong type-lock
      is the canonical trap; re-verify per set.

## Anchors (verified 2026-07-16/17 from `EN_Card_Data.csv` + `card_functions.json`)
| id | card | cat | tags | verified text fact (the load-bearing bit) |
|---|---|---|---|---|
| 1142 | Fighting Gong | Item | `search`, `tutor_energy` | **Basic {F} Energy or Basic {F} Pokémon** — type-locked; tag doesn't say so |
| 1219 | Team Rocket's Petrel | Supporter | `search`, `tutor_trainer` | any Trainer → reaches nearly everything at 2 hops; costs the Supporter slot |
| 1119 | Energy Search | Item | `tutor_energy` | any Basic Energy, to hand — the clean 1-hop Item out |
| 1100 | Energy Search Pro | Item | `tutor_energy` | any number of Basic Energy of *different types* — N-in-one-hop |
| 1198 | Crispin | Supporter | `tutor_energy` | fetches 2, **attaches 1 directly** — bypasses the manual attach |
| 1206 | Larry's Skill | Supporter | `tutor_energy` | **discards your hand first** — cost destroys held outs |
| 1097 | Night Stretcher | Item | `recycle` | Pokémon or Basic Energy **from discard** — visible-pool branch |
| 1118 | Energy Retrieval | Item | `recycle` | up to 2 Basic Energy from discard |
| 1121 | Ultra Ball | Item | `tutor_pokemon` | discard 2 from hand — the cost anchor |
| 1080 | Unfair Stamp | Item | `shuffle_hand` | the only **Item** refresh — keeps Supporter tutors live post-draw |
| 120 | Drakloak | Stage 1 (← Dreepy) | `dig`, `draw` | ability *Recon Directive*: top 2, take 1 — the selective engine (Stage 2) |
| 66 | Dudunsparce | Stage 1 (← Dunsparce) | `draw`, `stall` | ability *Run Away Draw*: draw 3, **shuffles itself + attached back in** — window +3, body leaves play |

## Where it plugs in (corrected)
**Priority:** the Gamble Rung's Outcome Classes (`_gamble_ko_classes`, ADR-0039) — v1 above — then the
probable-whiff generalization (ADR-0029) and win-odds/lethal reach. **Deferred behind ADR-0064:** any
probabilistic relaxation of the survival ceiling (must price the closure), and the matched-Read safety
read's recycle blindness. Tags index the graph (`src/common/card_functions.json`); predicates come from
card text (`data/EN_Card_Data.csv` / the ADR-0032 compendium when built).
