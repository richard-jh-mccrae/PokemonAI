# ADR-0073: Fetch reach and fetch deadness are opposite readings of one clause

**Status.** Accepted (grilled 2026-07-26, issue #164). Extends ADR-0065 (the card-worth closure
graph that owns `fetch_closure`), ADR-0032 (the Effect-Clause compendium the predicate reads) and
ADR-0029 (the sound/probabilistic split on own-deck knowledge). Companion to ADR-0068 (the Count
Triple, which supplies the deck-content facts both readings consume).

## Context

A fetch clause (`card_effects.json`, `{"kind": "fetch", "zone": "deck", "target": ...}`) is read by
two families of consumer that ask **opposite** questions of the same row:

- **Reach** (optimistic) — *"can this card get me card X back?"* Consumed by the card-worth closure's
  out-count (`fetch_closure.reaccess_outs` / `class_reaccess_outs`), the recycler count in
  `pilot._discard_equation_pick`, and the tutor-chain graph (`_chain_fetch_targets`). An over-count
  here inflates the gain side of every gamble and Hand Refresh.
- **Deadness** (pessimistic) — *"is there anything left in my deck for this card to find?"* Consumed
  by the play-side whiff veto (`dont-search-an-empty-deck`, via `_search_deck_set` ⊆
  `Board.deck_empty_ids`) and by the fetcher leg of the deadline gate
  (`gate_library.fetch_deploy_odds` via `planner._deploy_odds`).

One shared predicate (`fetch_closure.fetch_target_matches`) served both, carrying two narrowings
written for **reach** only: it rejects `dig` / `trigger` clauses outright (`fetch_closure.py:48`),
and its deadness caller further restricted target classes to `_FETCH_POKEMON_TARGETS`
(`pokemon` / `basic_pokemon` / `mega` / `evolution`).

Both narrowings are correct for reach and wrong for deadness. A Pokégear 3.0 (`{"target":
"supporter", "dig": 7}`) that digs 7 may **miss** a Supporter still in the deck, so it is no
guarantee of re-access — but if the deck holds **zero** Supporters, the dig provably finds nothing.
Rejecting the clause suppresses a sound whiff claim. The result was a family of six Trainers whose
deadness could never be read at all: **Pokégear 3.0, Energy Search, Energy Search Pro, Fighting
Gong, Hilda, Team Rocket's Petrel**. (Meowth ex's `trigger` clause is on a Pokémon, already excluded
by `_deploy_odds`'s Trainer-only guard.)

