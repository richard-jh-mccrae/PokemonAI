# ADR-0061: A locking attack's value includes its forced follow-up (Horizon-2)

**Status.** Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default
ON — it replaces a live constant rather than adding a new seam. Suite 2881 green.

## Context

**42 attacks in the pool carry a next-turn lock**, and they are two structurally different things that
`_LOCK_COST = 40` charged one flat number for:

| lock kind | text | example | two-turn damage | the flat 40 |
|---|---|---|---|---|
| **same-attack** | *"...can't use Mega Brave"* | Mega Lucario ex: Mega Brave 270 `{F}{F}` / Aura Jab 130 `{F}` | 270+130 = **400**, and 130+270 = **400** | **phantom charge** |
| **full** | *"...can't use attacks"* | Bloodmoon Ursaluna ex: Blood Moon 240 | 240 + **0** = **240**, losing to a lock-free 130/turn's **260** | **5× under-charge** |

The load-bearing fact for the same-attack kind: **you can never Mega Brave twice in a row whichever you
open with.** The alternation binds *both* orderings, so the lock forfeits nothing the other ordering
would have had. Charging 40 for it put a standing thumb on the scale toward Aura Jab, on top of the
+225 its recover rider was already collecting.

`AttackStat` has carried the two flags separately (`nextTurnSelfLock` vs `nextTurnSameAttackLock`) since
ADR-0033; only the scorer collapsed them.

Separately, the recover rider (Aura Jab: *"Attach up to 3 Basic {F} Energy from your discard pile to
your Benched Pokémon"*) was credited **75/energy** gated on one thing: `board.my_bench` being non-empty.
Three `{F}` onto a Lunatone/Solrock support bench scored an identical **+225** to three `{F}` onto a
Riolu that becomes the second Mega Lucario ex — and that +225 is exactly what tips Aura Jab (130) over
Mega Brave (270).

## Decision

**When an attack locks, next turn's option set is not a branching space to search — it is forced and
known.** A full lock means this Pokémon deals 0; a same-attack lock means next turn is its best *other*
affordable attack. So the follow-up is **evaluated, not explored**:

```
followup(A)  = 0                                    if A locks all attacks
             = best OTHER affordable attack         if A locks itself
             = best affordable attack               otherwise

lock_cost(A) = _FOLLOWUP_W * (max followup any pick leaves  −  followup(A))
```

Expressed as a cost (never a credit), so attacks keep their scale against develops. It is **0** for any
lock-free attack, **0** when the Active is `active_doomed` (there is no next turn — every lock is free,
front-load), and **0** on the Active's only affordable attack (chipping must still beat passing — the
one invariant `_lock_cost_applies` held, preserved).

`_FOLLOWUP_W = 0.5`. Below 1 because damage **this** turn is certain and next turn's is not — the
opponent moves in between and can KO us, heal, or switch the target away. At weight 1 the two Mega
Lucario orderings score *exactly* equal (which is the honest statement that the lock costs nothing); the
discount is what makes the front-loaded nuke edge the alternation when nothing else separates them.

**This is multi-turn reasoning without a tree.** It is the shape that has shipped here four times
(ADR-0039 gamble lines, ADR-0040 objectives, ADR-0044 opponent-choice reads, the Lethal Solver). The one
actual search — Tier-6 escalation (ADR-0043) — lost 12 points on a valid mirror instrument and stays
parked. Closed-form beats a budgeted tree whenever the branch factor is 1, and a lock makes it 1.

### The recover rider, bounded by what a recipient can use

`_recover_units` now takes **three** independent closed-form bounds instead of one:

1. `recoverN` — the card's printed ceiling ("attach up to 3").
2. the matching Basic-Energy **fuel** in my open discard — re-sourced from **`board.my_discard_basic_energy`**,
   which finally gives that Board field the consumer it was written for. (`_damage_context` keeps its own
   attacker-relative copy: that one must also serve the *Incoming* direction, so they are not duplicates.)
3. the recipients' remaining **need** — measured against each body's **forward form**, so a benched Riolu
   counts the `{F}{F}` its Mega Brave will cost, not the `{F}` its Quick Attack costs today.

Energy nobody can pay an attack with is not development.

## Consequences

- ml **f111** (`active_doomed`, lethal Mega Brave): the cooldown charge collapses to **0**. The old flat
  40 docked a game-winning KO for a flexibility the Active was never going to get to use.
- ml **f88** (Active alive): Mega Brave is charged **70** — derived from `270 − 130`, its own alternative
  — not 40. Swap the Pokémon's other attack and the number moves, as it should.
- A **full-lock** attack (no pool card in the three decks has one, but 9 in the pool do) is now charged
  the whole turn it costs, ~120–140 rather than 40.
- `_LOCK_KO` (the KO-branch sub-prize tiebreak) is now gated on `lock_cost > 0`, so a same-attack lock
  with an equal-value alternation is no longer charged there either.

## Deferred (deliberately not built)

- **A role/quality discount on the recover recipient** — "energy on a support bench is worth less than
  energy on the wincon line". Plausible, and the user raised it, but **no correction demands it**, and the
  ADR-0060 build had just demonstrated what happens when an unmeasured term is given a large magnitude
  (it silently voided the entire hand-quality guard family). The need-cap shipped here is *provable*
  (energy nobody can pay an attack with is not development); a role discount would be a guess. Revisit
  when a real frame shows the misplay.
- **Horizon > 2.** The follow-up is forced only for ONE turn; beyond that the option set branches again
  and this stops being closed-form.
- **The opponent's reply.** `active_doomed` is a worst-case flag, deliberately (ADR-0031). A survival
  *probability* would price the "probably survives" middle band that a worst-case flag rounds to doomed —
  but that is a new probabilistic term, and the repo's doctrine has been to keep `active_doomed`
  worst-case on purpose.
