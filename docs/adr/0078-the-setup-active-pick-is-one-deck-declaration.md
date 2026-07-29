# ADR-0078 — The Set-Up Active pick is one deck declaration, not a pile of derived rungs

**Status:** Accepted (grilled 2026-07-28, `/grill-with-docs` on Issue #161 — nine locked decisions).
Build: Issue #161. **Authored as 0075, renumbered 0075 → 0077 → 0078 across two rebases
(2026-07-29)** — ADR-0075 (the KO oracle's typed Budget), ADR-0076 (the opponent-target slot family)
and ADR-0077 (a ranked count consumer reads `expected`) each reached `main` while this branch was
open. All are strategy ADRs, so the README's tooling-moves-first rule never applied and the 0071/0072
precedent governed each time — first-merged keeps the number. The commit history and the Issue #161
comments therefore say 0075; this file is the same ADR. **Overturns** the 2026-07-15 evolve grill's Ruling 5
(`docs/plans/evolve-valuation-grill-spec.md`) in its remaining half, and completes
**ADR-0070 §4**, which re-ruled `f2` out of the evolve decider's scope and parked it as "a placement
follow-up". Applies **ADR-0034** (deck rules fold general when the vocabulary is general) and
**ADR-0046** (analysis proposes, one skill applies).

**Context issues:** Issue #161 (this grill / build), Issue #140 (Phase 1b, which re-ruled `f2` out of
scope), Issue #197 (the pregame **Bench** sibling, split out by decision 9).

## Context

`f2` (`dp_open_utility_over_fragile_line_base_f2`) has sat `xfail(strict)` in
`tests/strategy/test_evolve_valuation_corpus.py` since 2026-07-15, labelled "exposure / opener
(line-shape)", waiting on an equation that structurally cannot reach it: it is a `_SETUP_ACTIVE`
placement decision, off the `_EVOLVE` path. ADR-0070 §4 struck the exposure term for the second time
and re-ruled the frame out of scope. This ADR is where the frame is actually addressed.

Three findings from this grill reshaped the issue as filed.

**1. The decision is silent, not wrong.** Running the shipped Pilot on the `f2` observation:

```
opt[0] card=119 Dreepy     score=0.0  fired=[]
opt[1] card=112 Munkidori  score=0.0  fired=[]
opt[2] card=119 Dreepy     score=0.0  fired=[]
```

Nothing fires; Dreepy wins on the option-index tie-break. This is bit-for-bit the failure recorded
in mega_lucario's `start-solrock-over-lunatone` rationale — *"Both score 0, so the option-index
tie-break opened Lunatone (ml f1: CRITICAL)"*. **Two decks, two frames, one root cause:** the
Set-Up Active seam does not rank the field.

**2. The issue's own prescription is refuted by card data.** Ruling 5 specified the opener term as
`hops_to_payoff × can't-attack-now × slot-threat`, and `f2`'s fixture note reads *"Dreepy (2-hop,
**no attack**)"*. Verified at source in `data/EN_Card_Data.csv` (2026-07-28):

| card | HP | retreat | attack | hops to payoff |
|---|---|---|---|---|
| Dreepy (119) | 70 | 1 | Petty Grudge `{P}` **10**; Bite `{R}{P}` 40 | 2 (→ Drakloak → Dragapult ex) |
| Munkidori (112) | 110 | 1 | Mind Bend `{P}●` **60** + Confused | 0 (final form) |
| Riolu (677) | 80 | 2 | Accelerating Stab `{F}` **30** | 1 (→ Mega Lucario ex, 340 HP) |

Dreepy **can** attack. `can't-attack-now` is `False` on the very frame the term was designed for, so
the prescribed product is zero, and the factor does not separate Dreepy from Riolu — both are
1-Energy attackers and both are Line bases. The real separators are HP (110 vs 70) and damage
(60 vs 10), i.e. body quality in the exposed slot, not line shape.