The motivating frame is `82525741-78` (issue #164): a target-exhausted Buddy-Buddy Poffin. Its
Pokémon-class clause *is* covered — the `-60` fires on today's build — but the deck's four Pokégear
3.0 sit in the same hand under the same defect, invisible to the same predicate.

**Found at build time: for a MULTI-clause fetcher the defect was not blindness but UNSOUNDNESS.**
Fighting Gong and Hilda each carry two deck-zone clauses, one class in the old scope and one outside
it — Gong fetches a Basic {F} Energy *or* a Basic {F} Pokémon, Hilda an Energy *or* an evolution. A
fetcher is dead only when **every** class it can search is exhausted, so dropping a class from the
set makes the `all(gone)` conjunction range over too little and go True too early. Verified against
the pre-change tree: `_search_deck_set(Fighting Gong)` returned the five Pokémon ids and nothing
else, so once those were gone the `-60` would have vetoed a Gong that could still find Energy — a
**fabricated** deadness claim, the exact fail direction `fetch_closure` forbids of an endorser. That
reframes this ADR: it is a soundness fix that also closes a coverage hole, not the reverse.

**No new deck knowledge is required for any of this.** `StateModel.unseen_counts` (decklist −
visible − anchored prizes) and the sound `Board.deck_empty_ids` already answer "what is left in my
deck" per card id on every frame, with or without a prior deck-revealing search — all three Staryu
at `82525741-78` were provably gone from visible zones alone. The gap was never epistemic; it was a
filter written for one consumer and silently inherited by the other.

## Decision

**Reach and deadness are distinct readings of one clause row, and the asymmetry is stated, not
implied.**

1. **One predicate, one explicit opt-out.** `fetch_closure.fetch_target_matches(clause, stat, *,
   deadness: bool = False)`. The default is unchanged and remains the reach reading, `dig` /
   `trigger` rejection included. `deadness=True` skips that rejection and is passed by exactly one
   caller: `doctrine_fetch._search_deck_set`.
2. **The deadness caller ranges over every deck-zone target class**, not just the Pokémon ones —
   `_FETCH_POKEMON_TARGETS` is superseded for this reading by the full set (`pokemon`,
   `basic_pokemon`, `mega`, `evolution`, `supporter`, `trainer`, `energy`, `basic_energy`).
3. **Over-inclusion is sound in the deadness direction, and that is why it is permitted.** Deadness
   is `all(t in deck_empty_ids for t in fetch_set)`. Widening `fetch_set` makes that `all()` *harder*
   to satisfy, so an over-broad target class can only **suppress** a whiff claim, never fabricate
   one. `energy_type` on a Pokémon target is the worked example, and it stays deliberately unread
   here — but its *reach* caveat is *retired* by the 2026-08-08 amendment below.
4. **One deadness fact, two consumers — carried by a SEPARATE set from the reach one.** A single
   `_fetch_deadness_set` feeds both the play-side `dont-search-an-empty-deck` rung and the keep-side
   `_deploy_odds` fetcher gate. This closes issue #164's "widen the predicate **or** price by deploy
   odds" as a false choice: they read the same set, so widening it prices the gate too.

   **Amended at build time (2026-07-26).** This decision originally said the *widened
   `_search_deck_set`* feeds both. That was wrong, and shipping it would have been unsound.
   `_search_deck_set` has five consumers, and three of them are **endorsers**, not deadness
   questions: `fetch-when-it-fills-a-need`, the deferral deadline (`_fetch_target_deferred`), and the
   wincon-tutor redundancy read. Decision 3's soundness argument covers only the conjunction
   (`all(gone)`); under an *existential* (`any(reachable and worth grabbing)`) a wider set
   **fabricates** endorsement — a dig-7 Pokégear over a Supporter-holding deck would claim it FILLS
   that need, when it can only probably reach it. So the two readings carry two memoised sets:
   `_search_deck_set` (reach scope, unchanged) and `_fetch_deadness_set` (deadness scope), with the
   reach set a **subset** of the deadness set for every card of every shipped deck — pinned by a
   test. Only the two deadness consumers were re-pointed.

**Rejected: moving the `dig` / `trigger` rejection out to the five reach consumers**, leaving the
shared predicate policy-free. That is the tidier seam and it loses on fail direction. Under the
accepted decision, a future caller that forgets `deadness=True` gets the safe answer — a *missed*
whiff claim, visible as a played dead card in a score-diff. Under the rejected one, a future reach
consumer that forgets the guard silently over-counts out-count, unsound and invisible without a
targeted test. Correctness outranks seam purity (grill ranking criterion 1 over 2).

**Rejected: widening only the non-`dig` classes** (five of the six cards). It is a one-line change
that leaves the live instance of the defect — the 4× Pokégear 3.0 the agent actually plays at the
anchor frame — shipping.

## Consequences

- Six Trainers newly become readable as dead. They gain the `-60` play-side veto **and** a 0.0
  fetcher gate in the graded refresh SHED / gamble keep-floor, so this is a behavioural change on
  two surfaces and needs a **score-diff run**, not only a unit pin, before it lands.
- `fetch_target_matches`'s existing five reach call sites are untouched; the closure's out-count
  keeps exactly the epistemic ADR-0065 gave it.
- The `dig` rejection at `fetch_closure.py:48` stays load-bearing for reach and acquires a stated
  reason for *not* applying to deadness, replacing what was an unremarked inheritance.
- Extension point unchanged: a new fetch card is a new **clause row**, and it is now read by both
  questions automatically rather than only by reach.
- **A `supporter` branch was added to the predicate, DEADNESS-ONLY** — found at build time. The class
  had no branch at all, so a `supporter`-target clause matched nothing and the deadness set came back
  empty even once the target class was in scope. It is gated on `deadness` so reach stays unchanged
  *provably* rather than incidentally: reading it for reach would be inert today (both carriers are
  `dig`/`trigger` clauses) but would rest the guarantee on which cards happen to exist. A future
  *plain* Supporter search genuinely is a deterministic whole-deck search and so a real closure edge —
  un-gating it is then a deliberate, measured change to the out-count rather than a silent
  consequence of a new card row. Until then the omission under-counts outs, this module's safe
  direction.
- **Measured before landing.** The Score-Diff Gate over the corrections corpus (372 frames × three
  shipped agents, `scores` mode) reports **0 divergent**. That is the expected shape, not a null
  result: the six newly-readable Trainers only fire once their whole target class is provably
  exhausted, a late-game condition the corpus does not contain. Reachability is carried instead by
  behavioural tests — a dig-class fetcher vetoed once its Supporters are provably gone, left alone
  while one remains, and never claiming to fill a need in either case.

## Amendment (2026-08-08, split out of issue #440): body COLOUR narrows REACH, and only reach

Decision 3 waved `energy_type` on a Pokémon target through as an accepted over-inclusion because it
was **"unresolvable from `CardStat`"**. That premise was already false when it was written.
`provider._build_cache` writes `energyType=int(c.energyType)` for every card, and across the five
shipped decks all **41** Pokémon rows carry a non-`None` colour. So reach now takes the narrowing.

**It binds reach and NOT deadness, and the asymmetry is the whole point.** Reach's consumers are
ENDORSERS asking `any(reachable)`, so a *narrower* set can only withdraw an endorsement — the safe
direction. Deadness asks `all(gone)`, where narrowing makes the conjunction go True *earlier* and
**fabricates** a whiff: precisely the unsoundness this ADR was written to fix. Reach therefore stays
a **subset** of deadness by construction here, since this change can only ever shrink it.

**Read `energyType == 0` with care.** Trainers report `0` as well (Pokégear 3.0), so the field alone
cannot tell {C} from "not a Pokémon". The filter is applied inside `_pokemon_body_matches`, reachable
only past `stat.is_pokemon`, so `0` unambiguously means Colorless there — a *structural* guard rather
than an `is_pokemon` check each future caller must remember. Its home with the shared per-body
predicates also means all **eight** Pokémon classes take it, not just the two with carriers today.

**The clause population is five, and only one is both reach-live and shipped.** `19` Telepath Psychic
Energy and `1094` Bug Catching Set pair `energy_type` with a Pokémon target but carry `trigger` /
`dig`, so reach already rejected them. Reach-live: `1142` Fighting Gong (`basic_pokemon`, {F}, deck),
`1233` Canari (`pokemon`, {L}, deck) and `1238` Tarragon (`pokemon`, {F}, **discard**). Only Fighting
Gong sits in a shipped decklist (mega_lucario); the other two are prospective.

**Measured before landing** — Score-Diff Gate, corrections corpus, 375 frames × three shipped agents,
`scores` mode:

- **mega_lucario — the only deck that runs Fighting Gong — is 0 divergent.** Its four {F} Basics
  (Makuhita, Lunatone, Solrock, Riolu) keep the endorsement; the single leg dropped is the {C} Meowth
  ex, which Gong could never legally fetch.
- **mega_starmie and dragapult_ex report the same 4 divergent frames**, and all four are
  *mega_lucario-recorded* observations replayed through a foreign decklist. Neither deck holds an {F}
  Pokémon, so Gong's reach set correctly collapses to empty and `fetch-when-it-fills-a-need`'s `+8`
  withdraws (one frame also flips the choice, `[11] -> [12]`). That configuration is **off-policy** —
  neither Pilot can hold Fighting Gong in a real game — and the movement is a fabricated endorsement
  being withdrawn, which is the direction this change exists to produce.
- **Attribution control:** with `fetch_closure.py` alone reverted and the same baselines, all three
  agents report 0 divergent. The four flips are this change, and the harness is deterministic.
- The two main-watchdog gates are **unmoved**: the Discrimination and Decision reports are identical
  to a clean `HEAD` checkout's (60 / 41 unruled respectively). Both were **already red on `main` at
  `a5f25cd2`** — pre-existing and out of scope here, but they do not gate this change either way.

**The five reach call sites this ADR named are now seven.** `board_expectation.outcome_pool` and
`board_choice._discard_matches` arrived after ADR-0073 and share the default parameter, so they take
the narrowing too — `outcome_pool` for Fighting Gong and Canari, `_discard_matches` for Tarragon.

**This does NOT close issue #440, and the distinction matters.** #440's subjects are Pokégear 3.0 and
Bug Catching Set, whose clauses carry `dig: 7`. `fetch_is_unconditional` rejects those under the
default reading, so they never reach the body branch this amendment changes — `outcome_pool` refuses
them outright today. #440 has to introduce a *third* reading that ADMITS a dig as a window over the
unseen pool. What this amendment buys that work is placement, not the fix: the colour filter sits with
the shared per-body predicates, so a dig-window reading inherits it automatically so long as it does
not pass `deadness=True`. Bug Catching Set's `{"target": "pokemon", "energy_type": 1}` is exactly the
clause that would otherwise over-count a window class, and it is still over-counting after this change.
