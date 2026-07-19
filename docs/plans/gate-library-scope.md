# Scope: the deadline gate library (ADR-0065 §Round 8-9, the deferred leg)

**Status.** Scoped 2026-07-18. **Stage 1 (evolution gate) BUILT 2026-07-18** — `common/gate_library.py`
+ the `deploy_odds` factor in `card_worth.keep_cost`, wired on the gamble keep-floor and refresh SHED
(`planner._deploy_odds`). A PARAMETER of the one keep-value equation, not a new rung; latent on the
current pins (bites only a genuinely dead evolution), unit + synthetic-integration tested, zero
regressions. Stages 2–4 below remain. Under ADR-0065.

## The one-line problem

`keep_cost = role_value × (1 − re-access odds)` prices a held card by role and recoverability, but it is
**deadline-blind**: it assumes "needed this turn, met by having the card in hand." Two real cases break
that assumption, and both surfaced as the residue of the convergences:

1. **Gate OPEN, closing NOW (spike).** A held Drakloak that can evolve my Active *this turn* must not be
   pitched — shuffling/pitching forfeits the play, and re-access can't help because I need it now. But an
   *identical* held Drakloak when a benched Drakloak already covers the evolution IS fine to pitch. Same
   card, same role value, opposite keep-value — the difference is the **gate** (open-and-mine vs covered).
   → corpus `86091435-68`.
