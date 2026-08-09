# ADR-0133 - `latent_worth` is read on BOTH boards of a play, so discounting it cut the SPEND CHARGE, not the fetch credit

**Status:** **Rejected as specified** (Issue #444, built and measured 2026-08-09; build preserved at
`3989f99b`, reverted at `97cd2569`). Nothing ships. **Amends nothing.** Issue #444 returns to
`status:1-grilling` with its W1 direction refuted and question 3 — *does a search owe a charge at
all* — promoted from an open question to the only remaining one.

This is ADR-0122's shape: a change justified by what it measured rather than by what it shipped. It
differs in one way — ADR-0122 salvaged one narrow fix from the same measurement, and this one
salvages none, because the measurement says the defect cannot be reached from where the issue
pointed.

**Three numbers in this ADR's first draft were wrong and were corrected by its own `/code-review`
Spec axis before merge.** They are listed under *What the review caught* below, because the pattern
that produced them is more useful than the corrections.

## Context

Issue #444's premise was verified at `HEAD` before any code, by the `/implement` step-0 protocol, and
it reproduced exactly:

| the issue claims | measured on `7b507263` |
|---|---|
| `latent_worth` has three sites and no demand counterpart | `needs.py:320` (field), `state_value.py:829` (reader), `planning/leaf.py:137` (producer) |
| *positive control* | the same grep for `slot_demand` returns **7** sites incl. a live registry `reads=(...)` entry, so the instrument finds a wired demand leg where one exists |
| a no-slot card is credited `+0.075` prizes | `_GENERAL_WORTH_W 0.45 x ROLE_TIER 20.0 x POC_WORTH_PRIZE_RATE 1/120` |
| the leaf's copy skips the Pilot's discounts | leaf: `_GENERAL_WORTH_W * role_value`; Pilot: `worth * deploy * _GENERAL_WORTH_W * liq` |

So the asymmetry the issue names is real, and `85163634-17` fetches a **Staryu** whose eligibility is
`set()` — it fills nothing and books 9.0 Worth. The issue's **answer** — make the leaf's latent worth
match the Pilot's — is what does not survive.

## Decision 1 — the two aggregations of the formula are different quantities, and only one is the slot view

The build extracted `NeedsMixin._latent_row_worth` as the one formula and aggregated it twice:
`_general_worth_classes` per CLASS for the Pilot's `general` slot, `_latent_holdings` per ROW for the
leaf's `hand_worth`. **The split is load-bearing and is the one thing here worth carrying forward.**
A slot any copy can supply is one slot, so the Pilot de-duplicates per card id; `hand_worth` is a
supply TOTAL, where a second copy is a second card.

Issue #444 specified per-cid dedup on the leaf as part of the fix. Built that way it measures
`composer == ruled` **98/270 → 87/270**. It is rejected on the reasoning above rather than on that
number — but the number agrees, and for a legible reason: `mega_starmie` holds four Basic `{W}`
Energy, and collapsing them to one class deletes three cards' worth of hand.

## Decision 2 — the term is read on both boards, and the two sides do not move together

`latent_worth` is read on **both** boards every play is differenced across. A card leaving hand gives
up its latent worth (the CHARGE for spending it); a card arriving adds its own (the CREDIT for
fetching it). One `state_value` scores both boards, so a change to the term perturbs both sides — but
**by amounts set by what is in each hand, and those amounts are not equal.** The first draft of this
ADR claimed they were, and that was wrong:

| | root `latent_worth` at `7b507263` | with `3989f99b` |
|---|---:|---:|
| `82752045-18` — the CHARGE side | 40.5 | **31.5** |
| `85163634-17` — the CREDIT side | 0.0 | **0.0** (composer score bit-identical, `2.345638641`) |

So the discounts cut the charge and left the credit untouched. That is the whole result: **card plays
got cheaper, and the fetch stayed exactly as attractive as before.** Which is why the corpus moved the
way it did.

Cards that fill a live need never reach this term at all — `assignment_coverage` prices those — so
`latent_worth` is by construction the no-need bucket at a flat `0.45 x tier`. The only lever inside it
is uniform, and a uniform lever cannot cut a credit that is already zero.

Measured, both instruments, full corpus, deterministic:

| instrument | `7b507263` | `3989f99b` |
|---|---:|---:|
| `composer_lab`, `composer == ruled` | 98/270 | **93/270** |
| ADR-0072 Decision Gate, **unruled** `REGRESSION` (the gated metric) | 52 | **50** |
| — the same gate's TOTAL regressed rows, incl. held-out + voided | 82 | 81 |

The two instruments grade different populations — the gate replays the real Pilot ladder, where the
composer only reaches frames the sound rungs decline and then tie-defers (ADR-0131), while the lab
runs `compose()` on every frame. Neither is a result to bet on: across all regressed rows 3 frames
left and 2 entered, and **the gate is already red by 52 before the change**.

**The flips were ruled, not counted** — Issue #444's own acceptance procedure. Ten frames lost (three
off-policy), five won (two off-policy). Three of the seven on-policy losses are the composer declining
a **ruled ATTACK** to play a card instead, `82752045-115` among them, where the developer's note is
*"Attacking will win the game, so just attack."* That is the direction Decision 2 predicts: a smaller
spend charge makes card plays cheaper, and in a deck full of playable Trainers that dominates.

