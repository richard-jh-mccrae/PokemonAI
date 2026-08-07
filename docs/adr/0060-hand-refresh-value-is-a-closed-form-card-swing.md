# ADR-0060: Hand-refresh value is a closed-form card swing, not a hand-size threshold

**Status.** Accepted (grilled 2026-07-14, `/grill-with-docs`) and **BUILT 2026-07-14 (`/tdd`)**, default
ON — it replaces an already-live pull rather than adding a new one, so there is no dark seam to gate.
Suite 2872 green.

> **Numbering note.** 0057–0059 are reserved for the ADR-renumber sweep (the 0022/0033/0050
> collisions, `docs/archive/plans/audit-remediation.md` WP6). This ADR took the next free slot above them.

## Context

**Judge and Harlequin are not strip cards. They are symmetric REFILLS.** Verified at source
(`data/EN_Card_Data.csv`):

| card | I draw | they draw | shuffles my hand | shuffles theirs |
|---|---|---|---|---|
| Judge (1213) | 4 | 4 | ✔ | ✔ |
| Harlequin (1223) | 5 \| 3 (coin) → **EV 4** | 3 \| 5 → **EV 4** | ✔ | ✔ |
| Unfair Stamp (1080, ACE SPEC **Item**) | 5 | 2 | ✔ | ✔ |
| Lillie's Determination (1227) | 6, **8 at exactly six prizes** | — | ✔ | ✘ |
| Lacey (1199) | 4, **8 if opp ≤3 prizes** | — | ✔ | ✘ |

Both players land on the card's printed count. So the whole play is described by how many cards move
and in which direction — and **the card's own draw number is the break-even.**

The pre-ADR-0060 code did not model this. It approximated it with three hand-size constants
(`_STACKED_HAND = 6`, `_REFRESH_HAND_FLOOR = 5`, `_TAILORED_HAND = 3`), **none of which is any card's
break-even**, and the only rung that reliably fired on a refresh was `dig-before-commit` (+20), which
is completely hand-size-blind — it endorsed Judge as "a draw card" whether we held 2 cards or 10.

Six human corrections, none of them gated by a test, all on this one axis:

| correction | swing | the human |
|---|---|---|
| ml f111 Judge, my 8 / opp 1 (**CRITICAL**) | −7 | "such an enormous blunder" |
| ms f60 Harlequin, my 11 / opp 2 | −9 | "a HUGE blunder, HUGE!" |
| ms f94 Lillie's, my 10 / opp 3 | −4 | "never shuffle back hand greater than 7" |
| ms f45 Harlequin, opp 7 | +1 | "harlequin would have done well here" |
| ms f100 Harlequin, opp 9 | +4 | "a great time to disrupt" |
| ms f64 Harlequin, opp 21 | +13 | "play harlequin to reduce their handsize" |

**ms f94 was a live blunder in the shipped agent**: it scored Lillie's **+20** on a −4 board and
*played it instead of attacking*. `dont-shuffle-away-the-bigger-hand` could never reach it — Lillie's
carries no `hand_disruption` tag. And ml f111 "passed" only because two hardcoded constants (+20 dig,
−25 guard) happened to land 5 apart; the KO masked the rest.

## Decision

**One closed-form oracle owns the card class.** `strategy/refresh.py` holds the draw-count facts once;
`pilot._refresh_swing_tactical` prices the play in the `tactical` chain — the same shape as the KO
oracle (ADR-0052) and the gust oracle:

```
  CYCLE                                   the DRAW side — flat, speculative, guard-cancellable
  - SHED  * max(-my_net, 0)               cards I hold and lose        (certain)
  + STRIP * max(-opp_net, 0) + FRESH * f  cards stripped from them     (certain)
  - GIFT  * max(opp_net, 0)               cards handed to them         (certain)
```

`dig-before-commit` is gated off `shuffle_hand`; it keeps owning genuine digs (Ball search, tutors).

### The four directions are not worth the same per card — and that is load-bearing

The first cut priced them symmetrically (`K * swing`). It reached **+76** and blew through the entire
hand-QUALITY guard family — `hold-wincon-dont-shuffle` (−25), `hold-irreplaceable-tool-dont-shuffle`
(−30), `dont-refresh-into-a-probable-miss` (−25) — every one of which was calibrated against
`dig-before-commit`'s flat +20. The guards fired correctly and were simply outvoted. Two suites caught
it; without them this would have shipped as "refresh always wins".

The asymmetry is the fix, and it is not a fudge:

- A card I **shed** is one I *chose to keep*: known, curated, certainly gone. Priced per card (8).
- Cards I **draw** are *unseen*. Their worth is not a count — it is whether the deck can still supply
  a live card, which is exactly what the `hold-*` / probable-miss guards adjudicate. A spent deck
  returns dregs however many cards it returns. So the draw side is a **flat, bounded** credit (20 —
  the same +20 `dig-before-commit` used to give), and the guards can still cancel it.
