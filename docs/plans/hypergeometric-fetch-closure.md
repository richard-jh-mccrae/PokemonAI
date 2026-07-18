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
4. **Hidden-info split — and pre-anchor is NOT a stand-down (user grill, 2026-07-17).** Anchored
   (`deck_known_counts`): the closure is deterministic counting. **Unanchored: the decklist is still
   fully known** (own deck, the ADR-0029 model) — only the prize assignment of unseen copies is random,
   and that is the same hypergeometric split `p_contains` prices. The gamble probability stays exact
   closed-form: sum over j = copies-in-deck (prize-split weights) × the window draw with j copies —
   ≤ 5 terms per card class (u ≤ 4), plain `math.comb`. The current `if not deck_known_counts: return
   None` gate in `_best_gamble_line` prices every pre-anchor gamble at ZERO — the same modeling-gap-as-
   caution failure this whole note attacks; uncertainty must shade P down smoothly, not slam the door.
   A large payoff rightly clears the higher bar ("roll the dice given the uncertainty"): the EV
   comparison needs no special case. Tutor-out validity goes probabilistic the same way (a tutor out is
   void only when EVERY matching target is prized — a computable, usually tiny corner).
5. **Prized outs**: removed this-turn, horizon-dependent across a KO (they take a prize when they KO).
6. **Horizon per consumer** — "this turn" vs "by their next attack" (+1 draw + their expansions).

### Staged build (re-grilled 2026-07-17 — user pushback: "why limit ourselves?")

**Stage 1 — the full ITEM closure (and it IS the full closure, not a truncation).** Closure outs in
`_gamble_ko_classes`: **Item-class** deck-tutors whose predicate matches the missing slot type AND whose
target remains in deck (exact post-anchor; prize-split-weighted pre-anchor, point 4 below), plus
**recycle Items** whose target sits in the visible discard. Under exact deck knowledge the fetch step is **deterministic** (whole-deck search / visible
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
terms are single multivariate-hypergeometric ratios (outs and engines are disjoint card classes).

**Engine-finds-engine recursion — GRILLED 2026-07-17 (the cutoff dissolves into a board-derived bound).**
The "one engine stage" cutoff was framed as a tractability limit; grilling shows it never was one:

1. **The formula ITERATES for free.** Conditioning on "no out in the windows so far" leaves all outs
   uniform in the thinned pool, so each further stage is the same two `comb` ratios in a loop — no new
   math, no blow-up.
2. **The true bound is the BOARD, not a constant.** A k-th engine *activation* needs a k-th eligible
   pre-evo already in play (evolution timing, `rules.md` §4) plus bench capacity — visible facts. So
   derive the recursion depth from **board-supported engine capacity** (count of eligible
   pre-evo/engine pairings), exactly the pattern that replaced the hardcoded one-short gate. Usually
   0–1, occasionally 2; compute to whatever the board legally supports.
3. **Magnitude honestly measured** (illustrative MC, 400k trials: pool 30, outs 6 = 4 Energy + 2 Item
   tutors, 2 Drakloak in deck, n=6 refresh, Recon top-2-take-1, greedy policy): depth 1 adds
   **+4.5pp** hit probability (~+50 EV at KO scale — Stage 2 earns its keep); depth 2 adds **+0.6pp**
   with TWO eligible pre-evos on board and **exactly 0** with one (illegal — confirming point 2).
   ~0.6pp ≈ tie-break EV; since depth is board-derived we pay its cost only when the board offers it.
4. **Engine→TUTOR→Energy is NOT recursion** — the second window's outs are the same Stage-1 union
   (Energy + valid Items + recyclers), and that mass is far larger than engine→engine. Stated
   explicitly so a builder doesn't count literal Energy only in window 2.
5. **Policy inside the probability:** Recon's take-1 is a CHOICE node — the model assumes the greedy
   policy (take an out > take an engine > best other), optimal for a single-target class; the only
   place player choice enters the chance tree.
6. **Dudunsparce bookkeeping:** Run Away Draw returns itself + attached cards to the deck AFTER its
   3-draw — a known-composition pool shift (which can even return an attached Energy as a fresh out);
   pure bookkeeping, still closed form. Its real cost (the body leaves play) is the leaf's to price.

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

**Non-KO outcome classes — GRILLED 2026-07-17 (triage: one is a missing KO class, one escapes the
keep-value blocker, the rest stay blocked).**

1. **FINDING — the evolution-KO class is MISSING and was never non-KO.** `_gamble_ko_classes` prices
   only the **current Active's** attacks (`planner.py:1507` feeds it `board.my_active_id`'s stat). But
   "draw the evolution → evolve the Active → ITS attack KOs" is legal in one turn (Active eligible =
   in play since last turn; evolving keeps attached Energy, `rules.md` §4; a Mega ex does NOT end the
   turn on evolving) and is KO-valued — no new value theory, no keep-value blocker. Outs = the
   evolution's copies + its tutor closure (Ultra Ball, Mega Signal, Hilda…). Variant B, the two-piece
   window ("evolution AND the missing Energy both in the draw"), is a multivariate hypergeometric —
   computable, smaller p, same class. This is the highest-value un-built class in the whole note.
