# ADR-0150 — Energy concentration and rental energy: the spread-vs-concentrate ruling priced

Status: Accepted (2026-08-20); BUILT. Follows ADR-0148; owner's sitting of the same day.

## Context

The deferred spread-vs-concentrate doctrine conflict was ruled by the owner: **concentrate is
the default** — keep feeding the started, non-doomed body toward its BIG attack before
starting new bodies; never feed a doomed body; prefer basic energy where it does the job.
**Diversify is a tempo exception** — read the opponent's strength; with an easy KO next turn
and no live threat, a second minimally-functional attacker beats over-stacking (recorded on
frame 92645419-25; the threat-read half is planner scope).

The evaluator could not express the default. Attached energy priced LINEARLY per usable unit,
so twin recipients tied exactly (+0.0350 vs +0.0350 on the decomposed frame) and the menu-
index tie-break picked the bare twin. And Ignition Energy — *"discard it at the end of your
turn"* — priced on a benched body as durable stock, when it evaporates before that body can
ever attack: two rulings (83116501-89, 82752045-97) were RE-RULED by the owner from Ignition
to the basic {W}, same started recipient.

## Decision

- **Concentration term** (`evaluate._body_value`): each body earns
  `concentration x worth x discount x progress^2`, where `progress` = usable units over the
  body's LARGEST reachable attack cost (`worth.top_attack_cost` — own attacks in full, line
  evolutions through the reach gate). The square is the doctrine: the second energy toward a
  three-slot attack is worth three times the first on a fresh body, and the finishing energy
  most of all. `concentration` is an ordinary weight, default 0.0 = the term is off —
  shipping it changes nothing until a round arms it.
- **Rental energy** on a BENCHED body prices zero: an energy whose record carries
  `discard_eot` contributes no attached worth off the Active Spot. Static, from the card
  facts — no retreat-feasibility reasoning; the rare attach-then-promote-same-turn line stays
  planner scope. On the Active it prices normally (it can pay this turn's attack).
- The injured-recipient half of the ruling needs NO new mechanism: `_body_value` already
  scales the whole body — attached energy included — by remaining HP (`damage_floor` is the
  strength lever).

## Consequences

- Both re-ruled frames agree at DEFAULT weights (pinned in `test_ledger_corpus.py`): killing
  the bench-Ignition options alone lets the ruled basic-{W}-to-the-started-body pick win.
  Corpus at defaults: starmie 148 → 152 of 345, zero regressions.
- The tempo-exception frame (92645419-25) intentionally stays a miss: this term pushes
  concentrate there too, and the exception requires the threat read the 1-ply brain lacks.
- Evaluator mechanism tests pin both shapes (2-and-0 beats 1-and-1 when armed; splits tie at
  0.0; bench rental worth == bare body, active rental > bare).

## Addendum 2026-08-21

Armed at 0.1 by owner order, trading the zero-flip gate: 208 -> 213 of 426 (13 up, 8 down),
floor dragapult_ex 41.9%. Arming exposed that benched rentals counted as attack progress in
the concentration term; they no longer do (same rental ruling: it evaporates, so no progress).
