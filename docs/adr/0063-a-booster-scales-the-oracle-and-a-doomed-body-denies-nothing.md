# ADR-0063: A booster scales the oracle; a doomed body denies nothing; banked Energy is worth what it will pay for

**Status.** Accepted and **BUILT 2026-07-14 (`/tdd`)**, default ON — three amendments to ADR-0062's
energy-denial oracle, all correcting live defects. Suite green.

Supersedes nothing; **amends ADR-0062** and retires the `energy_denial` half of ADR-0026's
`disrupt-when-unfavored`.

## Context

ADR-0062 priced the Crushing Hammer correctly — `coin × what the strip takes away − the cost of
keeping the Item` — and then left three holes around that price. A sweep of **all 16** human
corrections mentioning a Hammer, each retested through the real Pilot, found them.

### 1. A flat booster overrode the oracle (CRITICAL, and self-inflicted)

**ms 83968638 f17.** Their Active is an Abra on 1 Energy; their whole bench is bare; my Active can
already KO. `_denial_play_tactical` stands down correctly — **tac 0.0**. And the Hammer was played
anyway, because `disrupt-when-unfavored` fired **+18**:

```
active_can_ko   = True
opp_denial_best = 10.0

_denial_play_tactical  -> 0.0    the oracle says HOLD
disrupt-when-unfavored -> +18    gate is `opp_denial_best > 0`  == True
                                 => score 18 > 0 => free Item => _finish_turn_last tier 0
                                 => PLAYED, right before the KO
```

Human: *"Must use turn planner to see that using Crushing Hammer here is a waste. we will KO the
opponents active."*

The rung's own rationale claimed it *"rides on top of the base disruption rule so it never boosts a
wasteful one"* and *"never overrides a KO."* Both were true when it rode the **flat**
`play-energy-denial` (+20) — a rung that only ever fired when a strip was worth making. ADR-0062
retired that rung and replaced it with a **signed tactical**, and re-gated the booster onto
`opp_denial_best > 0` — the raw *presence* of denial. Presence is not the oracle's verdict. **A flat
positive rung stacked on a signed oracle can always resurrect a hold**, and a free Item needs a
non-positive score to be declined at all.

This is [[hold-evolution-weight-inert]] one more time, in its third costume: the guard was calibrated
against a rung that no longer exists.

### 2. `active_can_ko` blanked the whole board, not just the doomed body

**ms 82748422 f26.** The stand-down zeroed `opp_denial_best` outright. But *"I am about to KO their
Active"* only says the **Active's** Energy is worthless to strip — it dies anyway. It says nothing
about a benched Mega Starmie ex sitting on **3 Energy** (Nebula Beam 210 → Jetting Blow 120: the
strip denies 90). Hammering the bench and *then* taking the KO costs nothing. The fix over-corrected
"don't waste the Hammer on a dying body" into "don't play Hammers on KO turns."

### 3. Energy on a pre-evolution is BANKED, not spent

**ms 82225643 f12.** Their Active is a **Riolu** holding 1 Energy. `denial_value` reads the target's
**own** attacks — Riolu's is *Accelerating Stab* (`{F}`, **30**) — so the strip priced at 30 and the
Hammer squeaked through at **+5.00**.

But `docs/rules.md:98`: **"Evolving keeps attached cards."** And Riolu is the *sole* pre-evolution of
**Mega Lucario ex** — a single hop, no intermediate Lucario in this set. That Energy is not paying for
a 30-damage Accelerating Stab. It is being **banked**: the turn it evolves, it pays **Aura Jab**
(`{F}`, **130**).

The margin tells the story. That Riolu passed *only* because it happened to be **Active**. On the
**bench** — where a pre-evolution normally banks Energy — `_DENIAL_BENCH` takes 30 to
`0.5 × 30 × 0.25 − 10 = −6.25` and **we hold the Hammer.** The archetypal case failed; the one
correction we had passed on a technicality.

Human: *"next turn he might evolve to opponents main attacker, mega lucario."*

## Decision

**1. `_DENIAL_UNFAVORED = 0.3` — the unfavored Read SCALES the oracle, inside it.**

```
play value = coin_odds(card) × _DENIAL_PLAY_W × (1 + _DENIAL_UNFAVORED if unfavored) × opp_denial_best
             − _DENIAL_ITEM_COST
```

A multiplier **cannot flip a sign**: scaling a whiff (0) leaves 0; scaling a hold (negative) leaves it
negative. The ADR-0026 intent survives — an unfavored race still makes a *real* strip worth more — but
it can no longer manufacture one. **The `energy_denial` half of `disrupt-when-unfavored` is RETIRED.**