**3. The seam already had five scoring rules and one dead declaration.** Four general rules in
`src/common/strategy/baseline/baseline_opening.py` (`open-the-accelerator` +40,
`open-the-item-lock-starter` +35, `dont-open-multiprize-active` −15, `dont-open-with-the-engine` −12)
plus **`start-solrock-over-lunatone` (+12), gated on `c.card_id == SOLROCK`**
(`src/agents/mega_lucario/strategy.py:118`) — a live instance of exactly the card-id reflex the issue
warns against. Meanwhile the `starter` **Role** (`context.py:87`, *"card the deck intends to open
with"*) influences nothing at this seam: its sole consumer is `_hand_startable` → the `_MULLIGAN`
rung, and `docs/rulebook.txt:224` states *"If either player has no Basic Pokémon in their opening
hand, that player must take a mulligan"* — so a hand holding a Basic never reaches the prompt. Every
`starter` declaration in the repo is either a Basic (dragapult Budew; grimmsnarl Snorunt + Budew;
mega_starmie Staryu) or Cinderace, which already carries the `opener` Tag (*"If this Pokémon is in
your hand when you are setting up to play, you may put it face down in the Active Spot"*). The Role
is dead code.

Other facts verified at source and load-bearing below: a player going first cannot attack or play a
Supporter on turn 1 (`docs/rules.md` §first-turn); no Pokémon may evolve on either player's very
first turn (`docs/rules.md:96-97`); the Hypothesis layer scores strictly boolean —
`score = sum(w for _h, w in fired) + tactical` (`pilot.py:1725`), with `when(ctx) -> bool` and a
scalar `weight`, so there is **no multiplier surface**.

## Decision

**1. Opener value is a DECK DECLARATION read by a card-id-free general rule — not a derived term.**
`Strategy.starter_priority: list[int]`, an ordered list of card ids, mirroring the two existing
precedents for deck-declared data consumed by general logic: `Strategy.fetch_priority`
(→ `board.top_fetch_priority_id` → `fetch-deck-priority`) and `Strategy.partners` (*"Deck-declared
data (ADR-0034); the general attach oracle reads it"*). The Pilot resolves the highest-ranked id
present among the `_SETUP_ACTIVE` options into `board.top_starter_id`; `Context.card_is_top_starter`
exposes it; one general Hypothesis `open-the-declared-starter` reads that boolean.

This satisfies the issue's "never a card-id" constraint on the reading that matters: **the constraint
governs the trigger, not the declaration.** `roles` is already a card-id-keyed dict. Ruling 5's
derived line-shape term is rejected outright — refuted by Context finding 2, and a derived placement
term is the third attempt at what ADR-0070 §4 struck twice.

**2. The declaration SUBSUMES the seam — all five scoring rules are DELETED.** Not folded into a
successor rung, not left as guards: deleted. `open-the-accelerator`, `open-the-item-lock-starter`,
`dont-open-multiprize-active`, `dont-open-with-the-engine`, and mega_lucario's
`start-solrock-over-lunatone` all retire with migration NOTEs naming `open-the-declared-starter`.

The positives were deck opinions expressed *by proxy* (a Role, a Tag) and a declaration states the
same thing directly and in order. The negatives are derived heuristics standing in for a deck opinion
that is now explicit — and a guard that second-guesses a complete, deliberate ranking is not a safety
rail, it is an override of deck intent. Deleting them also removes the accidental cross-rule ordering
nobody ever grilled: a deck holding both an `accel_source` and an `item_lock` body had its opener
decided by `+40 > +35`, a comparison between two independently-tuned numbers.

**3. The declaration is a FLAT ordered list; first/second conditionality awaits a frame.** dragapult
records `preferred_start="second"` because Budew's Itchy Pollen fires T1 going second and only T2
going first, but its STRATEGY.md never names an *alternative* opener for going first. No deck has
been grilled into a coin-toss-dependent order, and no `Board` field exposes which side goes first
(the Pilot proxies it as `board.turn <= 1`). A two-key `{first, second}` schema would ship a branch
no deck exercises plus a Board field nothing else reads. Per the discipline ADR-0069/ADR-0070 both
close on, the refinement awaits a frame — and decision 6's question bank asks for it explicitly, so
the frame will surface if it exists.

**4. The `starter` Role is RETIRED.** `_STARTER_ROLE` leaves `_hand_startable` (the `opener` Tag
provably covers the only live case) and `context.py`'s exports; `"starter"` is stripped from the
three deck files that declare it, their comment prose carried across to `starter_priority`. Two
vocabularies for one concept is the ambiguity decision 2 deletes at the rule layer, and keeping a
decorative declaration beside a load-bearing one desynchronises at the first edit.

**5. Selection is BOOLEAN top-present, made exactly correct by a CI COMPLETENESS INVARIANT.** Not
rank-scaled. At any small rank scale the surviving guards would have dominated — but more durably:
`_SETUP_ACTIVE` is a forced single pick (`minCount 1`, `maxCount 1`), so argmax reads only the
winner, and under a complete list boolean and any monotone rank scale choose **identically**. Rank
scaling's one genuine merit — graceful degradation when only a low-ranked starter is present, where
"top present" promotes it to full weight — exists only under an *incomplete* list. The cheaper fix is
to forbid that state: a test asserts, for every agent, that `starter_priority` is **non-empty** and
**ranks every startable body** in the deck list (a Basic, or an `opener`-tagged card). Rank scaling would also demand
either N Hypothesis ids or the `tactical` computed-term lane, i.e. a second scoring mechanism at the
seam this ADR reduces to one.

With decision 2, this invariant is the **sole** guarantee for the whole seam: an undeclared deck has
nothing at `_SETUP_ACTIVE` and falls straight back to the index tie-break — the `f2` bug, for every
deck.

> **Amendment E (build, 2026-07-28) — how the invariant is actually drift-proofed.** The pre-build
> wording above claimed the completeness predicate is "the same predicate `_hand_startable` uses". As
> built that is not true and could not be: `_hand_startable` answers a deliberately NARROWER question
> (can this hand start *without* a Basic — the only case the mulligan prompt can reach), while the
> invariant needs the full Basic-or-`opener` universe. Shipping one predicate for both would have made
> `_hand_startable` trivially true on any hand containing a Basic.
>
> The drift-proofing that does exist, and is the one that matters: the **Ability route** into the
> Active Spot is defined exactly once, in `Pilot._opens_from_hand`, and both readers derive from it —
> `_hand_startable` is that predicate alone, `_is_startable_body` is "a Basic, or that". And
> `_is_startable_body` lives on the **runtime**, not in the test that consumes it, because the
> invariant is only worth anything if it measures the declaration against what the engine can
> actually offer; a re-implementation inside the test would be free to drift, which is the failure
> the invariant exists to prevent. It returns False on unknown stats, so the test additionally asserts
> a non-empty startable set — otherwise a stats-loading failure would satisfy the subset checks
> vacuously and the invariant would go green while measuring nothing.
>
> **Amendment A (build, 2026-07-28) — the invariant scopes to AUTHORED agents.** It applies to every
> agent carrying a `STRATEGY.md`, the marker of a deck-genie'd doctrine. `grimmsnarl_ex` (no
> STRATEGY.md, no `aligned.json`, no `tuned.json`) and `slowking` (a decklist only) are pre-doctrine
> and exempt — the same line `/deck-align` already draws ("a deck with no real `strategy.py` is
> deck-genie's job first — report it, don't align it"). The exemption is asserted **explicitly** in
> the test, not left implicit, so adding an agent cannot silently opt out. **Accepted regression:**
> until it is authored, `grimmsnarl_ex` loses the opener guidance it has today (`+35` on Budew, the
> two guards) and its Set-Up Active pick falls to the option-index tie-break. It is a pre-doctrine
> agent with no recorded opening doctrine to transcribe; decision 10's `/deck-align` drift check is
> what surfaces it.

**6. `open-the-declared-starter` seeds at 40 — for band legibility, not calibration.** With one rule
at the seam the weight interacts with nothing and any positive value is behaviourally identical.
40 is the `docs/weights.md` "strong preference — core doctrine" band whose cited exemplar
(`open-cinderace = 40`) is this rule's ancestor, and it preserves mega_starmie's Cinderace value
exactly. Per-deck strength goes to `weight_overrides` (ADR-0035), never into the seed.

**7. The seam gets ONE test file.** `tests/strategy/test_setup_active_placement.py` absorbs and
retires `test_setup_active_multiprize.py` (carrying `REQ-OPEN-0002` to the successor), and holds four
groups: the `f2` fixture assertion, the two rewritten legacy behaviours, and the decision-5 invariant.
The legacy tests are rewritten as **outcome** assertions (which body ends up Active), never score
assertions, so they survive the currency change. **`f2` lands PASSING, not `xfail`** — dragapult's
declaration is in scope, so an `xfail(strict)` would XPASS and hard-fail, which is the exact
dishonesty Issue #161 opens by complaining about. Its fixture's `claims` entry (`"owner": "#161"`)
resolves to the shipped ruling.

> **Amendment C (build, 2026-07-28) — `test_budew_sacrificial_starter.py` is AMENDED, not retired.**
> This ADR over-stated it before the code was read. Only one of that file's three tests was about
> this seam; the other two (`worth 0`, `never a funding target`) are Budew *identity* claims under
> `REQ-WORTH-0003` and are untouched. The opener BEHAVIOUR moved to the placement file; the Role
> assertion was rewritten in place as a `starter_priority` rank-1 assertion. `REQ-GEN-0056` likewise
> re-points from the deleted `open-the-accelerator` to `open-the-declared-starter` inside
> `test_general_strategy.py`, the natural home for a per-general-rule unit test, rather than moving.

**8. The four declarations are authored through the ADR-0046 proposal pipeline, and the change lands
ATOMICALLY.** Authoring four decks' opening doctrine *is* strategy authoring: `/deck-align` per deck
emits a `starter_priority` Strategy Proposal (`target_layer: deck-strategy`,
`verification_contract: score-diff`); `/update-strategy` authors and gates it. mega_lucario's
additionally folds `start-solrock-over-lunatone`. Running the decision-6 bank four times is also the
only honest test that it produces a usable ordering. Because decision 5's invariant fails the moment
the rules are deleted without declarations present, the rule deletions, the fold, the four
declarations and the invariant have **no green intermediate commit** — they land as one change.

> **Amendment B (build, 2026-07-28) — the orders are TRANSCRIBED from shipped doctrine in-build, not
> re-grilled.** The atomicity requirement makes a stop-at-fodder pass deliver nothing, so the three
> authored decks' orders were derived in the build turn and confirmed by the user before being
> written. This is not a weakening of ADR-0046: its concern is *unreviewed* executable authoring, and
> the orders were reviewed before authoring rather than after. Crucially the orders **encode the very
> rules being deleted**, so `score_diff` in `choice` mode is a real gate — a divergence means the
> transcription is wrong, not that doctrine changed. Landed orders:
>
> | deck | `starter_priority` | provenance |
> |---|---|---|
> | `mega_starmie` | Cinderace → Staryu | `open-cinderace`/`open-the-accelerator` (+40); Staryu is the wincon basic, belongs benched |
> | `mega_lucario` | Solrock → Riolu → Makuhita → Lunatone → Meowth ex | `start-solrock-over-lunatone` (+12, ml f1); the open-Riolu constraint; `dont-open-with-the-engine` on Lunatone; `dont-open-multiprize-active` on Meowth ex (REQ-OPEN-0002) |
> | `dragapult_ex` | Budew → Munkidori → Dunsparce → Fezandipiti ex → Dreepy → Meowth ex | `open-the-item-lock-starter` (+35); `f2` (Munkidori ≻ Dreepy); **user ruling 2026-07-28** — Dreepy ranks 5th, *below* a 2-prize Fezandipiti ex, because the Line base is wanted on the BENCH (`develop-the-wincon-base-first`), not merely tolerated in the Active Spot |
>
> The dragapult order is the one that could not have been derived mechanically: a naive "fragility +
> prize-liability" read puts Dreepy above both ex's. The doctrine is the opposite — an Active Dreepy
> is a *misplaced* Line base, which is worse than exposing a body the deck can afford to lose.

**9. Active only. The pregame Bench is out of scope → Issue #197.** `_SETUP_BENCH` (SelectContext 2)
has seven rules in `baseline_bench.py` and **no motivating frame**, and the design does not transfer:
"highest-ranked present" is single-winner, the Bench is a multi-pick. `f2`'s bench half — Dreepy
belongs on the Bench — is already covered by `develop-the-wincon-base-first`.

**10. `/deck-genie` and `/deck-align` gain first-class opener grilling.** Both skills' existing
opener coverage is per-card ("what's its job?") or hand-shaped ("the dream open") — neither asks a
deck to **rank its startable bodies against each other**, and a per-card bank structurally cannot
produce a total order. So: a dedicated `### Opening placement — the Set-Up Active pick` bank in
`.claude/skills/deck-genie/references/grilling-playbook.md`; **Starter order** added to SKILL.md's
Phase-3 cross-card list and Phase-4 disposition table, so Phase 6 emits a proposal for it; and in
`/deck-align`, `starter_priority` added to the Phase-1 "Vocabulary + wiring" surfaces **plus** a named
finding — *deck has ≥2 startable bodies and no `starter_priority` → drift*. The bank asks, at minimum:
enumerate every legally startable body; rank them; justify each rank (attacks now for how much; HP in
the most-exposed slot; hops from payoff; what it does the instant it is Active); name the bodies you
specifically do **not** want Active and where they belong instead; whether the order flips going
first vs second (decision 3's frame-hunt); multi-prize liability in that slot; and what happens when
your #1 is not in the opening hand.

> **Amendment D (build, 2026-07-28) — the score_diff gate result.** `choice` mode, 372 correction
> frames, run for all four agents against a pre-change baseline. **Every divergence is a
> `_SETUP_ACTIVE` frame — zero collateral divergence anywhere else in the corpus**, which is the
> claim decision 2 rests on (the five rules only ever scored this seam).
>
> Partitioning the divergences by whether the frame is *reachable* for that agent (i.e. every card in
> the select is in its deck.csv):
>
> | agent | own-deck frames | result |
> |---|---|---|
> | `dragapult_ex` | `86091728` (= f2) | **diverges `[0] → [1]` — the intended fix**, matching the correction's `correct` |
> | `mega_lucario` | `84890060`, `85059103` | **no divergence** — the declaration reproduces `start-solrock-over-lunatone`, `dont-open-with-the-engine` and `dont-open-multiprize-active` exactly |
> | `mega_starmie`, `grimmsnarl_ex` | none in corpus | — |
>
> All remaining divergences are **foreign frames**: another deck's correction replayed under this
> agent's Pilot, on cards absent from its deck list. `score_diff` deliberately replays the whole
> corpus under every agent, so that cross-product is a harness artifact rather than reachable play.
> They diverge because the deleted guards were *deck-agnostic* (they scored any card's stats/tags)
> whereas the declaration is *deck-scoped* (silent on cards a deck does not run). Inside a real game a
> deck only ever sees its own cards, and decision 5's completeness invariant guarantees every one of
> those is ranked — which is precisely why the invariant, not the guards, is what makes this safe.
>
> Net: **score-equal on every reachable frame, with the single intended exception.**

> **Amendment F (build, 2026-07-29) — the undeclared-deck gap is WIDER than amendment A said, because
> `open-the-accelerator` was DERIVATION-backed.** Amendment A framed the loss as `grimmsnarl_ex` only.
> That was wrong. `open-the-accelerator` triggered on `"accel_source" in c.roles`, and the Pilot
> *derives* that Role when a deck fields an accelerator body (`_derived_accel_body_ids` —
> "derivation-first, declaration as the confirm/override"). So the rule fired for decks that declared
> **nothing**, and its declaration-keyed successor does not.
>
> Measured, not reasoned: driving 24 `_SETUP_ACTIVE` frames with a bare `Strategy()` on the
> mega_starmie fixture deck, `open-the-accelerator` fires on `main` and **no rule fires** on this
> branch — the pick drops to the engine's option index and opens Staryu roughly half the time
> instead of Cinderace.
>
> This surfaced as a **CI determinism-backstop failure** (run 30430142964, repeat 6 of 15):
> `test_lethal_engine.py::test_live_wiring_engine_refutes_a_phantom_direct_lock` drives whole games
> from a bare-`Strategy()` pilot, so the changed opening moved it into a frame where the planner
> proposed a `kind="evolve"` win. That exposed a **pre-existing hole in the test**, not a defect in
> this decision: its retry guard skipped a frame only when `planned.verified` was truthy, but
> `verified=None` is a legitimate verdict for a win lock (True-or-None, ADR-0037), so an unverified
> non-direct rung tripped an assertion meant for the *direct* phantom. Both engine-drive tests now
> DECLARE `starter_priority` — restoring the trajectory and stating outright what was previously an
> accident of derivation — and the guard skips any win that is not `kind="direct"`.
>
> The decision stands: an undeclared deck getting nothing is the intended consequence of decision 2,
> and decision 5's invariant is what makes it safe *for authored agents*. What changes is the honest
> scope of the carried cost — it is every pilot without a declaration, not one deck.

## Consequences

- The Set-Up Active seam goes from five rules across two layers to **one rule plus one declaration
  per deck**. Opener doctrine becomes readable in one place per deck instead of inferred from a Role,
  a Tag, and a card-id gate.
- A live card-id-gated opener rule (`card_id == SOLROCK`) leaves the tree — the hazard Issue #161 was
  filed to prevent re-buying was already shipped.
- `tests/fixtures/agents/mega_starmie/tuned.json` carries a **learned** `"open-the-accelerator": 45.0`;
  deleting the id fails `test_tuned_wiring`, so it migrates to the successor id or drops.
- Other call sites to update: `test_general_strategy.py`, `test_baseline_clusters.py`,
  `test_system_mega_starmie.py` (its `role_keyed` set — the successor is *declaration*-keyed but opts
  in the same way), `test_submit_brief.py` (which uses the id only as a stand-in for the manifest
  machinery), `tests/fixtures/agents/mega_starmie/strategy.py`, `tests/strategy/test_role_coverage.py`
  (dropping `starter` from `BEHAVIOURAL_ROLES`, else the retired Role could be re-added and lint
  clean), and `docs/general-strategy.md` — whose claim
  that `open-the-accelerator` is *"The only rule in the system at the Set-Up Active pick"* is already
  stale and becomes true again, of a different rule.
- **Accepted cost:** opening doctrine is now split across two vocabularies — a declaration for the
  Active slot, derived rules for the Bench. Recorded here and owned by Issue #197.
- **Accepted risk:** decision 5's invariant is the only thing standing between an undeclared deck and
  the index tie-break. If it is skipped or its "startable body" predicate drifts from
  `_hand_startable`, the regression is silent.
- `xfail`-count bookkeeping in `test_evolve_valuation_corpus.py` settles: with `f2` relocated the file
  holds 4 pins + 1 claims case and **no** targets (ADR-0070 §4 anticipated "4 pins + 2 in-path
  targets" before Issue #140's swap promoted `f40` to a pin).

## Alternatives rejected

- **A derived line-shape term (Ruling 5 as written).** Refuted at source: its named discriminator
  `can't-attack-now` is `False` on its own motivating frame, and a derived placement value is what
  ADR-0070 §4 struck twice, ruling that if exposure ever returns it lands as a per-axis **Gate**
  (ADR-0069 §4), never a subtracted term.
- **Additive: a declaration rung stacking on the existing rules.** Two signals firing on one card for
  one reason — the failure recorded in mega_lucario's retired `dont-attach-to-the-engine`
  (*"Keeping both would stack to −24 …"*).
- **A tie-break-weight declaration.** Would pass `f2` (everything is 0.0 there) while leaving the
  accidental `+40 > +35` ordering intact. Solves the test, not the problem.
- **Rank-scaled weights (1…N).** At 1–5 the surviving guards were 3× the entire spread of the
  ranking, so a deck deliberately ranking its Basic-ex first netted `5 − 15 = −10` and lost to an
  unranked Basic — the declaration overruled exactly where `dont-open-multiprize-active`'s own
  rationale promised an escape. Scaling up restores authority but multiplies the calibration question
  by N. Moot after decision 2 deletes the guards, and dominated by decision 5 under a complete list.
- **Keeping the `starter` Role as opt-in, with the list supplying only order.** Two declarations that
  must agree per card.
- **Hand-authoring the four lists inline.** Precisely what ADR-0046 exists to prevent, and it would
  ship the decision-10 question bank without ever running it.
