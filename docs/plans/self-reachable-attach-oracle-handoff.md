# Self reachable-attach affordability oracle — build handoff (2026-07-22)

**For a session building the SELF-side attach oracle.** One shared primitive answers "**which attack
can MY body pay THIS turn**, given everything I can attach this turn" — the mirror of ADR-0064's
opponent-side `reachable_incoming` ("what can the OPPONENT deal me next turn"). It is currently
approximated by three separate partial signals; unifying them dissolves a live false-famine bug and
unblocks two deferred promote/retreat terms. Companions: `valuation-systems-coverage-review.md`
(the finding log), `promote-retreat-grill-spec.md` (two blocked consumers), `threat-clock-unification-handoff.md`
(the opponent-side twin).

## The finding — one primitive, first surfaced at dragapult f70

`dp_stall_gust_false_famine_accel_f70` (user ruled 2026-07-19, "100% our choice"): Active Dragapult ex
at **0 Energy**, hand holds **Crispin** (`tutor_energy`). The stall-gust equation fired a famine stall
(+105) reading "0e → can't attack". **FALSE:** Crispin attaches one Basic Energy by its effect AND
hands a second of a different type, which the unused manual attach then plays → Dragapult ex reaches
`{R}{P}` THIS turn = **Phantom Dive 200 + 6 counters**. The stall forgoes the 200 (all three hand
cards are Supporters — Boss's-stall and Crispin-attack are mutually exclusive).

The user's ruling: **fix at value altitude, not with a stall-gust gate.** A body's "can't attack" is
not "0 attached Energy" — it is "the cheapest attack is unpayable **even after this turn's full attach
budget**." That budget is a first-class quantity the whole codebase currently under-reads.

## The oracle — symmetric to `reachable_incoming`

```
reachable_attach(my_body, target_attack | "cheapest", *, attach_budget) -> bool     # payable?
      attach_budget this turn =
          manual_attach              1 wild attach, IFF board.energy_attached is False
        + Σ over hand cards:         the attach EFFECT of each playable `tutor_energy` / `energy_accel`
                                     card (Crispin: +1 typed from deck AND hands a 2nd of a different
                                     type the manual attach then plays; per-card supporter/item quota
                                     respected — one Supporter/turn), modelled at its FULL yield, not +1
    payable = the target attack's TYPED cost (per-slot EnergyType; 0 = colourless) is coverable by
              attached Energy + the budget (greedy typed match, the `_typed_can_pay` discipline)
    famine  = reachable_attach(my_body, "cheapest") is False        # the cheapest attack unpayable even so
    readiness_p (EV variant, ruling 3) = P(the budget lands) — 1.0 for a CERTAIN in-hand/deck-certain
              enabler; the hypergeometric draw for an out still in the deck (deck_odds), for the
              promote/retreat `fetch_enables_p` middle.
```

Mirror of `reachable_incoming(my_body, opp_bodies, charged=...)`: same "budget a development step, then
test affordability" shape, opposite side of the table. `reachable_incoming` charges the OPPONENT's
accel policy against MY survival; `reachable_attach` charges MY accel budget toward MY attack. Build it
**beside** `reachable_incoming` in `strategy/combat.py` (`CombatMath`) so the two read as one family.

## What exists today — three partial approximations to REPLACE

| signal | where | what it under-reads |
|---|---|---|
| `Board.active_attack_payable` | `pilot._active_attack_payable` | attached + best single hand-attach — **no deck-fetch accel** |
| `Board.active_attack_payable_via_accel` | `pilot._active_attack_payable_via_accel` (4633) | one `tutor_energy`, **exactly +1 attach**, **cheapest** cost only (`len(energies)+1 >= minAttackCost`) — misses the FULL budget (2-cost `{R}{P}`) and multiple accel cards |
| `_promote_fetch_p` | `pilot` (1697) | reuses `_via_accel` → 1.0/0.0, **no hypergeometric middle** |

All three are `active`-only or `+1`-only or boolean-only. The oracle generalises all: **any body**,
**full budget**, **any target attack**, with an **EV** variant.

## Consumers (build the primitive once; wire these)

1. **Stall-gust famine** (`doctrine_gust`, the f70 bug). Replace the `0e / active_attack_payable`
   premise with `famine = not reachable_attach(active, "cheapest")`. Dissolves the false +105 stall on
   ep dragapult f70. **The original driver — verify this frame first.**
2. **Posture / doom** consumers of "can't attack" (per the coverage-review finding) — same swap, no new
   rung/gate; they inherit the corrected famine.
3. **Promote/retreat `fetch_enables_p`** (`promote-retreat-grill-spec.md` §Build status, ruling 3). The
   INTERIM ships the certain 1.0/0.0 (`_promote_fetch_p` → `_active_attack_payable_via_accel`); point it
   at `reachable_attach`'s **readiness_p** for the probabilistic middle. Pure upgrade, same call site.
4. **Promote/retreat Finding B2** (`promote-retreat-grill-spec.md` §Sweep #4). The whether-site's
   `stay_yield` under-prices "staying finishes powering the attacker" — the 3 residual regressions
   (`81905522-47`, `82749168-61` = attacker one attach from ready; `83007714-8` = turn-1 setup). Add a
   **stay-to-develop** term = `reachable_attach(current_active, its_biggest_attack)` on the stay side,
   symmetric to the promote side's `fetch_enables_p`. Same oracle, both sides of the retreat diff.

## Build shape

1. `CombatMath.reachable_attach(my_body, attack_id|None, *, attach_budget, hand, board_flags) -> bool`
   beside `reachable_incoming`; a thin `attach_budget(me, board)` helper enumerating manual + in-hand
   accel effects (the card-effect model is the real work — read each `tutor_energy`/`energy_accel`
   card's actual yield from stats/functions, fail-CLOSED on an unmodelled effect so a PROVABLE famine
   still fires the stall). SOUND under-count, never over: a false "can attack" is the catastrophic error.
2. Wire consumer 1 (stall-gust) first, gate on the f70 fixture + the full gust corpus (no regression to
   `test_gust_round0_corpus.py`). Then 2 (posture/doom, inherit). Then 3/4 (promote/retreat, shadow-only
   — free, reporting).
3. Readiness_p (EV) reuses `deck_odds.draw_hit_probability` + `fetch_closure` for the still-in-deck out;
   the certain enabler is the `deck_definitely_has` / in-hand branch → 1.0.

## Hazards

- **Fail-closed is load-bearing.** A false "can attack" turns off a stall / mis-prices doom (live
  deciders). Model only card effects you can read at source (verify per the CLAUDE.md rule); unknown →
  treat as no budget. Symmetric to `reachable_incoming`'s ceiling discipline but the OPPOSITE fail
  direction — here under-count the budget, there over-count the threat.
- **Supporter/Item quota.** One Supporter per turn; a `tutor_energy` Supporter and a manual attach can
  co-occur (f70), two Supporters cannot. The budget helper must respect `board.supporter_played`.
- **Full budget, not +1.** The whole point is the 2-cost reach (`{R}{P}`), not the cheapest slot —
  `_active_attack_payable_via_accel`'s `+1` is exactly the bug.
- The promote/retreat consumers are SHADOW (reporting-only) — zero live risk; stall-gust/posture/doom
  are LIVE — corpus-gate every swap.

## Corpus anchors

- `dp_stall_gust_false_famine_accel_f70` (the primitive's reason to exist — the +105 false stall).
- Promote/retreat B2: `81905522-47`, `82749168-61` (attacker one attach from ready), `83007714-8`
  (turn-1 setup) — the whether-site regressions the stay-to-develop term should convert
  (`tools/train/probes/promote_retreat_decider_sweep.py` measures it — the shadow-era
  `tools/train/promote_retreat_sweep.py` was deleted by #141/ADR-0073, which retired the record
  and the sign bit it read).
- `fetch_enables_p` has no corpus frame that drives it >0 today (the pick/whether fixtures fail-close
  correctly); the readiness_p upgrade wants a fresh 1-attach-short-wincon-with-hand-accel fixture.
