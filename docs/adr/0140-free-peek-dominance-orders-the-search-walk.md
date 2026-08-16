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

**Amended 2026-08-16 (same day, re-adjudication complete): the split premise did not survive.**
The "Ignition-attach-before-Pokégear ruling" was a test pin flipped by `546369c9` to track a
solver budget flip — the frame's own human `turn_plan` reads "pokegear > replan > attach basic
energy to active", i.e. peek-first.  The worklist grew to nine overridden frames at arming and
every one is now resolved — see *Re-adjudication of the nine overridden frames* below.  The gate
stays armed; the reconciled principle and the narrowed trigger it implies are recorded there.

**Built 2026-08-16 (same day): the narrowed trigger and the two value fixes now ship** — see
*Build round* at the end.  Eight of the nine frames hold their human ruling under the armed gate,
the two budget-flip frames still pass, and the ninth (`8db4265d078d`, no human frame ruling) is
unpinned and ledgered.

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

The gate defers to the value model where the model already knows better (developer-directed
expansion, 2026-08-16).  Playing a card is never free — the ledger charges every play's hand
worth, floors a dead fetch's held worth, credits discarding dead cards as payment, and prices a
peek's benefit through reveal continuations enumerated over the actual remaining deck — so two
situations the model already prices correctly must not be overridden by ordering:

1. **A dead peek orders nothing.**  If the peek's fetch window has zero live targets in
   `deck_counts` (`fetch_target_matches`, WINDOW reading), it carries zero information and the
   gate ignores it.
2. **A discard-cost play disarms the whole node.**  If any legal play carries a
   `cost`/`cost_required` clause (Ultra Ball class), the peek may be worth more as discarded
   payment than as a peek — with one supporter allowance, a fetched Supporter can even be
   unplayable — and only the Bellman cost-benefit can weigh that.  The node is left ungated.

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

## Re-adjudication of the nine overridden frames (2026-08-16)

Method: each frame replayed through the deployed runtime armed and disarmed
(`AGENT_OVERLAY` = `tests/fixtures/agent_overlays/information_dominance_off.json`), read against
its full board (`tools/train/blunder/frame_view.py`), its Correction record, and the pin history.
A fact that reframed the worklist: four of the nine failing pins were not human rulings at all —
`546369c9` (2026-08-15, the 1.6x throughput round) re-pinned them to post-speed-up solver picks
without a `reviewed.json` disposition, each against the record's own words (two `turn_plan`s,
two CRITICAL `correct` labels).

**Machine re-pins reverted to the human ruling — the armed gate agrees with the human:**

| frame | human artifact | armed pick | outcome |
|---|---|---|---|
| `810eb9a2ae5c` / 92708809-35 | turn_plan "pokegear > replan > attach basic energy to active" | `[0]` Pokégear | pin restored to `[0]`; passes armed |
| `8db4265d078d` / 92455378-89 | turn_plan "pokegear first, fetch Wallys if able" | `[0]` Pokégear | pin restored to `[0]`; passes armed |
| `231db774b45e` / 92459166-93 | correct `[0]` Staryu ("need a staryu on bench for backup") | churns `[0]`/`[1]` | UNPINNED: isolated replays (both arms) pick the ruled `[0]`, in-suite armed runs can pick `[1]` — the 546369c9 speed-up flipped this deadline-limited recovery menu off the ruling and the armed gate leaves it timing-churned.  User re-confirmed 2026-08-16 and sharpened the stakes: the bench is EMPTY, the hand holds no Pokémon, and the 60/330 Active faces a 270 hit — a KO with no replacement loses the game outright (`docs/rules.md` §7.2), so the recovered Staryu is the only card in reach that removes the instant-loss line and must dominate the energy pick STRUCTURALLY (loss-prevention pricing), not by timing luck.  Standing disagreement, same class as ADR-0095's 82225643-11; a value fix, next build round |

**Rulings that stand — counterexamples to the armed trigger, kept gating under the gate-off
overlay (production stays armed by developer request):**

