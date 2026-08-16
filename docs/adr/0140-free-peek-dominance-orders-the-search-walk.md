# ADR-0140: Free-peek dominance orders the search walk

Status: Accepted for production activation by developer request (2026-08-16), knowingly
overriding part of the ruling corpus.  The corpus is split on the principle:
mega_starmie_20260813_33b43c86 rules Pokégear-before-energy on one frame (d31f6bfa4803) and
Ignition-attach-before-Pokégear on another (810eb9a2ae5c), so no unconditional peek-first gate
can satisfy both.  Armed on, the gate resolves the two disputed budget-flip frames and
contradicts four previously passing rulings, including one where pruning cheap completable
commitment lines degraded capped lower bounds enough to surface a ruled-out dead fetch
(25c423bbb0ec).  Those four rulings are the open re-adjudication worklist; the switch below
restores the full walk at any time.

## Context

The production solver got ~1.6x faster per decision, and two deadline-limited correction frames
flipped: with more nodes in the same 15 seconds, deep narrow commitment lines (attach to the
successor attacker; retreat) produced higher incomplete lower bounds than the shallow, bushy
Pokégear-first lines the human rulings prescribe.  The strategy beam already ranks
`general.low_cost_information_access_before_commitment` first, but beams allocate search order and
budget only; the final selection is a pure value comparison, so a deeper-dug alternative can
overtake the focused line whenever the clock cuts the bushy reveal subtree short.

The desire is for strong sequencing knowledge to constrain which paths the search walks at all.  A
strategy-strength hard gate was considered and rejected: it reintroduces rules overriding the
value calculation (the pattern the Bellman migration removed, and the forgo-KO history shows the
failure mode), needs a tuned threshold with cliff behaviour, and hides value-model disagreements
instead of surfacing them.

## Decision

The production solver prunes by *dominance*, not by strategy strength.  At an own-turn MAIN
decision where a costless pure deck peek is legal — an action whose footprint carries
`information_first`, i.e. a pure hidden fetch consuming no allowance — every hand-and-deck-neutral
commitment action is pruned from that node's walk: `commitment` footprints that are not barriers
(energy attaches, evolutions, retreats, declared-deterministic trainer plays).  Peek-first lines
still reach those commitments one node later, so the pruned orderings are weakly dominated: the
peek reads and writes only the deck and its own hand slot, leaves every such commitment exactly as
legal and identical in effect, and adds information.

Never pruned:

- **Barrier actions** (draws, hand shuffles, opaque plays): a shuffle destroys the peek's
  knowledge, so peek-first is not dominant over them — Harlequin-first can be strictly better
  than Pokégear-into-Harlequin.
- **Attack and End**: the guaranteed-executable safety fallback and the exact End lower bound
  must stay reachable at every node.
- Anything at a non-MAIN selection, or when no legal peek survived sleep-set filtering.

The rule is a per-node filter (it re-evaluates at every state; once the peek is consumed the
commitments reappear), runs after sleep-set pruning and before strategy focus and width caps,
counts into `information_first_permutations_pruned`, and records
`{"proof_type": "information_dominance"}` rows in `structural_prunes`.  Switch:
`search.information_dominance_enabled`, default **on**.  The reference solver stays exhaustive.

## Consequences

- The gate resolves the two disputed budget-flip frames to their ruled information-first plays
  by construction — and overrides four other rulings, accepted by the developer to observe the
  rule live; those four are the re-adjudication worklist.
- Two limits of the dominance argument surfaced by the corpus, recorded for any future arming:
  1. *In-model free is not free.*  Pokégear's reveal shows the fetched Supporter to the opponent;
     tutors classified `information_first` (Mega Signal) are spendable resources.  The model
     prices neither, and rulings do.
  2. *Dominance over true values does not transfer to capped lower bounds.*  Pruning a cheap,
     completable commitment line in favour of a bushy reveal subtree can lower a node's
     achievable bound under node/time caps, and the degraded bound can promote a genuinely bad
     root action.
- Any future arming needs at minimum: a trigger narrowed to windows the rulings treat as free,
  and a bound-safety condition (only prune where the peek-first line completes within the cap).
- The beam remains ordering-only; no strategy score can remove a line a proof does not cover.
