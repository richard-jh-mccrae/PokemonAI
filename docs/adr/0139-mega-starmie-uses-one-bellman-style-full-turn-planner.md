# ADR-0139 — Mega Starmie uses one Bellman-style full-turn planner

Status: Accepted and implemented for Mega Starmie.

## Context

Mega Starmie's shipped Pilot is a rules-heavy hybrid. Legal-option generation, tactical deciders,
Needs, hypothesis rungs, goal ladders, Composer, planner overrides, and doctrine ordering can each
own part of the same choice. Several layers are incomplete or dark, and a locally sensible score can
be overwritten by a different subsystem that prices a different part of the line. The result is not
one optimization problem and cannot explain a turn with one conserved ledger.

[ADR-TEMP-507](temp-issue507-every-action-is-benefit-minus-opportunity-cost.md) established the local
economic invariant:

```
net(action) = realised benefit(action) - opportunity cost(consumed resources)
```

Only End Turn is exactly zero. A known action that realizes no benefit is strictly negative. That
invariant must now govern the complete reachable turn rather than selected seams.

The older [ADR-0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) planner is
goal-directed: special rungs generate a small set of lines and a mixture of closed-form and engine
values ranks them. That was a useful bridge, but it is still a rules-based candidate policy rather
than exhaustive legal-action Bellman search. Adding another override to it would deepen the ownership
problem.

## Decision

### 1. One recursive objective

For every decision state `s`, the planner evaluates every legal action `a`:

```
Q(s, a) = E[benefit(s, a, s') - cost(s, a, s') + V(s')]
V(s)    = max(0, max_a Q(s, a))
Q(s, End Turn) = 0
```

`benefit - cost` is a diagnostic decomposition. Selection is made from the total `Q`; no tactical
rung, doctrine, card exception, or independently ranked trace may replace it. A consequence is owned
once, at the transition or state potential where it becomes true, and is never re-credited by a
continuation.

The node algebra is:

| node | operation | examples |
|---|---|---|
| our choice | `max` | MAIN action, fetch target, Energy allocation, snipe target |
| opponent choice | `min` | forced promotion, opponent-selected target |
| known chance | probability-weighted expectation | shuffle/draw/reveal windows, coin outcomes |
| engine rule | deterministic transition | damage, KO, discard, prize award, quotas |

End Turn consumes nothing and is the sole deliberate zero. An unknown or unmodelled transition is
`UNKNOWN`, never zero and never a reason to call an action free.

### 2. Scope and atomic activation

The first production owner is Mega Starmie only. The implementation lives behind an isolated
Bellman entry point until the complete prototype passes its acceptance gates. Mega Starmie's live
Pilot then switches atomically: there is no stepwise mixing and no legacy fallback.

The Bellman path must not consult strategic outputs from:

- `OptionTrace.score`;
- hypotheses, tuned rungs, or goal ladders;
- the legacy Lethal Solver or goal-directed Turn Planner;
- Composer candidate selection or admission scores;
- attach, fetch, refresh, retreat, heal, or gust sequence overrides;
- `_finish_turn_last` or other doctrine ordering.

Neutral substrate may be reused: engine legal options, immutable state construction, canonical
option identity, card/effect facts, CombatMath, Needs, hypergeometric odds, Scouting facts, semantic
state identity, and diagnostics. Reuse does not grant the old component decision ownership.

Mega Lucario and Dragapult remain on the legacy Pilot during this prototype. The Bellman kernel is
deck-neutral so they can migrate later by supplying declarations, not copied tactics.

### 3. Turn boundary

Pregame and Set-Up remain outside Bellman. The deck's complete starter declaration chooses the
Active; Mega Starmie's authored order is Cinderace, then Staryu. Every optional Set-Up Bench
placement is declined by the existing structural `setup-never-bench` rule from
[ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md).

Bellman begins at the first normal decision of the turn.

End Turn is immediately terminal. Attack ends voluntary MAIN actions but is not itself a leaf. The
attack transition is terminal only after the complete attack-resolution decision tree:

1. choose and pay a legal attack;
2. resolve damage and deterministic effects;
3. resolve our attack-owned selections and chance outcomes;
4. resolve recoil, return-to-hand, discard, and other self-effects;
5. resolve Active and Bench KOs, prizes, and game termination;
6. resolve opponent forced choices, including promotion, as `min` nodes;
7. value the final post-attack board.