| frame | ruling | armed pick | counterexample class |
|---|---|---|---|
| `b028d86ba9da` / 82228017-4 | attach {W} ("dont waste the mega signal"; two Mega Starmie ex already in hand) | plays Mega Signal | spendable tutor + deck-count liveness is not hand-marginal liveness |
| `6a0242d3e39a` / 92459166-125 | attach {W} to the empty 330/330 Active (KOs the 10HP Mega Lucario ex) | plays Mega Signal | spendable tutor + its only target is PRIZED: `own_prizes=None` makes a dead peek read live in replay |
| `6858e8b5861b` / 83456015-35 | Wally's heal first (protects the 210HP Active from the modeled 210) | plays Pokégear | urgent Supporter pruned as a "neutral commitment"; the ruling orders the peek AFTER the heal, before the attach |
| `25c423bbb0ec` / 92708809-21 | Pokégear, never the dead Poffin | plays the dead Poffin | bound degradation: root-only gating does not reproduce it; deep-subtree gating degrades capped bounds until a ruled-out fetch wins the root |
| `cb70b1405932` / 92646350-132 | retreat (PR #523 supersession of the `[3]` label, now ledgered `refuted` per ADR-0088) | Jetting Blow | replay-liveness: the prized Mega Starmie ex makes the dead Mega Signal read live, arming the gate at a node it should ignore |

**The last conflict, resolved by the user (2026-08-16, same day):** `dbf1ff1d6fef` / 92591287-60 —
the record's `[0]` Salvatore STANDS.  The user's words: the rationale is the key — Wally's is
wasted healing only 50HP, *and it heals the benched Mega, which is far from doomed*.  `546369c9`'s
`[3]` Wally's re-pin is refuted.  The agent plays Wally's gate-off and a Mega Signal armed, both
with completed searches — a stable value error, not timing churn, so the frame is UNPINNED and
stands as a standing disagreement (the ADR-0095 82225643-11 treatment): the ruling stays active in
the corpus for the next build round.  Work items it names, specified by the user:

- **Heal pricing.**  Wally's value is the healed amount relative to the Mega's total HP, read
  against the damage the opponent can do to that body next turn, then compared against the other
  Supporters in hand for the one allowance.  The user's calibration: heal 50 of ~340 on a safe
  body → very little value; heal 50 of ~340 on a body currently doomed next turn → high value
  (the heal flips the doom calculus — 83456015-35 is exactly this and was ruled CRITICAL-correct);
  heal ~200 of ~340 on a safe body → pretty high value, to be weighed against the other
  Supporters in hand.
- **Supporter opportunity cost orders Salvatore vs Mega Signal.**  Signal (an Item) is only
  slightly weaker than Salvatore here: its fetched Mega cannot evolve the Staryu that entered
  play this turn, while Salvatore evolves straight from the deck and is usable on a Pokémon
  played this turn — and that ordering stands ONLY because no other worthwhile Supporter competes
  for the allowance; a live competing Supporter flips it (play Signal, spend the slot on the
  better Supporter).  Wally's-then-Signal reads coherent (both add some value; two Mega Starmies
  are already in play) and is still the wrong choice.
- Armed, the Mega Signal spend is a fourth spendable-tutor data point — it would even strip the
  deck's last Mega Starmie ex out of the ruled Salvatore line's own window.

### The reconciled sequencing principle

A free peek precedes a commitment **only when all four hold**; each clause carries its
counterexamples:

1. **Look-class peeks only.**  Pokégear (look-7, optional reveal) is what the rulings treat as
   free.  A tutor that certainly spends itself fetching a known card — Mega Signal, Buddy-Buddy
   Poffin, Salvatore — is a priced resource, and playing it is a commitment, not information
   (82228017-4, 92459166-125, 92591287-60).
2. **Live at the margin, prize-exact.**  The window must be able to return something the hand
   does not already supply (two Mega Starmie ex in hand make a Signal fetch worthless while
   `deck_counts` still says live), and liveness must subtract known prizes — replays carry
   `own_prizes=None`, so a peek whose only target is prized reads live and arms the gate on dead
   information (92459166-125, 92646350-132).