2. **Gate CLOSED / role not live (discount).** A held Mega Lucario ex with no Riolu anywhere is a *dead
   card* — its role can't be realized, so it should be cheap to shuffle/pitch to dig for the base. Flat
   `role_value` over-keeps it. → the `wincon_in_hand_undeployable` case (retired guard
   `hold-wincon-dont-shuffle`'s explicit stand-down; synthetic `test_hold_wincon_stands_down…`).

The spec's closed form (Round 8 §4) already names the fix:
```
keep_cost(X) = role_value(X) × [ P(need met by X's DEADLINE | keep X) − P(met | shuffle/pitch X) ]
```
Today's keep_cost is the special case `P(met|keep)=1`, `P(met|shuffle)=re-access`. The gate library
generalises "need met" to the **actual role realisation** (deploy the evolution, land the attach, …) and
its **deadline** (this turn / k turns / never), both **derived from runtime state — never authored**
(Round 9 §2).

## What actually needs it (measured against the shipped agent, not assumed)

| corpus id | gap | gate | clean win? |
|---|---|---|---|
| `86091435-68` | don't pitch a Drakloak that can evolve the Active *this turn* | **evolution gate** (open-and-mine vs `immediate_preevo_in_play` covered) | ✅ yes — the flagship |
| (correctness) | don't over-keep an undeployable wincon/pre-evo (`wincon_in_hand_undeployable`) | **evolution gate** (closed → discount) | ✅ yes — restores the retired stand-down, gradedly |
| `hold-successor-when-doomed` (kept guard) | keep the successor when the Active is doomed next turn | **pressure gate** (`active_doomed` → deadline next turn) | ◐ folds a surviving flat guard into the currency |
| `82749168-65`, `83969481-55` | Ignition/Wally's valued by *next-turn* need (refresh scores small-+, is chosen) | **quota gate** (k-th 1/turn resource → deadline k−1) | ◐ partial — entangled with the attack that should also win |

**NOT gate-library (do not over-claim):** `83038055-51`, `82752045-94`, `83037962-49` — the refresh
already scores negative there; the agent picks a *different* high-scoring option over the correct attack.
That is a **combat / attack-selection** axis, a separate concern. The refresh keep-value convergence did
its job on these; the gate library will not move them.

So the honest tally: **one flagship corpus flip** (`86091435-68`) + **one correctness restoration**
(undeployable discount) + **two flat-guard folds** (`hold-successor-when-doomed`, and cleanly retiring the
last hand-quality residue) + **two partial** (`82749168-65`, `83969481-55`). Not the whole "keep" family.

## The gate types (Round 9 §2) and their resolving state — mostly already on the Board

| gate | question | resolving state (EXISTS unless noted) |
|---|---|---|
| **evolution** | can card X evolve an in-play body *this turn*, and is it the only copy that can? | `evolvesFrom` (CardStat) + a body in play with matching name + `appearThisTurn` False + turn≥2 (the gamble evolution class already computes this) + `immediate_preevo_in_play` / `line_preevo_in_play` for "covered" |
| **quota** | is X the k-th held copy of a 1-per-turn class (attach/Supporter)? deadline = k−1 turns | `energy_attached`, `supporter_played`, hand copy counts (`hand_duplicate_ids`) |
| **recycler** | is X's discard-zone target non-empty (its role live)? | `my_discard_basic_energy` and the discard list (needs a small general "discard contents" accessor) |
| **pressure** | is a switch/heal needed by the threat read? deadline = next turn | `active_doomed`, `incoming_active_damage`, `reachable_incoming` |

The spec's promise holds: **the deck data only has to make each card's gate RESOLVE** — no authored
deadlines. The evolution and pressure gates resolve entirely from existing Board state; the recycler gate
needs one small accessor; the quota gate needs the k-th-copy index (derivable from `hand_duplicate_ids` +
the spent-quota flags).

## Design sketch

A pure `common/gate_library.py` (sibling of `fetch_closure.py` / `card_worth.py`), consumed — never
deciding:

```python
def role_met_odds(cid, board, *, keep: bool, stat_of, ...) -> float:
    """P(the card's ROLE is realised by its deadline) under keep vs shuffle/pitch. Per gate class:
       evolution: keep → 1.0 if the gate is open-and-mine (else it is covered/closed);
                  shuffle → P(re-draw a copy in time) if closed-this-turn, else the covered odds.
       quota:     deadline k−1 turns → widen the re-access window by (k−1) turns of draws.
       pressure:  active_doomed → deadline next turn; heal/switch keep floors accordingly.
       Falls back to the current fixed-window behaviour when no gate applies (a plain card)."""

def keep_cost_gated(cid, ...) = role_value(cid) × max(0, role_met_odds(keep=True) − role_met_odds(keep=False))
```

`planner._keep_cost` and `pilot._refresh_shed_keepcost` (and a NEW discard keep-floor rung) call
`keep_cost_gated` instead of the fixed-window `keep_cost`. The evolution-gate "spike/discount" is the
first and cleanest; it modulates the SAME currency, no new constants (currency-zone rule).

## Consumers and acceptance

- **Discard floor (new):** a `keep-role-live-at-discard` rung reading `keep_cost_gated` so a live-now
  evolution piece (Drakloak) is floored and an undeployable one is not. Gate: `86091435-68` flips,
  `83686860-18` (covered Drakloak) still correctly pitches — the acceptance PAIR that a flat floor fails.
- **Refresh SHED / gamble keep:** swap `keep_cost` → `keep_cost_gated`. Re-audit the six ADR-0060 pins +
  the corpus keep pins (the undeployable discount must not break the big-good-hand negatives).
- **Fold `hold-successor-when-doomed`** into the pressure gate once it's live (the last flat refresh guard).

## Risk & staging (build order)

1. ✅ **Evolution gate — the CLOSED/undeployable discount (BUILT).** As the `deploy_odds` factor of
   `keep_cost` on the gamble + refresh sites — a held evolution whose base is gone collapses to 0.
   Landed as an equation parameter (not a rung). NOTE: the deploy-now SPIKE on the *discard* side
   (`86091435-68`) was deliberately NOT built here — injecting a gate into the un-converged discard
   ladder means either a flat rung (the regression the currency-zone rule forbids) or a full discard
   convergence; it waits for the latter (see the grab/pitch finding in ADR-0065). The refresh/gamble
   discount needs no discard change and carries no such tension.
2. **Evolution gate into refresh/gamble keep_cost** (the undeployable discount). Re-audit the ADR-0060
   pins + keep pins. Medium risk (touches the converged keep-value sites).
3. **Pressure gate** — fold `hold-successor-when-doomed`; re-audit ep83037962 f49. Medium.
4. **Quota gate** (next-turn deadline for Ignition/Wally's). Highest entanglement with the combat axis;
   `82749168-65`/`83969481-55` need the attack to win too — gate the keep, but the flip may still wait on
   the combat-selection work. **Defer / do last.**

Each stage is corpus-gated and score-diff-gated, staged like the ADR-0064 five-call-site refactor. The
combat/attack-selection axis (`83038055-51`, `82752045-94`, `83037962-49`) is explicitly **out of scope** —
a separate investigation.

## Effort estimate

- Stage 1 (evolution gate + discard floor): ~a focused session. One module, one rung, the flagship pair.
- Stages 2–3: ~a session each, each a keep-value re-audit.
- Stage 4: gated on the combat-axis work; not self-contained.

Recommended cut for the next build: **Stage 1 alone** — it is the one clean, self-contained corpus flip
(`86091435-68`) with a built-in guard against over-keeping (`83686860-18`), and it stands up the
`gate_library.py` seam the later stages extend.