2. **The SURVIVAL class escapes the keep-value blocker.** Trigger: the ADR-0064 predicted-loss shape
   (my bench empty / Active doomed, budgeted incoming ≥ HP) — crisp, already-built machinery
   (`active_doomed`, `_predicted_loss`). Outs: `switch`/`heal`/`bench_guard`-class cards + their
   closure. Value: averting a predicted GAME loss is ±KO_SCORE-scale by the loss rung's own
   definition — it dwarfs per-card shed cost exactly like the KO class, so the binary hold-* guards
   suffice and the round-3 blocker does not apply. Same void rule (enabler in hand → deterministic
   line, no gamble) and det baseline (the deterministic route to survival) as the KO class.
3. **Mid-value classes — blocker REVISED (round 6, user grill 2026-07-17): keep-value has a
   closed-form FLOOR, and it is this note's own machinery pointed backwards.** The round-3/5 ruling
   ("blocked behind the ML value model") was too coarse. Hand value splits:
   - **Replaceability — closed-form.** A refresh SHUFFLES the hand into the DECK (nothing is
     destroyed), so the cost of shuffling card X = X's role value × the drop in P(having X when
     needed) — and re-access probability is exactly the closure math (window draws + tutor closure +
     recycle closure), per card class. The same code prices BOTH sides of a refresh: P(gain the hunt
     target) and P(lose access to the held cards). A held Energy with Energy Search copies in deck
     shuffles at ≈0 cost; a closure-unreachable one-of shuffles at ≈full role value. Role tiers
     already exist (wincon / line piece / tool / energy / dreg — the `_development_plan_set`
     vocabulary); joint multi-piece re-assembly is multivariate but computable; horizon defaults to
     next turn. Refinement en passant: the binary `irreplaceable_tool_in_hand` flag is DECK-RELATIVE —
     Hero's Cape is a Trainer, so a Petrel deck can re-fetch a shuffled ACE SPEC from deck; the
     closure computes per-deck what the flag hardcodes.
   - **Situational synergy — the genuine ML residue.** Combo adjacency/timing windows, sequencing,
     tempo, opponent-context ("they will Judge me anyway"). This part stays parked on
     ADR-0007/0042/0053.
   Revised ruling: mid-value classes (ability unlock, ACE-SPEC hunt, need-filling) unblock behind the
   **replaceability-floor keep-value**, shipped under the standard correction-corpus / score-diff
   gate, with the synergy residue a stated known error (replaceability plausibly dominates —
   irreplaceability is most of why shuffling hurts). Distinguish the `handCount`-overfit precedent:
   that was a raw SIZE scalar with no structure; this is role-priced and closure-derived — the
   corrections arbitrate, not a hand-fitted constant.