3. **Only over hand-and-deck-neutral BOARD commitments** — attach, evolve, retreat.  Never over
   Trainer/Supporter plays: the Supporter allowance makes them non-neutral by construction, and
   an urgent ruled play beats any reveal (83456015-35: ruled heal → peek → attach → attack; the
   peek belongs before the ATTACH, not before the HEAL).
4. **Ordering, never deletion, under caps.**  Weak dominance holds over true values, not over
   capped lower bounds: deleting completable commitment lines degraded bounds until a ruled-out
   dead fetch won a root three nodes away (25c423bbb0ec), and subtree gating flipped a node whose
   only root peek was dead (92646350-132).  The safe fallback is the pre-gate contract — the beam
   orders information first, the final selection stays a pure value comparison — and any pruning
   form needs the bound-safety condition above (prune only where the peek-first line completes
   within the cap).

Where all four hold, peek-first **is** the ruled order — both turn_plans, the two budget-flip
fixes (d31f6bfa4803, c7fd0670fb3e), and ADR-0095's 82225643-11 — and the ruled continuation
after the peek is a *replan*, not the pre-peek line.

### Narrowed trigger implied for the next arming

- Arm only on peeks that are look-class (`information_first` **and** no certain self-spend
  fetch), distinguishing Pokégear-class "look at the top N, may reveal" clauses from
  search-and-take tutors.
- Liveness = hand-marginal (at least one window target the hand does not already hold redundant
  copies of) **and** prize-exact where `own_prizes` is available; a stored frame without it must
  not count prized copies as deck.
- The prunable set drops declared-deterministic trainer plays: `{attach, evolve, retreat}` only.
- Bound-safety: no pruning at a node unless the retained peek-first subtree completes within the
  budget actually granted to that node.

## Build round (2026-08-16, same day): the narrowed trigger and two value fixes

The specifications above were built and measured the same day, by developer request.  Every claim
here is an A/B over the nine re-adjudicated frames plus the two budget-flip frames this ADR was
written to fix, replayed through the deployed runtime.  Score: **7 disagreements of 9 before, 1
after**, with both budget-flip frames still passing.

### The narrowed trigger (`solver.py`)

Clauses 1 and 3 became code.  `_peek_is_look_class` requires a bounded dig on every fetch clause
of the played card — the distinction the card table already carries, where 7 fetch clauses in
`card_effects.json` have `dig` and 53 do not, so a whole-deck tutor is a priced commitment rather
than free information.  `DOMINATED_COMMITMENT_KINDS` keys the prunable set on the action kind, so
no Trainer or Supporter play is ever dominated.  Together these two resolved four frames:
`82228017-4`, `92459166-125`, `83456015-35` and `92646350-132`.

Clause 2 needed no code.  `DecisionState.from_observation` already subtracts `own_prizes` from
`deck_counts`; the frames that read a prized target as live are a fixture limit, not a defect.

Clause 4 was attempted twice and **both attempts were rejected by measurement**.  Root-only gating
regressed to 5 disagreements of 9 — deep pruning is load-bearing for `8db4265d078d` and
`83456015-35`.  Arming only where a single live peek exists kept the budget-flip frames but did
not cure `25c423bbb0ec`.  No bound-safety condition ships; the frame that motivated it turned out
to have a different cause.

### Dead-fetch pruning (`solver.py`, `search.dead_fetch_pruning_enabled`, default on)

`25c423bbb0ec` was misdiagnosed as bound degradation.  The gate's only prunes at that frame were
retreats; the real defect was that a provably dead Buddy-Buddy Poffin scored 2.898 against the
ruled Pokégear's 2.197.  No Staryu remain in the deck and Cinderace is a Stage 2 at 160 HP, so the
fetch is dead by printed text — and the immediate ledger charged it only 0.105, a margin a
deadline erases.  The frame churned 1-in-3 before and is 3-of-3 after.

A play whose entire printed effect is an unconditional fetch reaching nothing in its named zones
moves only itself to the discard, so every continuation stays available without it with a strictly
larger hand: it is weakly dominated by skipping it.  This is the corpus's own standing rule —
`496a7657096f` and `baede6accfac` both pin that a dead Mega Signal must not detour the line — now
structural rather than a value margin.

### Per-body doom conditioning (`potential.py`)

