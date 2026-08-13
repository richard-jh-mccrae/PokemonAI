# Agent architecture

All decks share the same Bellman runtime.

```text
agent main.py
  -> common.runtime.make_agent
  -> sole legal semantic action: commit immediately, or
  -> declarative setup, or
  -> Scouting Read + deck Strategy profile
  -> Bellman transition tree
  -> recursive deterministic solve + stochastic successor backup
  -> commit the root action
```

`strategy.py` is the only deck-specific policy surface. It declares deck-specific Roles, exceptional
evolution Lines, starter order, deck-specific partner dependencies, prize routes, and a preferred
starting turn. Printed card roles, evolution edges, and partner dependencies come from shared
card-function data. Mega Starmie, Mega Lucario, and Dragapult all enter the same `BellmanRuntime`
and `BellmanTurnPlanner`.

Production transitions use the native `cg` search API. `cgpy` is an offline diagnostic adapter only
and is excluded from submissions. Both adapters enter the same state, ledger, value registry, and
solver contracts.
Triggered on-play/on-evolve Ability confirmation menus reconstruct their source hook rather than
being mistaken for attacks merely because the source Pokémon is already in play.

Production recursively solves deterministic action sequences. For a stochastic draw or reveal it
backs up the probability-weighted observable successor potential when cgpy returns to MAIN; mandatory
cost and target menus remain inside the branch. The exact reference solver remains recursively
exhaustive for finite test graphs. This avoids multiplying every random outcome by a duplicate
whole-turn tree without a depth tier, action policy, or deck/card branch.

Shuffle-refresh cards are a deliberate exception to successor-state expansion. The solver does not
invent a shuffled hand and play a hypothetical remainder of the turn. `common.needs` derives
immediate unmet jobs, direct/fetch coverage, and deterministic next-turn options for visible cards.
The next-turn projection advances only evolution legality for known cards; future Supporter effects
remain in the normal hand family until a generic effect-outcome evaluator exists. It never predicts
an opponent action or unknown card. `common.refresh` integrates immediate coverage classes with exact hypergeometric
probabilities and weighs that benefit against both current and next-turn known-hand option value.
The branch stops at the refresh commitment; after the live engine produces the real hand, the next
callback replans from reality.

This keeps refresh decisions inside the Bellman ledger without turning random cards into an
imaginary turn. It also makes useful non-Supporter plays naturally precede a refresh: realizing a
known option removes its shuffle-away cost, while a need already satisfiable from hand receives no
draw credit.

Typed successor reachability also lives in `BoardPotential`. Fetch clauses form a
probability-discounted graph, so a tutor carries the option value of its best legal target without
summing mutually exclusive targets. This covers multi-hop lines such as a Supporter tutor into a
Trainer tutor while the transition engine remains authoritative for same-turn costs and limits.
Before valuing that option, `common.needs` removes operations already supplied by the visible hand,
then propagates remaining energy, Pokémon, retreat, and damage-threshold demand through the same
typed fetch graph for Trainer/Supporter tutors. Once played, Meowth's pending choice carries the
value of a legal downstream Petrel route; target selection remains a normal Bellman continuation.
The visible demand is frozen once per solve, while legality and target inventory remain live. A
same-turn route exists only when the need is not already covered by a playable hand card, its
source is playable or presently resolving, every downstream identity has a known or inferred deck
copy, and the final card becomes a legal MAIN action. Each committed play and verified target
selection raises the route's discounted state value. The value transfers into the fulfilled board
state when the final card is played, so bounded search never loses the Bellman gradient between
fetching the answer and realizing its effect. Existing hand copies cannot masquerade as newly
fetched progress, and an actual target menu overrides inferred inventory.

Prize routes are conditional chains, not forced scripts. Progress reads our lost prizes and can
resume from the current Active after an off-route KO. Route value requires every remaining body to
be reachable and values resources already committed to the next attacker. It does not assume a free
future manual attachment: Bellman search retains that Energy's competing uses. A KO
of the opponent's only in-play Pokémon uses terminal game utility; damage boosts still in hand are
access-discounted until played, preserving a Bellman gradient toward the exact winning line.

No incomplete result or adapter failure falls back to another strategy system.