**Round 7 (user grill, 2026-07-17) — card worth is ONE marginal oracle, and the repo has four
disjoint shadows of it.** User ruling, CONCEDED after source-check: "what a card is worth" and "the
cost to shuffle/discard it" are not two problems — worth is only ever a **difference at a decision
point**: `worth(card | state, horizon) = best-plan(with) − best-plan(without)`. There is no absolute
card value, which is precisely what makes it computable: the situation enters through visible-state
gates, not through an oracle of taste. The codebase already proves the principle LOCALLY — ADR-0023's
fetch doctrine runs one shared value function behind whether-to-play / what-to-grab / what-to-discard
("agree by construction": `_grab_value_of` benefit side, `_pitch_value_of` signed cost side,
`_shed_signals` top-2 netting = exactly the user's Ultra-Ball trade) — but the repo holds **four
partial valuations that do not share a spine**: (a) the fetch grab/pitch rungs, (b) ADR-0060's flat
refresh prices (shed −8 flat, draw +20 flat), (c) the gamble's binary keep-floors, (d) the
develop-leaf plan-tier credit. Same card, same state, four answers. Unification target: one
**card-worth oracle** module (the ADR-0052 one-oracle pattern), consumed by all four sites + this
note's keep-value floor; existing rung weights seed the calibration; corrections arbitrate.

The closed-form ladder (the HOW): **role tier** (deck-declared: wincon / line piece / engine fuel /
energy / tech / dreg — exists, `_BASE_ROLES`/`_wincon_set`/plan-tier vocabulary, which measurably
lifted the leaf lab) × **gate proximity** (is the card's precondition live NOW: pre-evo in play →
evolution hot; typed energy deficit on a matching body → energy hot; Active doomed → switch hot;
discard empty → recycler dead — what the need-gated rungs encode piecemeal today) × **redundancy
discount** (visible copies + closure re-access, round 6) + **residue** (timing windows, sequencing,
opponent context — the true ML remainder, now small).

Corrections to the user's formulation, accepted into the design:
- **Sets, not sums.** Hand value is non-additive (a 2nd copy of a one-use Supporter ≈ dead; combo
  pairs superadditive — the doctrine itself already fights naive additivity: "a 2nd Dreepy is a 2nd
  LINE, not junk"). The Ultra-Ball discard pair is valued **jointly** (C(hand,2) pairs, cheap);
  `_shed_signals`' current top-2-independent pitch is exactly the naive form — an upgrade site.
- **Differences, not ratios.** Cost/benefit < 1 breaks at zero cost (free Items) and a good ratio on
  a tiny benefit still loses to a better menu option; the single tactical scale + menu argmax
  subsumes the ratio test. Net = benefit − cost, ranked against the menu.
- **Signed by zone and deck.** Kyogre (721, verified text) counts Basic {W} Energy IN THE DISCARD as
  attack fuel — for that deck, pitching W Energy has NEGATIVE cost (it is progress). Only a
  deck-declared, role-aware valuation flips that sign; recycle reachability (round 6) makes discard
  partially recoverable everywhere else.
- **The Lillie's formula grades ADR-0060.** Hand total X (set-corrected marginal worths) vs
  `E[n random] = n × deck-mean marginal worth over the remaining decklist` — computable, and it
  auto-derives ADR-0060's deferred "a spent deck returns dregs" (deck-mean falls as the deck spends).
  ⚠️ Blast radius: ADR-0060's flat asymmetry was deliberately calibrated against the keep-guard
  family after the +76 blowthrough incident — the graded swing REPLACES that calibration and must
  re-audit it under the correction corpus, not bolt on beside it.

**Round 8 (user grill, 2026-07-17) — gate proximity is a DEADLINE, not a multiplier; the horizon is
owned by role tier + hard rungs.**

1. **The proximity-multiplier table (live-now ×1.0 / next-turn ×0.7 / cold ×0.3) is REFUTED before it
   was built.** Shuffling a next-turn-live card doesn't cost a fraction of its worth — it costs
   `role value × P(can't have it back by when the gate opens)`. Same card, same proximity, opposite
   costs depending on the closure between now and the deadline (Mega Lucario in hand, Riolu benched
   this turn: cheap to shuffle with 2 Mega Signal + Ultra Ball live, near-catastrophic with them
   spent). Proximity is the **deadline parameter of the re-access probability** — hot = short window
   = high cost, derived, zero new constants.
2. **Resource quotas are gates**: 1 attach/turn gives the k-th held copy of a class deadline k−1 —
   the 3rd hand Energy is near-free to shuffle because two turns of draws+closure stand before its
   deadline. Derives the intuition instead of asserting it.
3. **Gates CLOSE as well as open** — use-it-or-lose-it (the KO window, a pre-evo the threat read
   prices as dying). A gate is an interval [opens, closes]; a closing edge SPIKES keep-cost — decay
   constants are wrong-shaped for cliffs. Closing edges come from existing machinery
   (`reachable_incoming`).
4. **The ladder COLLAPSES.** Role × proximity × redundancy was pedagogy; the computation is one
   marginal probability difference per class:
   `keep-cost(X) = role value × [P(class need met by deadline | keep X) − P(met | shuffle X)]` —
   redundancy and proximity both live inside the same closure query, and it is the SAME math as the
   gamble's gain side pointed backwards. The oracle got simpler under grilling (the right-primitive
   sign).
5. **Held-card risk (new seam, tier-2):** holding across k opponent turns exposes the card to THEIR
   symmetric refreshes (Judge/Harlequin); P(stripped before my deadline) from the matched Read's rep
   build minus tracker-observed plays (`copies_left_odds` pointed at their disruption count). Prices
   fetch-early (certainty now, exposure till deadline) vs fetch-late (no exposure, re-access risk) —
   both sides closed-form.
6. **Horizon discipline: the oracle refuses to price the match.** Provably match-deciding cards are
   the hard rungs' jurisdiction (lethal solver / loss rung / win rung, KO_SCORE scale, outrank leaf
   math by construction); the oracle prices ONLY the positional band, and worth-to-the-match enters
   through role TIER alone — bounded, already encoded. No match-importance multiplier, no blanket γ:
   enumerate the computable risks (stripped, gate-closes) instead; a residual γ only ever ships as
   one tuned seed under the score-diff gate. This is the structural guard against a +76-class
   runaway recurring in the new currency.