The `damage` family already discounted own damage to `SAFE_DAMAGE_RESERVE_SHARE`, but on a
whole-board switch: one reachable-lethal body priced *every* body's counters at full weight.
`_lethal_exposure` now also returns the positions a printed attack can knock out and
`_damage_progress` discounts per body.

This is the user's heal equation.  Healing 50 of 340 on a body no attack reaches next turn is
worth 0.025 prizes instead of 0.25, while a heal that flips a doomed Active keeps full value —
`83456015-35`, ruled CRITICAL-correct, still passes.  `dbf1ff1d6fef` now plays the ruled
Salvatore, closing the standing disagreement above.

### Replacement risk (`potential.py`)

An Active knocked out with nothing to promote loses the game outright (`docs/rules.md` §7.2), and
the model priced that as the Active's prize value alone.  `_replacement_risk` puts the collapse in
the `game` family at the opponent's remaining prizes — unit-consistent with `prize_race`, and
larger the further the opponent still had to go.  Two clauses were forced by measurement, and both
made the rule *more* correct rather than less:

- **A Basic in hand discharges it.**  The bench being empty is not enough: a benchable Basic can be
  played this turn, so the loss is not forced.  Gating on the hand as well as the bench also moved
  the payoff onto the recovery node itself, where no search depth is needed to see it.
- **Fragility persists when no knockout is reachable yet.**  Gated on present reachability, the
  term vanished the moment a line healed the Active out of range, and `231db774b45e` came back as
  an *exact* three-way tie at 4.9487 with the search completing — the model could not tell a
  recovered Staryu from a recovered Energy from a recovered Cinderace at end of turn.  An exact
  tie across every option is a missing term, not a close call.  A board that cannot replace its
  Active is one unanswered knockout from losing whenever that knockout lands, so the liability is
  now weighted by `SAFE_DAMAGE_RESERVE_SHARE` when not immediately reachable — the same reserve
  the neighbouring damage term already uses, so no new constant enters the model.

`231db774b45e` now takes the ruled Staryu recovery decisively rather than by timing luck.

### One valuation change was built, measured, and reverted

Chasing the same tie, the stack-occupancy counting in `_hand_resources` / `_hand_demand` looked
wrong: one Mega over its own pre-evolution fills a capacity-2 `primary_attacker` job by itself, so
a spare Basic in hand priced at exactly 0.0.  Collapsing a stack to one occupant fixed the frame
and **regressed two adjudicated rulings** (`baede6accfac`, and `eb4fb1f19691` in
`test_m7_runtime`), cleanly attributed by A/B.

The counting is not a defect.  `_prize_job_capacities` counts the *cards along a prize route*, so
a route through a pre-evolution and its payoff asks for two slots of that job and a stack supplies
both.  Occupancy in cards and capacity in cards are consistent by construction; the change broke
that invariant.  It is reverted, and `_occupied_jobs` now exists only to carry that reasoning next
to the code.  The backup body the ruling wanted is a replacement concern, not a job-capacity one,
and belongs where it now lives.

### The one frame this round trades away

`8db4265d078d` / 92455378-89 flips to `[3]` Night Stretcher, deterministically (4 of 4 armed; 4 of
4 on the ruled `[0]` with `_replacement_risk` disabled).  The trade was taken deliberately:

- The frame carries **no human frame ruling** — its `correct` is empty and its `turn_plan` is
  `ungraded`.  Its pin came from this ADR's own re-adjudication, restored from the plan's stated
  first action after `546369c9` had moved it.
- The board is the same shape `_replacement_risk` was built for: empty bench, no Pokémon in hand,
  and an Active one attack from a game-ending knockout.  The plan's answer is conditional in its
  own words — "pokegear first, fetch Wallys **if able**" — a seven-card dig for a Supporter that
  would also bounce the attacker's Energy away, against a deterministic line that secures a
  replacement body.  The agent preferring the certain answer to a game-loss threat is defensible.

It is therefore **unpinned**, not re-pinned to the machine's pick, and ledgered in
`reviewed.json`.  A future round that wants the plan's ordering back should make the peek line's
payoff visible without depth, not weaken the rule that an unreplaceable Active is a lost game.