## Decision 3 — the build reaches NEITHER acceptance frame, which is what settles it

- `85163634-17` — **unchanged**. The fetched Staryu has `deploy 1.0`, `liquidity 1.0` and no duplicate
  in hand, so every discount the build adds is a no-op on the exact frame the issue is named for.
- `82752045-18` — **unchanged**; the composer still commits the ruled-against Hilda. (The per-CLASS
  variant of Decision 1 did move it — to a *tie*, deferring under ADR-0131 rather than playing the
  ruled attack — and that variant is rejected.)

A change that costs 5 on its own acceptance instrument while moving neither acceptance frame is not a
partial win to iterate on. ADR-0122 governs: reported and reverted, not tuned until it passes.

## Decision 4 — one real defect is recorded here rather than smuggled in

The leaf credits latent worth to cards that **cannot be played at all**. On `82522698|62` a
Buddy-Buddy Poffin with nothing left to fetch and a Cinderace with no room both read `deploy 0.0` and
together book `0.45 x (10.0 + 12.0) = 9.9` Worth. That contradicts ADR-0104's playability doctrine —
*"a card that can NEVER be played covers NOTHING"* — in the one place the composer reads.

It is **not** shipped, because Decision 2 makes it inseparable: zeroing an unplayable card's worth is
purely a charge-side cut, so it makes playing that card free, and the developer has ruled the opposite
(`85164605-64`, *"Played Ultra ball for nothing"*). Fixing it needs the action charged, not the card.
Recorded so the next reader finds the measurement instead of re-deriving the fix and re-measuring the
same loss.

## Decision 5 — the developer rules BOTH ways on searches, in comparable numbers

The guardrail against a flat penalty is not a handful of frames. Keyed on `card_effects.json` clause
kinds (`fetch` / `dig` / `draw`) rather than on card names — a name sweep misses Poké Pad, Night
Stretcher, Mega Signal and Team Rocket's Petrel, and misfiles *"played search A, should have played
search B"* — over 64 search/draw cards and the whole corpus:

| the developer ruled | frames | on-policy |
|---|---:|---:|
| **FOR** playing a search (did something else) | 55 | 55 |
| **AGAINST** playing a search (played one) | 59 | 46 |

*Positive control:* Ultra Ball (1121) is in the derived id set, and the set is non-empty at 64 cards.

**Neither a flat penalty nor a flat credit can be right at these ratios.** The discriminator the
developer actually uses is whether the fetch fills a live need *on this board*, which is a demand
read — and `latent_worth`, being the no-need bucket, is the one place that read cannot live.

## What the review caught

`/code-review`'s Spec axis, briefed that this issue was **self-filed and self-re-measured**, found
three false claims in the first draft. All three were mine, and all three came from the same habit —
**quoting a number an instrument printed without checking which population it counted**:

1. *"the Decision Gate is red by 82 unruled"* — 82 is the TOTAL regressed rows. The gated metric is
   **52**, and the delta is 52 → 50. Corrected above; the parse counted `REGRESSED` lines instead of
   reading the gate's own verdict line.
2. *"no discount shrinks the credit without equally shrinking the charge"* — falsified by the build's
   own numbers (Decision 2). The mechanism is real; the symmetry was asserted, never measured.
3. *"~26 corpus frames are ruled FOR playing a search"* — a card-NAME regex. The clause-keyed count is
   **55** (Decision 5). The review's own counter-figure of 25 was a name sweep too and is also wrong;
   what settled it was keying on the effect vocabulary and adding a positive control.

The review also disputed Decision 4's `9.9` as `15.3` over three `deploy 0.0` rows. Re-measured at
source: `82522698|62` carries **two** such rows (Poffin 10.0, Cinderace 12.0) and books 9.9. Decision
4 stands as written.

## Consequences

- **Issue #444's remaining direction is question 3, and it is a new term, not a patch.** A search that
  fills no need is not worth 0 — it thins the deck and can set up next turn — and Decision 5 puts 55
  ruled frames on that side. So the term has to read demand and charge the ACTION, and no edit to
  `latent_worth` can express that.
- `tests/strategy/test_state_value.py`'s live-board positive control is UNIVERSAL (`hand > 0.0` on
  every live board) where `hand` is a SIGNED family that can honestly net 0.0. It is **green at
  `7b507263`** and only the rejected build tripped it, so nothing is owed. Recorded as an observation
  about the control, **not** as licence to weaken it: a future change that trips it must be ruled on
  its own evidence, and this ADR pre-authorises nothing.
- **The ADR-0072 Decision Gate is red on `main`** at `7b507263` — 52 unruled `REGRESSION`s with no
  change applied. `docs/ci.md` describes a gate that fails on exactly this, so either it is not
  running or its reds are going unruled. Not this issue's to fix; recorded because it makes the gate
  weak as an acceptance instrument until someone owns it.
- **Issue #444's acceptance bar named a population it never measured** — *"no regression on the ≈26
  search-endorsing frames"*. That bar was neither well-defined (Decision 5) nor reported. A future
  acceptance bar on this class should name the clause-keyed population and report it before and after.