- A card **stripped** from them is certain denial (4); a card **gifted** to them is as real as one of
  mine (8).

`fresh` (`opp_hand_size_delta`) counts how many of the stripped cards *arrived last turn*: stripping
live resources denies more than stripping cards they have demonstrably been unable to play. This also
settles a sign convention that `opponent_resources.py` and `pilot.py` flatly contradicted each other
on — **positive delta = they grew their hand = fresh.**

### Consequences

- **RETIRED `dont-shuffle-away-the-bigger-hand`** (−25): tag-gated to `hand_disruption`, so it could
  not see Lillie's at all, and its floor was no card's break-even.
- **NARROWED `strip-the-stacked-engine-hand`** to ONE-SIDED strips (`shuffle_hand` not in tags). Its
  `opp_draw_engine_in_play` gate is why the plain "their hand is big, Judge them" case never fired —
  the human never once mentions a draw engine. A one-sided card has no draw count for a card-fact
  oracle to price, so that branch genuinely needs a tag-driven rung. No pool card is one-sided: this
  is a live forward contract, not dead code, and it is why the rung survived rather than the branch.
- **`disrupt-the-tailored-hand` REFUTED for symmetric refills** and gated on `shuffle_hand` not in
  tags. Its premise — Iono a hand they tailored down to a few key cards — is sound for a one-sided
  strip and *inverted* for a refill: Judge into a 2-card opponent hand **hands them 4 cards**. The
  human's own CRITICAL (f111) calls exactly that "an enormous blunder". Stays weight-0.
- **`_DRAW_COUNTS` deleted.** It was a second copy of the same card text and had silently drifted —
  **missing Unfair Stamp entirely**, so `dont-refresh-into-a-probable-miss` could never fire on it.
  Both it and the planner's gamble rung now read `refresh.py`.
- **Two test fixtures were describing impossible boards.** `test_disruption_value_survives_the_
  probable_miss_veto` and `test_favored_half_never_kills_genuinely_triggered_disruption` each claimed
  to disrupt an opponent's hand-size attacker while giving the opponent **zero cards in hand**
  (`handCount` absent). Judge is a refill: playing it there hands them 4 cards and *arms the very
  attacker being disrupted* (0 cards = 0 damage; 4 cards = 80). The old scorer could not represent a
  gift, so nobody noticed. Both boards were fixed; neither assertion was.
- **The SHED leg has since been re-denominated twice, and the swing's shape survived both.**
  ADR-0065 replaced the flat `SHED × cards-lost` with `Σ keep_cost` over the actual hand; **ADR-0101**
  (2026-08-01) replaced that sum with the v2 assignment SET marginal `needs.set_keep_v2`, so a shuffled
  duplicate costs what the pair is worth rather than twice one copy. All six corrections above still
  hold under both. The STRIP / GIFT / FRESH constants below are untouched by either and remain
  authored (`firing-equation-constants`, the ratified POC whitelist) — grading them needs an opponent
  role sheet that does not exist yet; ADR-0101 §"STRIP/GIFT" records the measurement and the parking.
- **ADR-0024's anti-hoarding finding survives** — the ~3:1 mirror cost of hoarding the refresh. It
  now lives inside `_REFRESH_CYCLE` rather than in a hand-blind rung.

### Deferred

- **Harlequin's coin.** Its ±2 variance is real (heads 5/3, tails 3/5) and the branches are kept
  PAIRED in `refresh.py` for it, but it ranks at EV today — the EV term already reproduces all four
  Harlequin corrections, and the variance only moves the pick in a narrow near-neutral band. The
  gamble machinery (ADR-0039) is where it belongs.
- **Hand QUALITY.** The oracle counts cards. "8 GOOD cards" (f111) vs "8 dregs" is a hand-quality
  read this codebase does not model; the `hold-*` guards are its only proxies. That is ADR-0007's
  Base Value Model, explicitly parked.
- **Supporter-economy opportunity cost** (ADR-0023's deferred seam), now better motivated: Unfair
  Stamp is strictly **+3 swing** over Judge *and* it is an Item, so it does not spend the Supporter.

## Alternatives rejected

- **Patch the existing rungs' gates.** Keeps seven overlapping rungs that can stack, and every new
  refresh card needs another hand-fitted constant. The card already prints the number.
- **Raise the guard weights** so they still dominate a large symmetric swing. Makes
  `hold-wincon-dont-shuffle` near-absolute (it is deliberately "moderate, so a genuinely dead hand
  still refills") and re-tunes a tested family to accommodate a scaling mistake.
- **Cap the oracle's positive output** into the guards' band. Bounds it, but collapses the ranking the
  corrections demand: Harlequin (+4 swing) and Lillie's (+1) would tie again at the cap, which is the
  exact defect f100 exposes.
