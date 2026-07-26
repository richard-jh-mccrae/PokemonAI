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
   one. The documented over-inclusion of `energy_type` on a Pokémon target (unresolvable from
   `CardStat`) is therefore safe here for the same reason it is flagged as a caveat for reach.
4. **One deadness fact, two consumers.** The widened `_search_deck_set` feeds both the play-side
   `dont-search-an-empty-deck` rung and the keep-side `_deploy_odds` fetcher gate. This closes issue
   #164's "widen the predicate **or** price by deploy odds" as a false choice: they read the same
   set, so widening it prices the gate too.

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