Examples of attack-owned subtrees include Turbo Flare's Basic-Energy count and recipients, Jetting
Blow's Bench target, Aura Jab's discarded-Energy recipient, and Phantom Dive's complete damage-counter
allocation. These are recursively evaluated choices, not calls to separate tactical deciders. The
parent attack pays the attack/card/allowance costs once.

### 4. Legal actions and transitions

The engine-facing enumerator generates every currently legal option. Each option is normalized to a
canonical action identity and applied through one transition contract:

```
TransitionResult = Deterministic(state)
                 | Choice(actor, children)
                 | Chance(weighted_children)
                 | Terminal(state, result)
                 | Unknown(reason, missing_fact)
```

Per-turn budgets—Supporter, manual attachment, retreat, Ability use, attack, and card-specific
allowances—are state, not hidden decider knowledge. Consuming one is a transition cost even when the
visible board does not change.

Mechanic adapters may branch on card rules because they simulate consequences. They may not branch
on tactical conclusions such as “play this card in this matchup” or “prefer this target.” Those
conclusions must emerge from successor value.

Before activation, every option and nested selection reachable from the Mega Starmie deck must be
deterministic, a fully enumerated Choice/Chance node, or an explicit tested refusal. A refusal reachable
in ordinary Mega Starmie play blocks activation; the legacy Pilot may not silently handle it.

### 5. Benefits, costs, and state value

Benefits are realized changes in the canonical state/value families, including:

- game result, prizes, and prize race;
- damage, KOs, threat removal, and post-attack safety;
- typed attack readiness and persistent Energy development;
- legal evolution and dependency-chain progress;
- hand option coverage, information, and future access;
- denial measured as the opponent's best continuation before versus after the resource loss;
- survival and positional mobility against the opponent belief.

Costs include every consumed scarce object or allowance:

- portable held-card Worth;
- cards discarded, shuffled away, or made inaccessible;
- attached or discarded Energy and lost alternative recipients;
- Supporter, manual-attach, retreat, Ability, and attack allowances;
- Bench slots and target opportunity;
- information lost by committing before observing;
- option value destroyed by an irreversible action.

Shared initial Worth seeds remain human-authored and training-free:

| function | Worth |
|---|---:|
| win condition | 30 |
| evolution-line base | 20 |
| Energy acceleration | 12 |
| search, tutor, dig, Bench fill, Item lock | 10 |
| draw, hand refresh, Basic Energy | 8 |
| Energy denial | 6 |
| switch, stall, known-card floor | 5 |

`120 Worth = 1 prize` is the initial bridge. A card's portable function Worth is shared across decks;
a deck may raise it, never lower it. These are explicit seed parameters for later fitting, not
action-specific rules. Training may calibrate parameters after the prototype; it may not replace the
Bellman ownership contract.

### 6. Needs are causal marginal demand

Needs supplies marginal demand to the value function; it never chooses an action. A need is derived
from legal dependency chains rather than a flat deck wish list. For Mega Starmie:

```
Turbo Flare supplies Bench Energy
  -> a legal Bench recipient is needed
  -> Staryu supplies the Mega Starmie evolution line
  -> that line converts Turbo Flare's attack rider into persistent readiness
```

The same graph vocabulary transfers to Aura Jab recipients, Solrock/Lunatone partnerships, Recon
Dive information, Crispin's typed supply, and Phantom Dive/Munkidori counter interactions. New decks
should declare evolution lines, roles, rare partnerships, starter order, upward Worth overrides, and
match objectives. They should not add tactical `if/else` branches to the solver.

### 7. Known uncertainty and replanning

Known uncertainty is evaluated as an outcome distribution. Hypergeometric/card-window odds provide
probability; Needs and successor search provide each outcome's marginal value. Outcome classes are
mutually exclusive complete states, not independently summed hit rates. Whiff mass is explicit.

Lillie's Determination, Recon Dive, an unknown-order Ultra Ball search, and similar effects are
contingent policy trees:

1. compare the expected value of taking the uncertain action now with every current alternative;
2. choose it only when expected benefit exceeds its full cost and opportunity margin;
3. execute the real action;
4. replan from the actual revealed state;
5. make the newly presented off-MAIN selection with the same evaluator.

