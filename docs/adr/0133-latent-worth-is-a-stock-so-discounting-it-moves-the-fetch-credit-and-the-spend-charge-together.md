# ADR-0133 - `latent_worth` is a STOCK, so discounting it moves the fetch credit and the spend charge together

**Status:** **Rejected as specified** (Issue #444, built and measured 2026-08-09; build preserved at
`3989f99b`, reverted at `97cd2569`). Nothing ships. **Amends nothing.** Issue #444 returns to
`status:1-grilling` with its W1 direction refuted and question 3 — *does a search owe a charge at
all* — promoted from an open question to the only remaining one.

This is ADR-0122's shape: a change justified by what it measured rather than by what it shipped. It
differs in one way that matters — ADR-0122 salvaged one narrow fix from the same measurement, and
this one salvages none, because the measurement says the defect cannot be reached from where the
issue pointed.

## Context

Issue #444's premise was verified at `HEAD` before any code, by the `/implement` step-0 protocol, and
it reproduced exactly:

| the issue claims | measured on `7b507263` |
|---|---|
| `latent_worth` has three sites and no demand counterpart | `needs.py:320` (field), `state_value.py:829` (reader), `planning/leaf.py:137` (producer) |
| *positive control* | the same grep for `slot_demand` returns 7 sites incl. a live registry `reads=(...)` entry, so the instrument finds a wired demand leg where one exists |
| a no-slot card is credited `+0.075` prizes | `_GENERAL_WORTH_W 0.45 x ROLE_TIER 20.0 x POC_WORTH_PRIZE_RATE 1/120` |
| the leaf's copy skips the Pilot's discounts | leaf: `_GENERAL_WORTH_W * role_value`; Pilot: `worth * deploy * _GENERAL_WORTH_W * liq` |

So the asymmetry the issue names is real, and `85163634-17` fetches a **Staryu** whose eligibility is
`set()` — it fills nothing and books 9.0 Worth. The issue's **answer** — make the leaf's latent worth
match the Pilot's — is what does not survive.

## Decision 1 — the two aggregations of the formula are different quantities, and only one is the slot view

The build extracted `NeedsMixin._latent_row_worth` as the one formula and aggregated it twice:
`_general_worth_classes` per CLASS for the Pilot's `general` slot, `_latent_holdings` per ROW for the
leaf's `hand_worth`. **The split is load-bearing and is the one thing here worth keeping in mind.**
A slot any copy can supply is one slot, so the Pilot de-duplicates per card id; `hand_worth` is a
supply TOTAL, where a second copy is a second card.

Issue #444 specified per-cid dedup on the leaf as part of the fix. Built that way it measures
`composer == ruled` **98/270 → 87/270**. It is rejected on the reasoning above rather than on that
number — but the number agrees, and it agrees for a legible reason: `mega_starmie` holds four Basic
`{W}` Energy, and collapsing them to one class deletes three cards' worth of hand.

## Decision 2 — a stock cannot be discounted on one side

`latent_worth` appears on **both** sides of every card play. Playing a card removes it from hand, so
its latent worth is the CHARGE for spending it; a search that lands a card adds latent worth, so the
same number is the CREDIT for acquiring it. The composer scores by differencing two boards through
one `state_value`, so there is no discount that shrinks the credit without equally shrinking the
charge.

Cards that fill a live need never reach this term at all — `assignment_coverage` prices those. So
`latent_worth` is *by construction* the no-need bucket at a flat `0.45 x tier`, and the only lever
inside it is uniform.

Measured, both instruments, full corpus, deterministic:

| instrument | `7b507263` | `3989f99b` |
|---|---:|---:|
| `composer_lab`, `composer == ruled` | 98/270 | **93/270** |
| ADR-0072 Decision Gate, unruled `REGRESSION` | 82 | **81** |

The two disagree because they grade different populations — the gate replays the real Pilot ladder,
where the composer only reaches frames the sound rungs decline and then tie-defers (ADR-0131), while
the lab runs `compose()` on every frame. Neither is a result to bet on: the gate moves 3 fixed
against 2 broken, and it is already red by 82 before the change.

**The flips were ruled, not counted** — Issue #444's own acceptance procedure. Ten frames lost
(three off-policy), five won (two off-policy). Three of the seven on-policy losses are the composer
declining a **ruled ATTACK** to play a card instead, `82752045-115` among them, where the developer's
note is *"Attacking will win the game, so just attack."* That is the direction Decision 2 predicts: a
smaller spend charge makes card plays cheaper, and in a deck full of playable Trainers that dominates
the smaller fetch credit.

## Decision 3 — the build reaches NEITHER acceptance frame, which is what settles it

- `85163634-17` — **unchanged**. The fetched Staryu has `deploy 1.0`, `liquidity 1.0` and no
  duplicate in hand, so every discount the build adds is a no-op on the exact frame the issue is
  named for.
- `82752045-18` — **unchanged**; the composer still commits the ruled-against Hilda. (The per-CLASS
  variant of Decision 1 did move it — to a *tie*, deferring under ADR-0131 rather than playing the
  ruled attack — and that variant is rejected.)

A change that costs 5 on its own acceptance instrument while moving neither acceptance frame is not a
partial win to iterate on. ADR-0122 governs: reported and reverted, not tuned until it passes.

## Decision 4 — one real defect is recorded here rather than smuggled in

The leaf credits latent worth to cards that **cannot be played at all**. On `82522698|62` a
Buddy-Buddy Poffin with nothing left to fetch and a Cinderace with no room both read `deploy 0.0` and
together booked `+9.9` Worth. That contradicts ADR-0104's playability doctrine — *"a card that can
NEVER be played covers NOTHING"* — in the one place the composer reads.

It is **not** shipped, because Decision 2 makes it inseparable: zeroing an unplayable card's worth
also makes playing it free, and the developer has ruled the opposite (`85164605-64`, *"Played Ultra
ball for nothing"*). Fixing it needs the action charged, not the card. It is recorded here so the
next reader finds the measurement instead of re-deriving the fix and re-measuring the same loss.

## Consequences

- **Issue #444's remaining direction is question 3, and it is a new term, not a patch.** A search that
  fills no need is not worth 0 — it thins the deck and can set up next turn — and ~26 corpus frames
  are ruled *for* playing a search. So the term has to read demand and charge the ACTION, and no edit
  to `latent_worth` can express that.
- `tests/strategy/test_state_value.py`'s live-board positive control was found to be UNIVERSAL where
  it should be existential — `hand` is a signed family and a fully-covered hand nets exactly 0.0
  honestly. The build corrected it; the revert takes the correction back out with the rest. If a
  later change trips it, that is the bug, not the change.
- **The ADR-0072 Decision Gate is red on `main`** at `7b507263` — 82 unruled `REGRESSION`s with no
  change applied. `docs/ci.md` describes a gate that fails on exactly this, so either it is not
  running or its reds have been going unruled. Not this issue's to fix; recorded because it makes the
  gate useless as an acceptance instrument until someone owns it.
