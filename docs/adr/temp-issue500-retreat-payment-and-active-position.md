# ADR-TEMP-500 — Retreat payment is unit-funded; Active-position access is one state potential

Status: Accepted and built for Issue #500.

## Decision

Retreat Cost is paid by supplied Energy units and discards whole attached Energy cards. The canonical
enumerator derives every card's current holder-aware provision, permits every reachable stop set, and
stops a path immediately when the remaining cost reaches zero. Unknown provision refuses.

Readiness owns one additional consequence: the current-turn option to exercise a legal manual
retreat. Its value is the positive maximum of `position_state_value(after) -
position_state_value(before)` over the registered retreat outcomes. The position projection is capped
attack realization plus nonterminal survival exposure. Terminal attack yield, lethal bands, predicted
loss, wall progress, and item-lock tempo remain outside it.

## Bounds and accounting

The attack board cap still applies only to attack realization. `ACTIVE_POSITION_MAX` derives from
that cap plus the maximum ranked survival exposure over six three-prize bodies. It joins
`POSITIONAL_MAX`, preserving loss/win dominance by construction. Before exercise, readiness carries
the option; after exercise, the allowance is spent and the better position is realized.

## Consumers

`board_choice` ranking synthesizes and scores exact post-retreat boards. Energy and Tool attaches
apply their real transition and consume `active_position_delta`; no fixed fraction or clamp survives.
The promote/retreat local working exposes `position_delta` and retains only specialized residuals.

## Consequences

The state-value contract advances to schema 3. Unknown legality remains numeric zero with UNKNOWN
diagnostics. Known unavailable or non-improving retreats are KNOWN zero. Runtime policy contains no
deck, card, frame, or correction identity branch.