Its `hand_disruption` half **survives**, and the distinction matters: that half fires against an
`opp_has_hand_size_attacker` (Alakazam's Powerful Hand scales damage with hand size), where the strip
denies **damage**, not cards — a quantity ADR-0060's swing oracle does not model. It is a proxy for an
*unmodelled* value, not an override of a *modelled* one. (I initially believed it carried the identical
bug; reading the gate proved otherwise.)

**2. A doomed Active is dropped from the denial max, not the board.**
`_opp_denial_best(opp, active_doomed)` removes only the Active's tier. `_denial_target_tactical`
likewise scores the doomed Active's Energy at 0, so a won flip lands on the bench instead of shaving a
corpse.

**3. `_DENIAL_FORWARD = 0.5` — denial is measured against the forward form too.**

```
denial(body) = max( denial_now(body),  _DENIAL_FORWARD × max over forms it evolves into )
```

Discounted, never face value: the payoff is a **turn away** (they must evolve first) and **contingent**
(they must actually hold the evolution). The bound is **derived from two frames, not tuned to taste**:

| frame | forward | must | forces |
|---|---|---|---|
| ms 82225643 f12 — Active Riolu, 1 Energy | Mega Lucario ex (130) | **PLAY** | `_DENIAL_FORWARD > 0.154` |
| dx 85046350 f32 — Active Gabite, 1 Energy | Garchomp (100) | **stay under the retreat-to-wall (30)** | `_DENIAL_FORWARD < 0.8` |

The second is the load-bearing one. At **face value** the Gabite's forward form prices the strip at 100,
the Hammer leaps from +10 to **+40**, buries both the evolve (20) and the retreat-to-wall (30) — and a
CRITICAL comes straight back. *This is the ADR-0060 trap exactly: a big new positive term voids every
guard sized against the old one.* It was caught by measuring before building, not after.

## Consequences

All 16 Hammer corrections, retested through the real Pilot:

| frame | denial | Hammer | plays | human |
|---|---|---|---|---|
| ms 82224509-67 | 130.0 | +74.50 | yes | PLAY ✔ |
| ms 82225643-12 | 65.0 | **+22.50** | yes | PLAY ✔ *(was +5.00 — the knife-edge)* |
| ms 82525101-92 / -102 | 140.0 | +60.00 | yes | PLAY ✔ |
| ms 83968638-17 | **0.0** | **0.00** | **no** | HOLD ✔ **(the CRITICAL)** |
| dx 85046350-32 | 50.0 | +15.00 | **no** | HOLD ✔ *(loses to the retreat, 30)* |
| ms 82749168-21 / -29 | 17.5 | −1.25 | no | HOLD ✔ |
| ms 82752604-14 | 8.8 | −5.62 | no | HOLD ✔ |
| ms 82750161-29 · 82753102-37 · 82754241-41 · 85163634-41 · dx 85045840-6 | 0.0 | 0.00 | no | HOLD ✔ |

**One deliberate divergence from a human label: ms 82748422 f26** now plays a Hammer at **+1.25**. The
human called that Hammer worthless — but they were reasoning about stripping **Cinderace**, the Active
we KO this turn. The Hammer the oracle now wants is on the **benched Mega Starmie ex holding 3 Energy**,
and the user's ruling is explicit: *"Doing a hammer against a bench pokemon then KOing the active is of
course just fine."* The label is narrower than the doctrine. The margin is +1.25 — i.e. noise — and it
is recorded here rather than buried.

`_POSTURE_UNFAVORED` / `_POSTURE_FAVORED` / `_POSTURE_MIN_COVERAGE` move from `baseline_disruption.py`
into `strategy/context.py` (and its explicit `__all__` — the ADR-0062 sharp edge), because the
Hypothesis layer and the priced oracle now both read them and they must have exactly one home.

## Deferred

- **Reachability of the forward form.** `_DENIAL_FORWARD` credits a Riolu's Mega Lucario ex without
  checking they still *have* one. Our deck-odds machinery (ADR-0029) reads **our** deck; the
  opponent's would need the γ-gated Read. The discount absorbs this for now.
- **`forward_card_ids` is multi-hop.** A Dreepy is credited for a Dragapult ex two evolutions away at
  the same discount as a Riolu one hop from Mega Lucario ex. A hop-count decay is the honest model; no
  correction yet demands it (ms 82752604 f14, the 2-hop case, holds at −5.62 with room to spare).
- **Enhanced Hammer's Special-Energy filter** and **multi-Hammer sequencing** — both re-examined this
  round. Multi-Hammer turned out to be a **phantom**: `decide()` is greedy per-frame and rebuilds the
  Board from fresh `obs`, so Hammer #2 already re-reads the post-strip board (proven on ms 82525101
  f92: `opp_denial_best` 140.0 → 130.0 after the first strip resolves). Nothing to fix.
