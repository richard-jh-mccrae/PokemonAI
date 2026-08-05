# ADR-TEMP-398 - Denial is the LINE's prize, and the Structural Zero is correct rather than a defect

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (grill of Issue #398 PR (b), 2026-08-05). **Amends ADR-0117**, whose framing of
the Structural Zero as a *defect* does not survive a rules check. Supersedes ADR-0051 Phase 3b's
`_WINCON_DENIAL_PRIZES`.

## Context

ADR-0117 measured that 87.3% of the opponent-target **Flat Tie** is a **Structural Zero**:
`CombatMath.incoming` aggregates their forms with a per-turn MAX, so removing a body that is not the
unique lead yields a removal Δ of exactly 0 at any resolution. It recorded this as the defect Issue
#398 still had to fix.

**That framing is wrong, and the rules say so.** `docs/rules.md` §3: *"Attack — **1**, and it **ends
the turn**"*. The opponent attacks once per turn, with one body. So the per-turn MAX is not a
modelling shortcut to be improved on — it is what the rules permit. Consequences, none of which
could be constructed into a counter-example:

- Remove a non-leading bench body → their Active still attacks next turn for the same damage. The
  clock genuinely does not move. **0 is correct.**
- Remove the leader → the next-best promotes. Δ = lead − next_best. **Already correct.**
- Two bodies tied for the lead → removing either leaves them at full power. **0 is correct.**
- A bench pre-evolution whose forward form out-damages their Active → `incoming()` credits forward
  forms all-descendants at every `t`, so that line IS the lead and its removal **does** score.

`survival_shift` is therefore a correct, rules-derived, winner-take-all statistic. The Flat Tie is
real, but `survival_shift` is not the term that should break it.

What is actually missing is everything else a removal is worth, and it is missing in four places at
four magnitudes:

| seam | expression | band |
|---|---|---|
| `state_value._denied_forward_payoff` | `_READINESS_W × dmg/PRIZE_DAMAGE_RATE × halve(hops)` | ~0.045 prizes |
| `pilot._opponent_target_rows` | `survival_shift × phase × _SURVIVAL_PER_TURN` | ~0.5 prizes |
| `doctrine_gust._gust_wincon_denial` | `_WINCON_DENIAL_PRIZES (1.5) × γ`, role-gated | 1.5 prizes |
| `doctrine_gust._gust_forward_denial` | `_EVOLVING_GUST_DENIAL (0.5)`, damage-thresholded | 0.5 prizes |

The first two are the same quantity — the forward line's damage, denied — **11× apart**. The fourth
reads a PRINTED damage index and so misses scaling attackers entirely (Decision 5).

## Decision 1 — the Structural Zero is CORRECT; PR (b) builds beside it, never replaces it

`survival_shift` keeps its winner-take-all shape. A proposal to make non-leading bodies score
survival must first show the rules permit a second attack in a turn.

ADR-0117's Correction section stands as a *measurement* (the numbers are right and were reproduced);
its characterisation of the residue as a defect to be fixed is **withdrawn** by this ADR.

## Decision 2 — denial is the LINE's prize, expressed INSIDE `prize_advance`

```
prize_advance = own_prize + (max_line_prize − own_prize) × halve(hops)
```

Reusing `grading.halve` (ADR-0070 §6's shipped `p_arrive` convention) and `TheirSide.forward_payoff`'s
existing hop walk. A Staryu one hop from a 3-prize Mega Starmie ex reads 2, not 1.

**Bounded by `MAX_PRIZE_VALUE` = 3 by construction**, so `needs.TARGET_VALUE_CEILING` stays 3.9 and
nothing downstream rescales. That is load-bearing in three places, not one — `state_value._THREAT_W
= _THREAT_CAP / TARGET_VALUE_CEILING`, `currency.GUST_TARGET_WORTH_RATE = GUST_TARGET_BAND /
TARGET_VALUE_CEILING`, and `currency.target_value_to_worth`'s clamp — each with its own
`sound_rules` whitelist entry. An ADDITIVE denial leg would have moved all three before the new term
did anything, entangling the rescale with the effect on the Decision Gate.

**The reading must reach ALL THREE consumers, and one of them does not read `prize_advance` at
all.** Found at build time: `doctrine_gust._gust_target_tactical` — the only caller of
`_gust_wincon_denial` — scores `KO_SCORE + self._prize_value(target) + …`, the body's OWN prize.
Deleting `_gust_wincon_denial` on the grounds that "the premium is now inside `prize_advance`" would
therefore have been false for that call site and would have silently dropped the wincon premium from
the gust doctrine path. `_gust_target_tactical`'s `_prize_value(target)` is replaced by the same
line-prize reading, which is what makes the justification true rather than merely plausible.

**Hops are hops to the best-PRIZE form, not to the best-DAMAGE form.** `ForwardPayoff.hops` answers
the latter (Issue #285) and the two diverge on any line whose biggest attacker is not its biggest
prize. The depth walk `CombatMath._forward_hop_depths` is the ONE home for *"how far is that form"*
and already serves two aggregations; this is a third, taken from the same walk rather than
re-derived beside it.

`_WINCON_DENIAL_PRIZES = 1.5 × γ` is **DELETED**, not relocated. Three things improve:

- an authored constant becomes a derivation;
- the γ-gate goes, so the reading fires on an unrecognised opponent — the silent-failure mode
  ADR-0117 recorded as fatal to the roles-supply-the-magnitude alternative;
- the role-gate goes, so any line with a bigger forward form is priced, not only the two curated
  wincon roles.

**Not a double-count against `prize_race`.** KOing that Staryu moves `prize_race` by 1 while
`prize_advance` read 2; the extra 1 is the Mega Starmie that never arrives, which `prize_race` never
counts. Recorded as an explicit `sound_rules` disjointness entry rather than left to look obvious.

## Decision 3 — one damage-denial quantity, two idioms, because the consumers differ structurally

The 11× gap is two correct answers to two different questions, not two opinions about one:

- **`state_value` differences.** Its one live consumer is `planner.py`'s leaf evaluator
  (`board_value = KO_SCORE × state_value(leaf_state_model(end))`), which scores end-of-turn boards.
  Remove their body and `survival` recomputes; the clock improvement arrives for free.
- **`pilot._opponent_target_rows` does not.** Its consumers are a one-shot ranking with no "after"
  to difference against — chiefly `gust_target_slot`, which prices *holding* a gust card in the
  Worth DP. That is the value of a play NOT made this turn, on a board that does not exist yet;
  `apply_option` has no after-state to produce. It is permanently outside the differencing
  mechanism, not transitionally so.

Therefore:

- `survival_shift` stays the RANKING's explicit damage-denial leg.
- `threat` keeps `survival_shift=0`, and this **stops being a fail-closed gap**: passing a real
  delta here would double-count against `survival` under differencing. `threat.blind_to`'s entry
  naming a T1-owed removal-delta accessor (Issue #260) is **retired as NOT OWED** rather than left
  standing as debt.
- `state_value._denied_forward_payoff` is **DELETED**. Its damage leg is what `incoming()` already
  composes into the clock, and its prize leg is Decision 2's.

A `sound_rules` entry records the differencing/ranking split, so a later reader does not "fix" the
asymmetry back into existence.

## Decision 4 — reachability stays with the consumer; this ADR does not touch it

Already ruled by ADR-0076 and restated at `_opponent_target_rows`: *"instrument-specifics (chip vs
KO, reachability) are each consumer's own job, not priced here."* The two live gates ask genuinely
different questions and both are correct:

| consumer | question | bench route |
|---|---|---|
| `state_value._reachable_target_values` | can I KO it WHERE IT SITS? | `best_reachable_bench_damage` (snipe/rider) |
| `doctrine_gust._gust_can_ko` | can I KO it AFTER dragging it Active? | `predicted_damage` vs the body |

A bench body unreachable by snipe is reachable once gusted. Denial value is seat-independent and
instrument-independent, so it belongs in the shared equation; reachability is neither, so it does
not.

## Decision 5 — the evolving-threat denial reads the BOARD-PRICED forward oracle, as a magnitude

`doctrine_gust._gust_forward_denial` thresholds `stats.forward_max_damage(cid) >= 100`
(`_EVOLVING_THREAT_DMG`) and returns a flat `_EVOLVING_GUST_DENIAL = 0.5`. Both the instrument and
the shape are wrong:

- **The instrument is printed-only.** `forward_max_damage` is a card-facts roll-up over the line —
  no board, no energy, no weakness, no scaling term. `CombatMath.forward_threat_ceiling`'s own
  docstring names the victim: *"the printed forward index reads **Alakazam at 10** because its whole
  threat lives in a scaling term."* So the shipped term returns **0** for one of the set's scariest
  evolving lines. This is ADR-0109's defect class — the same printed-`maxDamage` read it removed
  from `readiness` in favour of the board-priced `attack_payoff`.
- **The shape is a threshold**, so a line at 99 and a line at 400 are 0 and 0.5.

Replaced by `CombatMath.forward_threat_ceiling(cid, context=…)`, board-priced, crossing to prizes on
`currency.PRIZE_DAMAGE_RATE`, hop-discounted by the same `grading.halve` Decision 2 uses, and capped
at `needs._SURVIVAL_CAP` so the sub-prize tie-break discipline the old constant enforced is
preserved by an existing bound rather than a new one.

**AMENDED at build time (2026-08-05): this migration rides `scaled_threat_rank`, and the two
constants are RETIRED FROM THE LIVE PATH rather than deleted.** Step 0 found that Issue #213 already
performed this exact migration — printed `forward_max_damage` → board-priced
`forward_threat_ceiling` — at `Pilot._threat_damage_pair`, naming the same casualty (*"Alakazam
ranks at its forward index's 10"*), behind the `scaled_threat_rank` flag whose OFF branch promises
*"restoring the printed-only read exactly"* as an incident lever. `_gust_forward_denial` is the same
fact at a call site that migration left behind, so it belongs on the same lever: one fact, one
switch. Deleting the constants would leave OFF unable to restore this call site, making the lever
partial — and a lever that lies is worse than no lever. `_EVOLVING_GUST_DENIAL` and
`_EVOLVING_THREAT_DMG` therefore survive as the OFF branch only, live-path dead. Net authored
constants removed by this ADR: **two** (`_WINCON_DENIAL_PRIZES` deleted, `_denied_forward_payoff`
retired), not the four an earlier draft claimed.

**This is NOT the drift Decision 3 closed.** `survival_shift` answers *"does removing this move my
clock"* and is lead-only by the rules, so it structurally cannot see a line that is dangerous but
not currently leading. Decision 2's prize reading cannot see it either when the forward form is not
higher-prize (a 1-prize Basic evolving into a 1-prize Stage 1 that hits hard). Three readings, three
genuinely different questions — recorded so the next reader does not collapse them.

The doctrine layer must thread the THEIRS-direction Damage Formula context, exactly as Issue #343
threaded it into `_opponent_target_rows`; an unthreaded `context` prices a scaling attack at 0,
which is the very failure this decision exists to fix.

## Decisions taken without a question (stated, not asked)

- **This ADR amends ADR-0117 rather than editing it.** ADR-0117 shipped in PR #401 and is now an
  immutable record; a superseded framing is corrected by a successor, not rewritten in place.
- **`_gust_matchup_priority` and `_gust_target_denial` are untouched.** Neither is forward denial —
  the first is γ-gated role ORDERING (Issue #395 / PR (c)'s subject), the second is defensive
  URGENCY (*"this body would KO my Active"*). Out of PR (b)'s scope.
- **The evolving-threat leg's cap reuses `_SURVIVAL_CAP`** rather than introducing a band of its
  own. Deriving beats authoring, and this family already has exactly one "sub-prize tie-break
  ceiling" constant.
- **A sham-controlled probe is owed** for any argmax-movement claim PR (b) makes (ADR-0118), and the
  tie population must be reported on `value`, not on `survival_shift` — the sub-population error
  ADR-0117's own instrument made.

## Policy

- **A winner-take-all statistic is not automatically a defect.** Check the rule it models before
  proposing a richer aggregation — ADR-0117 spent a build on the opposite assumption.
- **Prefer expressing a bounded quantity inside an existing field over adding a term beside it**,
  when the bound is a real property of the domain. It keeps derived normalisation constants still.
- **Two consumers may spell one quantity differently when one differences and one does not.** Say
  so at both sites; do not converge them for symmetry.

## Verification

- The rules claim (1 attack per turn) is `docs/rules.md` §3, sourced from `rulebook.txt` L150.
- `TARGET_VALUE_CEILING` unchanged is assertable directly, and `test_currency.py` already guards the
  two derived rates.
- Decision Gate runs on PR (b) alone (Issue #398's three-PR sequence), against PR (a)'s post-merge
  control at `acf830c` — Decision Gate PASS, `agree 251/340`, 0 picks moved.
- A sham-controlled probe is owed under ADR-0118 for any argmax-movement claim this PR makes.
