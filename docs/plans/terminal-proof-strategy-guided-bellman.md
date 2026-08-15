# Terminal-proof, Strategy-guided Bellman decision record

Status: accepted.

## Decision

Normal-turn planning uses this precedence:

```text
guaranteed same-turn Terminal Proof
-> General + Deck + matched Opponent Strategy Snapshot
-> Strategy Beam searched to completed current-turn outcomes
-> Bellman widening and admissible bound proofs
-> best completed executable path at timeout
```

Pregame declarations and mandatory engine selections remain outside that pipeline.

## Ownership

Terminal Proof owns verified same-turn wins and runs first. It abstains under unresolved uncertainty.

Strategies are authored, conditional traversal hints. They rank promising actions and paths by match strength. They
never add reward, alter board utility, prove a branch inferior, or stop search when satisfied.

Bellman owns sequencing, successor-state value, widening, admissible pruning, and final choice. It searches focused
paths deeply enough to obtain completed executable outcomes, then widens across every unresolved legal path until a
Bellman bound proves it cannot beat the incumbent or time expires.

Pokémon Roles are value inputs. Own-deck Roles price development and preservation; scouted opponent Roles distinguish
primary attackers, secondary attackers, and support Pokémon when valuing damage and KOs. Trainer cards use shared
Card Functions, not deck Pokémon Roles.

Demand Slots remain the value-side model for resource access and retained options. They are not Strategies.

## Proof obligations

- A Terminal Proof wins in the current turn under every represented positive-probability outcome.
- Every permanent branch deletion records an independent legality, equivalence, dominance, or Bellman-bound proof.
- Strategy ON/OFF changes traversal order only; exhaustive search returns the same policy.
- Timeout returns the best completed executable path, never an unfinished hint.
- New strategy-relevant information starts a new Planning Epoch and recombines all three Strategy layers.
