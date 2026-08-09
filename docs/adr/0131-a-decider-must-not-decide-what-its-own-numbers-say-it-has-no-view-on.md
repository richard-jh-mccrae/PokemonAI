# ADR-0131 - A decider must not decide what its own numbers say it has no view on

**Status:** Accepted (Issue #386, 2026-08-07); BUILT. Amends nothing; ADDS a fourth defer to
`planner._composer_line` and a fourth fence to `pilot._finish_turn_last`'s tier gate. Both are
consequences of arming `common/composer.py` at MAIN, and both are load-bearing: without them the
swap breaks `sound_rules.information-before-commitment`, a whitelisted STRUCTURAL rule. Measured on
both ADR-0072 gates and reported here in full, including what each change cost.

## Context

POC-T4/5 arms the sequence composer as the MAIN single-pick decider and deletes the rung ladder it
replaces. The composer scores a turn by differencing end states:
`score = state_value(end board) + terminal_ev`. That is the whole thesis, and it is why the ladder
can go: a rung asserting a preference the leaf can compute is a second opinion about one board
(ADR-0092 decision 4).

**The thesis has a boundary, and `sound_rules` already named it.** ADR-0095 decision 3 ruled that
the information-before-commitment ordering — take the dig before the commitment — is

> *"NOT derivable by the planner — both orders reach the same end state, so no function of that
> state separates them."*

A composer is a function of the end state. So there exists a class of decisions the composer is
**definitionally** unable to make, it was written down a year before this issue, and the swap walked
straight into it.

It did so twice over, and the two failures are independent — either alone breaks the rule.

## Decision 1 — a free, informative, UNOPPOSED play reaches the boundary's band at score zero

`_finish_turn_last` sorts a MAIN menu into tiers, and the information-before-commitment boundary
lives *inside* its free band. Above the boundary sits an older gate:

```python
if traces[i].score <= 0:        # only an endorsed action sequences early
    return _TIER_ENDER
```

That gate is right about what it was written for — an ATTACH the decider prices at zero is the
attach-anyway blunder class (82749168-21, 82867148-34), and ADR-0069 measured and rejected loosening
it to `>= 0`.

It stopped being right when the thing it gates lost its endorsement. Measured on ADR-0095's own
anchor frame, `ms_information_before_commitment_f11`:

| | score | tier | sequenced |
|---|---|---|---|
| Pokégear 3.0 (free, INFORMATIVE) | **0.00** | `_TIER_ENDER` | last |
| Crushing Hammer (free, COMMITTING) | 22.50 | free band | **first** |

`dig-before-commit` (+20) was what carried the dig over the gate. Delete it and the dig falls out of
contention before the boundary underneath ever runs on it. **The boundary was intact the whole time;
its input had been removed** — which is the failure mode worth naming, because nothing about the
boundary's own code or tests changed and no failure pointed at it.

The fix is a carve-out with **four** fences, and the fourth is the one that matters:

| fence | why |
|---|---|
| `t == _PLAY` | a zero-priced ATTACH still falls to the last tier — the blunder class the gate exists for |
| `score == 0`, not `>= 0` | a NEGATIVE score is a decider saying the play is bad |
| not `cost_discard` | a costed dig is not free, so weak dominance does not hold |
| **nothing fired** | see below |

**A score of zero has two causes and they are opposite.** *Nothing prices this option* — the
Pokégear, once its rung was deleted, `fired` empty — and *a rung deliberately NEUTRALISED it* — Mega
Signal under `dont-tutor-the-held-wincon`, which nets a redundant tutor to exactly zero, `fired`
naming it. The old `score <= 0` gate collapsed both into "not endorsed" and was **right about the
second**. Without the fourth fence the carve-out sequenced a search the ladder had just refused
*first*; `test_benchless_agent_refreshes_over_a_redundant_wincon_tutor`, whose whole subject is a
neutralised tutor, is what caught it.

This is not the `>= 0` loosening ADR-0069 rejected. That was the whole sequencer; this is free,
informative, unopposed, and priced at nothing — the ADR-0095 case exactly.

## Decision 2 — on a tie the composer ABSTAINS; the structural sequencer decides

Repairing decision 1 was not enough, and the reason is the more general finding.

`composer.selection_key` always returns something. That is correct **within** an Option Equivalence
Class — indistinguishable options are one decision (ADR-0091), so which member wins is a tie about
nothing. It is wrong between genuinely different actions, because there a tied score is the composer
REPORTING that both end the turn in the same place, and *"they end the same"* is not the same claim
as *"take this one."*

On the anchor frame the composer prices **seven of ten options at exactly 0.0** — the ruled dig, both
Hammers, both Tools, an attach and End — and `selection_key` handed the turn to the attach. That is
ADR-0095 decision 3 happening in front of us.

So `_composer_line` gains a **fourth defer**, the same kind as its three existing ones and documented
beside them as a refusal to guess rather than a gate:

> when another menu index's best sequence ties the chosen one, the composer abstains and the tuned
> scoring keeps the turn.

Compared at `composer._SCORE_PLACES` — the **same float-noise floor** `selection_key` uses (ADR-0128),
deliberately not `EPSILON`. Reusing the admission band would quantise selection onto a corpus-fitted
number and hand every sub-epsilon decision back to the ladder, which is a different ruling nobody has
made. Sharing the floor is what stops a decision being a tie to one mechanism and not the other.

### What it costs, because a defer that fires everywhere hollows out the swap

| | frames | share |
|---|---|---|
| composer decides | 104 | **63.4%** |
| tie-defer | 43 | 26.2% |
| other defer (no `chosen` / coverage gap) | 17 | 10.4% |
| **MAIN single-pick corpus frames** | **164** | |

Unruled Decision-Gate regressions **58 → 44**. It retires **nine** xfails: four hyperclosure PINS
(`86091728-19`, `83661652-29`, `83661652-40`, `85058574-16`), three flip-table rows, the
`ko-score-band` veto gap in `test_attack_value.py`, and ADR-0095's anchor itself. On every one the
composer's own numbers tied, it stood down, and the human's ruling was played.

**One of the nine is the shape to remember.** `ml_lunar_cycle_over_inert_bench_attach_f16` was a
REFUSAL row — the seam cannot prove Lunar Cycle deterministic — and it resolved with **no widening of
the seam at all**. The refused option was never the problem. The composer committing a line it had no
view on was.

### What it does not fix, stated because the numbers are close

Two rows still disagree with the ruling and the disagreement is now the LADDER's:
`ml_ppp_attack_transient_locked_f69` and `ml_lethal_retreat_boost_to_ko_f24`. Both were failing
before the defer; it changed who owns them, not whether they pass.

And the defer deliberately does NOT catch near-ties above the floor —
`dragapult_dont_feed_draw_engine_f21` is decided by 0.0003 prizes, which is real to `_SCORE_PLACES`
and meaningless to a player. Widening the floor to a band is the different ruling above.

## Consequences

- `sound_rules.information-before-commitment` keeps its meaning, and keeps it by ABSTENTION rather
  than by a special case. That generalises: any structural rule on the whitelist is now reachable on
  exactly the frames the composer reports no view on, which is the same set ADR-0095 decision 3
  characterises.
- The composer's authority is now stated in its own units. It decides where its numbers separate
  options and nowhere else — which is a stronger claim than "the composer decides MAIN", and a
  falsifiable one: `test_composer_defers_on_a_tie.py` asserts both directions, including that the
  defer must NOT fire on a frame with a 2.43-prize margin.
- **`_finish_turn_last` is not retired by POC-T4/5** and should stop being described as if it were.
  It owns the sequencing claims no state function can express, and this ADR is why.

## Alternatives rejected

**Break the tie inside the composer, by Worth.** `selection_key` already does, and that is what
produced the wrong answer on the anchor frame. Adding a leg does not help: every leg is a function of
the end state, and the end states are equal.

**Restore `dig-before-commit`.** It would fix the anchor frame and nothing else — the composer would
still overrule the sequencer on any other tie, and the branch would carry a rung whose flat +20 is
exactly the unmeasured stand-in this issue exists to delete.

**Gate the composer behind a confidence flag.** ADR-0092 forbids it, and rightly: a composer that
decides and a ladder that decides are two spellings of one decision. The defer is not a confidence
gate — it fires on a measured tie, not on a threshold someone chose.

## Verification

- `tests/strategy/test_composer_defers_on_a_tie.py` — the premise (seven options at exactly 0.0), the
  abstention appearing in the trace, the sequencer playing the ruled dig, and the negative direction.
- `tests/strategy/test_information_before_commitment.py` — ADR-0095's falsifiable prediction,
  restored end-to-end.
- `tests/strategy/test_attack_value.py` — the `ko-score-band` veto, with three independently
  falsifiable links.
- Both ADR-0072 gates re-measured; **neither baseline re-captured**. Full record and every flip row:
  `docs/plans/issue-386-poc-t45-wave3-packet.md`.

## Amendment — terminal outcomes (Issue #460)

Terminal attack EV prices damage and riders; it is not a match-result oracle. A direct root attack
that deterministically takes the last prizes without a recoil draw constrains candidate selection
before scalar ordering, so chip or a bench rider cannot displace the game-winning attack.

The same pre-selection boundary holds a gust that takes the same terminal payoff as a direct KO of
an energized one-prize Active. It preserves the opponent's attached Energy while spending the
Supporter, so it does not outrank the direct attack. The guard is deliberately narrow: it is not a
general gust ranking. `tests/strategy/test_composer_s5_replays.py` replays both adjudicated states;
the Mega Starmie corpus moved only those two selections.