The plan commits only the next action, never a fictional post-reveal sequence. The expected search
and the real replan must use the same value contract.

### 8. Opponent belief and Scouting

Opponent-facing value reads one immutable `OpponentBelief` provider composed from:

- exact visible state;
- portable card, evolution, Ability, and attack facts;
- the latest Scouting archetype posterior;
- observed match history and Brief evidence;
- explicit unknown probability mass.

Scouting informs consequences; it never selects a target. Legal visible opponent responses are
enumerated from the engine. The opponent selects the worst response for us (`min`); roles and Scout
facts value those responses rather than replacing enumeration. Hidden archetype possibilities are
an expectation over the posterior, retaining an unknown bucket when confidence is low.

Gusting, attacking, sniping, and denial compare counterfactual successor states. No Scout-derived
tactical bonus, target rung, or confidence preference is permitted on the Bellman path. Hypothetical
own actions carry the same belief unless the action reveals information.

### 9. Search and performance

There are two modes over the same transition and value contracts:

- `reference`: exhaustive within its explicit node cap; any cap or unknown reports incomplete;
- `production`: the same recurrence with semantic transposition, explicit width/state capacity, and
  a zero End lower bound when capacity is reached at a state where End is legal.

Production grants the same state budget independently to every root action. A shared pool divided
by menu size is forbidden: it makes an action's estimate worse merely because unrelated actions are
also legal. Incomplete, budget-dependent lower bounds are never memoized as transposition values.
On exactly equal utility, the sole secondary objective is fewer remaining decisions; it is
lexicographic and therefore cannot overturn any real utility difference.

The reference solver is the correctness oracle for fixtures and sampled corpus states. Production
may prune for time but may not change the equation, fabricate a terminal value, or delegate a pruned
choice to legacy logic. Its budget and approximation regret are measured against reference states
before activation. Budget constants and stopping reasons appear in telemetry.

The live production transition provider uses the shipped forkable `cgpy` engine. Deterministic draws,
coins, reveal windows, and actor choices are transition algebra, not card-name handlers. A reveal is
`chance(revealed set) -> max(legal revealed continuation)`; static Worth never chooses the card.
Known reveal sets use exact hypergeometric mass. Wide hidden draws use deterministic bounded support,
and their continuation values are probability-weighted by the same recurrence.

For a reveal-and-choose effect the recurrence is
`E_R[max(c in legal(R) union decline, delta U(c) + V(successor(c)))]`. The revealed card is never
chosen by portable Worth or precedence. Same-turn transitions use discount 1 because the horizon is
one finite turn; probability supplies chance weighting. The named future-hand-access discount applies
only to resources left for later turns.

Search continues while a legal successor has positive value over stopping. It stops at End, a fully
resolved attack, a game result, or an explicit budget/unknown result. Cycles are prevented by semantic
state identity plus remaining allowances, not action-name blacklists.

### 10. Required explanatory ledger

Every evaluated root action exposes a stable decomposition:

```
immediate benefits
- consumed costs
+ expected continuation
= Q
```

Chance branches expose probability and branch value; `min` nodes expose the opponent response;
pruned or unknown nodes expose their reason. The chosen first action, End's exact zero, and the best
rejected alternative are always present. Diagnostics are evidence and never feed selection.

### 11. Atomic cutover and purity

The isolated planner is tested directly throughout the build while the live Mega Starmie Pilot stays
unchanged. Activation occurs in one final change only after every milestone in
[`mega-starmie-bellman-build.md`](../plans/mega-starmie-bellman-build.md) is complete.

A purity test replaces every legacy strategic chooser with a function that raises. Mega Starmie's
Bellman Pilot must still complete representative turns, uncertain reveals, fetches, attacks, nested
allocations, and forced promotions. A structural import/call audit prevents the Bellman package from
depending on legacy strategic selectors.

## Corpus and acceptance policy

The complete Mega Starmie correction corpus is always swept with no “covered” exclusions. The
correction rationale is the primary human ruling; an accidentally selected action label that
contradicts its rationale is reported rather than fitted.

Legacy exact first-action agreement is an audit, not a blanket activation veto. Every record is
classified:

- `MATCH`;
- `EQUIVALENT_OR_BETTER_COMPLETE_LINE`;
- `STALE_LABEL_RATIONALE_AGREES`;
- `BELLMAN_ERROR`;
- `UNMODELLED`.

Hard activation failures are:

- illegal actions or missed immediate wins;
- wrong attack payment, target, Energy type, or nested allocation;
- a pure-cost action beating End;
- a consumed resource with no beneficial continuation;
- duplicated or omitted consequence value;
- incorrect chance mass or replan behavior;
- incorrect post-attack KO, prize, or forced-promotion state;
- any ordinary Mega Starmie action reaching `UNKNOWN`;
- purity, reference-parity, performance, or crash-smoke failure.

The two initial full-turn acceptance fixtures are:

1. Cinderace Active with no Energy or Bench; Boss, Basic Water, and Lillie's in hand; opponent has a
   harmless Active and a 60-HP fragile future win condition on the Bench. The expected policy attaches
   Water to Cinderace, then plays Lillie's because Staryu outcomes unlock Turbo Flare's future rider.
2. The same state with a 50-HP benched win condition. Boss into a resolving KO is a competing line
   whose immediate threat removal may exceed the setup gamble; the equation, not a frame exception,
   decides the boundary.

Frozen gate baselines are ruling records. They are never captured, restamped, or conformed without a
developer verdict. Full-suite failures already present on clean `main` are named separately from
prototype regressions.

## Consequences

Mega Starmie's strategic choice becomes one inspectable optimization problem. The implementation is
larger than another decider rule and requires complete transition coverage, but it removes competing
strategic owners rather than adding one. Performance work becomes a measured search approximation
problem. Deck transfer becomes data/causal declaration work instead of copied tactical branches.

ADR-0031, ADR-0037, ADR-0095's legacy ordering fallback, and the current Composer/planner overrides
remain historical and continue to govern unmigrated decks. They are superseded as strategic owners
for Mega Starmie only when the atomic activation gate passes. Structural game rules, setup policy,
card facts, Needs, CombatMath, Scouting evidence, semantic identity, and ADR-TEMP-507's action-cost
invariant remain authoritative substrate.

## Implementation outcome

The atomic Mega Starmie cutover is complete. After Set-Up, every offered action and nested choice is
generated and transitioned through `common.bellman`; no legacy strategic chooser or fallback can
select the move. The bounded production solver and exhaustive reference solver share the same
state, transition, Worth, potential, chance, belief, and ledger contracts. Production has no depth
horizon: a turn ends only by engine transition, semantic-cycle detection, or explicit capacity.
There is no preview policy, tactical candidate filter, card precedence, or separate terminal-win
search. Engine-confirmed wins are ordinary terminal values and all legal siblings remain comparable,
including the lexicographic shorter-line tie break. At
capacity, production may back up End's exact-zero lower bound and marks the result incomplete in
telemetry; mandatory nested states still fail closed.

The unfiltered final corpus audit contains 259 corrections, zero exclusions, and zero unexplained
rows: 141 `MATCH`, 24 `EQUIVALENT_OR_BETTER_COMPLETE_LINE`, 19
`STALE_LABEL_RATIONALE_AGREES`, 13 `UNMODELLED`, and 62 explicitly named `BELLMAN_ERROR` tuning
rows. Issue #507's 21 target frames finish as 15 matches, two complete-line equivalents, one stale
label whose rationale agrees, and three named Bellman errors. These counts are the prototype's
honest tuning baseline; they are not recaptured as correctness.

All 1,989 offered corpus selection indices are covered by 1,623 semantic actions and transition
without `Unknown`. End remains exactly zero,
benefitless non-End actions remain negative, attacks resolve through nested riders and forced
promotion before terminal value, and the two Cinderace/Lillie's/Boss boundary fixtures pass. This
ADR establishes the complete architecture and live cutover, not a claim that the initial human
seeds are already a competitive policy. The adjudication ledger is the queue for subsequent
economic tuning without restoring rules-based strategic owners.

Submission collection preserves every emitted Bellman root ledger, branch diagnostic, cap, and
alternative in `performance.jsonl` under `telemetry.diagnostics`, indexed by match and decision.
The count/tier summary remains for dashboards, and raw Kaggle agent logs remain canonical.