**Round 9 (user grill, 2026-07-17) — where base values and deadlines COME FROM: declare identity,
derive everything else (the Meowth-ex lesson).** The general oracle must stay deck-agnostic while
deck-genie walks each card; the split follows the existing `ROLES` overlay + `Lines` mechanism and its
recorded misfire (mega_lucario: a declared `tutor` Role benched the 2-prize Meowth ex; the fix was
REMOVING the declaration for the general `supporter_tutor` tag — a wrong declared fact is worse than
none):

1. **Base value = one general tier table** (role → points, tuned under corrections, one currency
   zone; deck-genie NEVER invents numbers) **× mostly-derived roles**: wincon/line pieces from the
   declared `Lines` (payoff/path + forward index), engine from Function Tags, energy fit from the
   deck's attack costs. Deck-genie declares only the sparse identity residue (which lines are the
   plan; intentional roles the derivation can't see) — what `ROLES` already is.
2. **Deadlines are never authored** — runtime state, evaluated by a general **gate library** keyed by
   card class: evolution gate (`evolvesFrom` + Line), quota gate (k-th copy → deadline k−1),
   recycler gate (discard nonempty), pressure gates (switch/heal ← threat read). The deck data only
   has to make every card's gate RESOLVE.
3. **Synergy: derive the majority** (a tutor's held value = the closure-reachable value, recursively
   free; line adjacency from `Lines`; type fit from costs); **declare the residue** — text-effect
   synergies (Kyogre's discard-fuel sign flip, hand-size attackers) in one sparse `SYNERGIES` overlay
   sibling of `ROLES` (`{cards/class, zone, effect, rationale}`). If SYNERGIES grows dense, that is
   the ADR-0034 fold signal: a general vocabulary term is missing.
4. **Pipeline**: deck-genie's card walk gains a **Role Sheet** output (derived role confirmed or
   overridden + gate type + SYNERGIES entries, each grilled against the derivation: "the general
   layer would say X; overriding because…") → Strategy Proposal (ADR-0046) → `/update-strategy`
   compiles the overlay → `/deck-align` re-audits as `common/` vocabulary grows (ADR-0036).
5. **Guardrails**: a CI coverage lint (every `deck.csv` card resolves to a role, derived or declared
   — no card silently priced at zero, the Scouting-gate pattern); declarations are corrections to the
   deriver, never a parallel system.

This oracle outgrows this note — when built it earns its own ADR; it is recorded here because the
grill produced it and the closure supplies its redundancy leg.

**Information value of the FIRST whole-deck search (user grill, 2026-07-17).** `OwnCardModel` resolves
the prize split exactly only once a search reveals the whole deck (ADR-0029/0023). So the first
deck-revealing fetch pays twice: the card, plus anchoring the tracker — collapsing every later
consumer (gamble classes, whiff veto, closure counts, deck-emptiness) from hypergeometric to certainty
for the rest of the match. Seam: a small, bounded first-reveal credit on deck-revealing searches —
kept well below a real fetch need so we never dig just to peek (the ADR-0023 over-play risk); at
minimum, tie-break equal fetch lines toward the one that anchors.

## Grill checklist → build checklist (verdicts as of 2026-07-17; ✅ = BUILT 2026-07-18, suite-green)
- [x] ✅ **WP1** Outs count **tutor-closure entry points** — BUILT (`_ENERGY_FETCH_ITEMS` +
      `_fetch_reaches_slot`: Item energy-tutors join the class outs, verified against card text).
- [x] ✅ **WP1** Closure includes the **recycle/discard branch** — BUILT (Night Stretcher / Energy
      Retrieval / Max Rod, from the visible discard; a class can now EXIST via the recycler alone).
- [ ] **Hand-expansion** chains modeled — not built (first expansion only, via the Gamble window itself).
- [~] **1 Supporter / 1 attach / costs** charged along the chain — WP1/WP5 scope Items only (the
      refresh spends the Supporter slot); the Supporter-post-Unfair-Stamp branch is deferred.
- [x] ✅ **WP2** Entry-window × prize-split composition (NOT per-hop draws) — BUILT (`_prize_split_hit`).
- [x] **Exact tracker when revealed, hypergeometric on counts** — already the codebase shape
      (`deck_known_counts` / `p_contains` collapse, ADR-0029 §3).
- [x] ✅ **WP2** **Pre-anchor gambles NOT stood down** — BUILT: the `if not deck_known_counts: return
      None` gate is replaced by the prize-split-weighted window sum (`_prize_split_hit`, ≤ u+1 terms).
- [ ] **First-reveal information credit** — bounded, tie-break-level; never dig just to peek.
- [ ] **WP4** **Engine depth = board-supported capacity** (eligible pre-evo/engine pairings), not a
      hardcoded one stage; window-2 outs are the full Stage-1 union, not literal Energy.
- [x] ✅ **WP5** **Evolution-KO class** added to the gamble rung (`_gamble_evolution_ko_classes`: the
      Active's eligible evolutions' attacks, Energy carried over, Item Pokémon-tutor closure) — BUILT.
- [ ] **Survival class** (avert the ADR-0064 predicted-loss shape via `switch`/`heal` closure) —
      KO_SCORE-scale, exempt from the keep-value blocker.
- [ ] **Replaceability-floor keep-value** — cost of shuffling = Σ role value × (1 − re-access odds via
      the closure); unblocks the mid-value classes under the correction/score-diff gate; synergy
      residue stays on the value model (ADR-0007/0042/0053).
- [ ] **One card-worth oracle** (rounds 7–8): marginal (with-vs-without), set-capable, zone/deck-signed
      (Kyogre discard-fuel flip); keep-cost = role value × ΔP(class need met by DEADLINE | keep vs
      shuffle) — proximity is the deadline (quota-aware, interval-valued for closing windows), never a
      multiplier; horizon = role tier only, match scale stays with the hard rungs; unifies fetch
      grab/pitch, refresh swing, gamble keep-floors, and the plan-tier credit — graduates to its own
      ADR at build time.
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

## Round 10 (user, 2026-07-17) — build addendum: the correction-seeded test corpus, the module home,
## and the skill loop

**The whole grill is one subsystem: shuffle + fetch/discard economics.** Three build directives:

### 1. Tests seeded from the TAGGED BLUNDERS, not invented scenarios
The correction corpus (`data/corrections/*/corrections.jsonl`) holds ~70 shuffle/fetch/discard
corrections that ARE the acceptance suite. Repo pattern applies: replay the REAL recorded state
through the real `decide()` (the `test_critical_*` shape), assert the correct pick outranks the
blunder; join against `reviewed.json` dispositions first (refuted/covered corrections don't become
fixtures) and route via /blunder-buster classification. Families → design components:

- **Discard-pair valuation (sets, not sums; role floors):** 82525101-f14 (kept Ignition? never
  Ultra-Ball it away; pitch the duplicate Wally's), 82749656-f20 (pitched the ACE SPEC Hero's Cape),
  83661652-f30/f31 (pitched the main-line attacker; **discarded a Riolu to fetch a Riolu**),
  83686860-f18 (pitched BOTH Dreepy — killed a line: the pair-valuation case verbatim),
  82867148-f48 + 83967840-f54 (duplicates-first), 85045840-f14 (pitched Drakloak to fetch Dragapult —
  discarded the line piece the fetched card NEEDS), 86091435-f68 (pitched a live-now Drakloak).
- **Fetch-target valuation (role × gate × closure):** 84890060-f26 (energy-over-body: the fetched
  Energy chains attach→retreat→KO), 82228640-f9 + 82753746-f11 (role-dead Cinderace — gate closed
  after opening), 84071010-f53 + 83686860-f33 (fetch the evolution with pre-evos EXHAUSTED — deadline
  permanently closed, tracker-known), 85058051-f13 (fetch = WIN, missed), 81903490-f8 (Ultra Ball
  hunts the wincon), 85059103-f9 (fetched a duplicate of a held card).
- **Whether-to-play / hold the fetch (deadline + held-card risk + whiff):** 83007714-f8,
  85045840-f12, 83967841-f17, 86091728-f19 (no need → hold), 83661652-f29 (basics can't evolve yet —
  hold a turn), 85163634-f17 (**fetch one turn early = Judge exposure** — the held-card-risk seam's
  own correction), 85164605-f64 (fetched into a known whiff), 82754241-f12 + 82525741-f78 +
  82524455-f6 (Poffin with Staryu line exhausted), 85046350-f79 + 85058574-f114 (dead fetchers become
  **Ultra Ball fodder** — a negative-cost discard role).
- **Shuffle timing & keep-value (the refresh side):** 83686860-f13 + 83661652-f40 (fetched a piece
  then SHUFFLED IT AWAY next decision — cross-decision sequencing), 83038055-f51 + 82752045-f94
  (strong hand → don't refresh; ">7 good cards" heuristic emerges from graded keep-value),
  82749168-f65 + 83969481-f55 (Ignition / Wally's valued by next-turn & match need), 82750161-f60
  (Harlequin 11-vs-2, the ADR-0060 anchor), 83037962-f49 (symmetric refresh returned our own
  Starmie+Energy), 82756664-f9 (USE the Cape, then refresh — play-before-shuffle ordering),
  83457493-f31 (pitch dead cards BEFORE the symmetric shuffle).
- **Discard-as-resource (zone-signed worth):** 85785067-f42/f54 + 85058574-f16 (Lunatone: discard
  Energy to draw 3 — Energy is FUEL here), 84071010-f45 (hold surplus Energy FOR Aura Jab's
  discard-recycle — the sign flip in our own deck), 85058051-f4 (Ultra-Ball back the spent Supporters
  to feed the engine).
CI-gated like the rest of the suite; every family lists its correction ids so coverage is auditable.

### 2. One module home — the oracle is a backend, the doctrines stay the deciders
Consolidate the sprinkled machinery behind ONE seam (the ADR-0052 one-oracle pattern — `combat.py`
is the model): a `common` **card-economics module cluster** — `fetch_closure.py` (the tutor/recycle
graph + text predicates), `card_worth.py` (the marginal oracle: role table, gate library, deadlines,
keep-cost), extending `deck_odds.py` (window + prize-split math stays where it lives). NOT a
doctrine deprecation: `doctrine_fetch` / `doctrine_shuffle_refresh` / the gamble rung keep owning
WHEN-to-decide (rungs, gates, telemetry) and become CONSUMERS of the shared value backend —
`_grab_value_of` / `_pitch_value_of` / `refresh.py`'s swing / the gamble keep-floors all call the
oracle instead of carrying private valuations. The four-shadow disagreement (round 7) dies by
construction; each flip lands under the corpus above + the score-diff gate, staged like the ADR-0064
five-call-site refactor.

### 3. The skill loop closes it
Round 9's Role Sheet contract: **/deck-genie** authors roles/synergies for NEW decks;
**/deck-align** re-audits the three existing agents (mega_starmie, mega_lucario, dragapult_ex)
against the new vocabulary — their STRATEGY.md deck rules that merely restate what the oracle now
derives (fodder lists, "never Ultra-Ball the Ignition", duplicate-first pitching) FOLD into the
general layer per ADR-0034, shrinking deck files as the system generalizes.

## Round 11 (user, 2026-07-17) — tag completeness audit of the three decks: DONE, applied, suite-green

**Ruling.** The card representation must be complete WITHOUT a new text-consuming system — and the
repo already has the two designated tiers: Function Tags stay coarse boolean routing triggers
(ADR-0006), and parametric predicates (target type/class, counts, destination, costs, conditions)
belong in the BUILT `card_effects.json` Effect-Clause tier (ADR-0032: "a mechanic is encoded when a
Tier-0 consumer would blunder without it" — the closure is now that consumer). Tag fixes enter via
`tools/meta_tracker/function_overrides.json` (curated, never clobbered by probe rebuilds).

**Audit: all 50 unique cards of mega_starmie / mega_lucario / dragapult_ex, text vs tags vs clauses.**

*Boolean lapses — FIXED (overrides + shipped table, additive only):* 140 Fezandipiti ex `+draw`
(Flip the Script), 305 Dunsparce `+switch` (Trading Places; Samurott precedent for attack-based),
674 Hariyama `+gust` (Heave-Ho Catcher on-evolve), 675 Lunatone `+draw` (Lunar Cycle — the probe
can't stage its Solrock+hand-energy precondition), 1142 Fighting Gong `+tutor_pokemon` (fetches a
Basic {F} Pokémon — the user's own example), 1152 Poké Pad `+tutor_pokemon`, 1225 Hilda
`+tutor_pokemon` (fetches an Evolution Pokémon).

*Verified NOT lapses (right tier already):* 1141 Premium Power Pro / 1211 Black Belt's →
`CardStat.damageBoost` + TransientTracker; attack riders (Aura Jab, Jetting Blow, Phantom Dive,
Tuck Tail, Wild Press recoil) → the AttackStat tier; 676 Solrock — no draw of its own.

*Recorded decisions (deferred with reasons):* attack-based accel (678 Aura Jab, 666 Turbo Flare)
goes to the ATTACK tier, NOT card tags — the ADR-0064 burst-budget scan reads `energy_accel` tags
and attack-based accel must stay excluded from one-step budgets (a card tag would corrupt the scan);
1122 Pokégear's `draw` tag is loose (it digs, supporter-only — predicate to clause); 17 Ignition's
{C}{C}{C}-on-Evolution → an `energy_provide` clause (ADR-0064 hardcodes this knowledge today);
1252 Gravity Mountain / 1260 Risky Ruins have NO representation (stage-2 −30 HP shifts KO math; a
CardStat-parsed field like `damageBoost` is the recommended shape); 121 Dragapult ex benched-
immunity = the known CardStat gap (rules.md §11).

*Clause backlog (the card_effects.json extension the closure consumes — replaces
`doctrine_fetch._FETCH_FILTERS`, the FIFTH private valuation shadow):* fetch/tutor predicates for
1086 (≤70-HP Basics ×2 → BENCH), 1097/1110/1118 (recycle targets), 1121 (any Pokémon, cost
discard-2), 1122, 1142 ({F}-locked), 1145, 1152 (no Rule Box), 1189 (no-Ability evolution,
timing-exempt), 1198 (2 different-type Basics, 1 → attached), 1219, 1225 (evolution + ANY energy
incl. Special), 1071 (Supporter, on-bench-play trigger); draw-engine clauses for 66 (3 +
self-shuffle), 120 (top-2-take-1), 140/675 (conditional), 1080 (5/2, post-KO gate); accel clauses
for 666/678 (via attack)/1240 (discard→Stage-2, prize-behind gate); 1120 (coin).

**The consumer recalibration (the round-7 currency-zone warning, live).** Three pinned tests flipped
— each because a consumer was calibrated against the INCOMPLETE data: (1) `_is_draw_engine_body`
test had pinned "Lunatone untagged" as ground truth — re-baselined, and `dont-power-the-draw-engine`
is now LIVE on mega_lucario, exactly what corrections 85785067-f42/f54 + 85058574-f16 demanded;
(2) `dig-before-commit` (+20) endorsed BENCHING Lunatone over the wincon base (ml0703 f44) — fixed:
the rung stands down on Pokémon plays (benching a body whose ability draws later is not a dig;
Meowth ex is owned by `bench-the-supporter-tutor`); (3) `fetch-the-support` (+15) newly stacked with
mega_lucario's `fetch-the-missing-engine-half` (+22) to 49, out-ranking the +35 famine Energy and
re-opening ml0705 f9 — fixed: famine stand-down, honouring the rung's own "second only to
energy-when-starved" charter. One synthetic fixture re-powered (the famine gate needs a powered
Active it never modelled). Bonus: `use-the-draw-engine-ability` (+18) now fires on Lunar Cycle —
corrections-aligned. **Suite: 2941 passed, 13 skipped** (the 2 excluded files are a pre-existing
plotly environment gap, failing identically on the clean tree).

## Round 12 (user, 2026-07-17) — class-generality verification: the system is typed by TARGET
## CLASS, never "target = Energy"

Verified: the Energy examples were pedagogy, not architecture. Every layer is already
class-parameterized — the closure graph's edges are typed (`tutor_pokemon` / `tutor_mega` /
`tutor_trainer` / `supporter_tutor` / recycle's "Pokémon or Basic Energy"; Petrel is the universal
Trainer hop), the window/prize-split math counts ANY card class, keep-cost is defined over "class
need met by deadline" for any class, role tiers span all card types, and the correction corpus is
class-diverse (Riolu/Mega Starmie fetches, Wally's/Boss's keep-value). Rounds 5's classes already
target non-Energy (evolution-KO = Pokémon; survival = Trainer).

**Amendment that makes it explicit: outcome classes are an ENABLER TAXONOMY, "exactly one enabler
short," typed per class — each with the same void-if-in-hand rule, det baseline, and legality gate:**
- **Energy-attach** (built today) — slot-typed, attach-capacity-gated (round 3).
- **Evolution** (round 5) — eligibility-gated; closure via Ultra Ball / Mega Signal / Hilda / Poké Pad.
- **Gust** — the KO exists but the real target is BENCHED: drawing Boss's Orders (or closure: Petrel →
  Boss's) enables it. Gate: my affordable attack ≥ the benched target's HP.
- **Damage pump** — short by ≤ the boost: `CardStat.damageBoost` with its `damageBoostType`
  ({F}-only) and `damageBoostVsEx` gates — VERIFIED parsed (provider.py:97-100), so the class
  never over-credits a type-locked pump.
- **Switch/heal** (round 5 survival) — Trainer outs, threat-read-gated.
- **Bench-fill** (anti-donk survival) — bench empty + Active doomed: ANY Basic is an out, and
  Buddy-Buddy Poffin's destination is the BENCH directly (the closure's destination distinction).

## Round 13 (user, 2026-07-17) — the DEVELOPMENT gamble (third family) and the to-gamble threshold

**Not only "one enabler short of KO/survival."** The enabler taxonomy (round 12) lists the KO and
survival families because their value dwarfs keep-cost; the THIRD family — the **development
gamble** (refresh/dig to find a plan piece: Cinderace active, empty bench, payable Turbo Flare →
hunt a Staryu; Solrock leading → complete the Lunar Cycle pair) — is the rounds-5/6 mid-value class,
unblocked by the replaceability keep-value floor and riding behind it.

**It staples on GENERALLY — deck declares identity, machinery derives the gamble.** The Staryu case
prices with zero new deck rules: worth = the declared Line base (role `win_condition`, top tier);
gate = Turbo Flare's accel clause (`target: bench_only`) meeting an empty bench — the deck's engine
attack is firing blanks, a derivable "recipient needed NOW" signal; exposure = bench-empty as a
standing loss condition (loss-rung composition); outs = Staryu + Poffin (bench destination) + Ultra
Ball via the standard closure (illustratively ~65% on a 6-card Lillie's, ~40-card deck, 6-7 outs) —
× top-tier benefit − dead-hand keep-cost ⇒ "basically always," DERIVED. The Lunatone case is the
same formula one tier down (SYNERGIES-declared engine pair, half-open gate, engine-tier benefit) ⇒
"desirable at reasonable odds when the hand is cheap" falls out of tier ordering. Deck-specific
hypotheses remain only for what derivation can't see; today's `fetch-the-missing-engine-half` deck
rung is the fold-target precursor of the SYNERGIES declaration.

**The threshold is the EV comparison, never a fixed probability bar:**
> gamble iff **P(assemble) × benefit − keep-cost(shuffled hand) > best deterministic line on the menu**
— one currency (rounds 7-8). The bar moves correctly by itself: big benefit → long odds acceptable;
precious hand → higher bar; rich deterministic option → higher bar; dead hand + stalled board →
near-zero bar. Only the role-tier values are tuned constants; the hard rungs stay above (never
gamble past a deterministic KO; famine ordering holds). The graded keep-cost is what makes this
family safe — without it, "P × moderate benefit" beats a mispriced free shuffle far too often
(the 83686860-f13 Drakloak-then-Lillie's blunder class).

## Round 14 (user, 2026-07-17) — gamble observability: BUILT, suite-green

**The gamble rung now emits its full working to stderr, and the blunder shell shows it as a
dropdown.** `_best_gamble_line` records `self._gamble_trace` — either the complete pricing (pool,
det baseline, burst copies, every outcome class with its **sought out-card ids**, per-option
p·EV rows, the committed best) or the exact **stand-down reason** (feature off / turn 1 / attach
spent / active already KOs / KO on menu / each protected-hand gate separately / pre-anchor / no
one-short class). Never recorded mid-sim (engine re-runs can't clobber the live trace); cleared per
plan fingerprint. It rides `Decision.gamble` → the sparse `"gamble"` key of the `@T` stderr record
(`telemetry.to_record`, ADR-0019) → joins each frame's `live_trace` in the tagging shell → a
`<details>` dropdown: "🎲 gamble: priced — fired/declined · det · pool" with the classes (cards
sought) and per-option pricing, or "🎲 gamble: stood down — <why>". A shuffle-in / Ultra-Ball
correction can now target the real defect (outs undercounted? det wrong? a gate too eager?) and
/blunder-buster reads the same record from the correction's `live_trace`. Pinned by
`test_gamble.py` (trace on fire: classes+sought+p ranges+wire record; exact stand-down dicts for
pre-anchor and feature-off). Suite 2940 passed. As the Stage-1/2 closure and the new outcome
classes land, they extend THIS trace (closure outs appear in `sought`; new classes appear in
`classes`) — observability is now a build invariant, not an afterthought.

## Where it plugs in (corrected)
**Priority:** the Gamble Rung's Outcome Classes (`_gamble_ko_classes`, ADR-0039) — v1 above — then the
probable-whiff generalization (ADR-0029) and win-odds/lethal reach. **Deferred behind ADR-0064:** any
probabilistic relaxation of the survival ceiling (must price the closure), and the matched-Read safety
read's recycle blindness. Tags index the graph (`src/common/card_functions.json`); predicates come from
card text (`data/EN_Card_Data.csv` / the ADR-0032 compendium when built).
