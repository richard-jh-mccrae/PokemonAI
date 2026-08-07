# Gusting keep-cost — the full-equation DESIGN (design-only, not built)

**Status.** DESIGNED 2026-07-19 under the grill rulings recorded in `ADR-0066`
(scope: "small build + design the full equation"; denial ceiling: "up to ~1 effective prize of
override"; stall: separate tactical, settled). **Nothing here is built.** ADR-0066 shipped the
three measured fixes; every leg below carries an EVIDENCE GATE — a description of the correction
shape that would justify building it. No gate trips, no build (the grab/pitch precedent).

## The equation (the seed doc's hypothesis, priced under the rulings)

```
gust_value(T) = P(KO T this turn) × [ prizes(T) + min(1, their_keep_cost(T)) ]   ← ceiling ruling
              + stall(T)                       ← SETTLED: stays the separate small tactical (ADR-0066 §2)
              − value(best menu line)          ← SETTLED: menu_attack_total_prizes + the threat-forfeit
                                                 premium (ADR-0066 §1) — structural, no term needed

their_keep_cost(T) = their_role_value(T)       ← derive-first role sheet (§2)
                   × their_deadline_odds(T)    ← visible board + rep only, fails toward "live" (§4)
                   × (1 − their_reaccess(T))   ← their closure over their rep, haircut (§3)
```

**The exchange rate (denial ceiling ruling).** `their_keep_cost` is expressed DIRECTLY in effective
prizes and clamped to ≤ ~1 (the offensive band; `_WINCON_DENIAL_PRIZES = 1.5 × γ` is today's
role-scoped exception and the absolute ceiling — the design REPLACES it, so the clamp unifies at
1.5 pre-γ, ≤ ~1 in practice after the multiplicative discounts). There is NO worth-points↔prizes
conversion: opponent-side value never re-enters `card_worth`'s unit; the two currencies meet only
at the prize scale. Consequence: denial can flip a ≤1-prize gap, never a 2-prize one — KO_SCORE
arithmetic stays untouched.

> **Scope qualifier added 2026-08-02 (ADR-0107, Issue #313 item 2g).** The "NO worth-points↔prizes
> conversion" sentence governs THIS equation — the **play-side** `gust_value(T)` above, where
> `their_keep_cost` is already in effective prizes and our own value is prize-denominated, so the two
> genuinely do meet at the prize scale. It is **not** a rule about the **keep-side** `gust_target`
> slot, which prices OUR held card inside `needs`' worth-summing assignment. That slot does now cross,
> at `currency.target_value_to_worth` — and it crosses as a `[0, 1]` FRACTION of `TAG_TIER["gust"]`,
> so no prize-denominated magnitude lands in `card_worth`'s unit either; the prize scale is divided
> out first, the way ADR-0086 amendment B's deploy ratios divide out the worth scale. Recorded here
> because the two files otherwise contradict each other on their face, which is a worse failure than
> either position.

**What ADR-0066 already banked, and how it folds in (currency-zone rule — replace, never stack):**

| shipped term | fate under the full equation |
|---|---|
| `gust_ko_energy_swing` / `_gust_energy_denial` | becomes the sunk-Energy input of `their_role_value` (ADR-0062 marginal strip) — folded, tests re-audited |
| threat-forfeit premium | the defensive half of the same ≤1-prize band; stays structural in the gate |
| `_gust_forward_denial` (0.5) / `_gust_matchup_priority` (0.004×) / `_gust_wincon_denial` (1.5γ) | the three remaining shadows — REPLACED by the graded `their_keep_cost`, their pinned tests (`test_gust_*`, ADR-0022/0051 fixtures) re-audited in the same motion |
| stall legs (`retreatCost + _STALL_EX_BONUS`, swap gate) | stay OUT of the equation permanently (ruling 3) |

## §2 Their role sheet — derive first, declare as correction

Derived (deck-agnostic, from their REP = decklist − tracker-observed): `evolvesFrom` chains +
damage ceilings → attacker/wincon lines; engine tags (draw/accel abilities) → engine bodies; sunk
Energy → investment. The Brief's γ-gated roles (`prize_liability`, `fragile_preevo`, ADR-0051)
CORRECT the deriver where they disagree (Meowth-ex lesson: a wrong declared role is worse than
none), they are not a parallel system. Unrecognized opponent (γ→0, no rep confidence) ⇒ derived
residue only, discounted; fully unknown ⇒ keep-cost 0 (prize-greed is the fail direction —
ep86091435 f119's adjudication decides whether a derived engine-tag (Relicanth) may claim the
≤1-prize band WITHOUT a Brief; until then, no).

**Evidence gate:** a correction where the right gust turns on a role the deriver cannot see AND the
Brief does not declare — none exist today.

## §3 Their re-access — haircut, not coverage

`card_effects.json` FETCH-clause coverage was audited for OUR three decks only; their tutors run
through the same clauses unaudited. Under-counting their closure OVER-values denial (the kill looks
permanent while they rebuild — the +76 endorser-inflation shape). Ruling for the design: a flat
HAIRCUT — `their_reaccess ≥ 0.5` whenever their deck's clause coverage is unaudited (i.e. denial
credit is at most halved, never full) — with per-deck coverage extension only for decks the meta
tracker exports as recurring opponents. Fail direction: uncovered ⇒ assume rebuildable.

**Evidence gate:** a correction where a gust-KO was right/wrong BECAUSE the line was/wasn't
rebuildable — none exist today.

## §4 Their deadline — visible board + rep only, fails live

Their hand is hidden: `their_deadline_odds` may read only the visible board (bodies, attachments,
`copies_left_odds` over the rep) and must fail toward "live/rebuildable" (LESS denial credit),
never toward "dead". Gate-library gates that resolve opponent-side today: body-on-board,
energy-attached, copies-remaining. Everything hand-dependent resolves to 1.0 (live).

**Evidence gate:** a correction turning on their line being provably dead — none exist today.

## §5 Pin re-audit obligations (whoever builds this)

- The three refuted KO-leg pins (82224509-46, 82525741-58, 83966968-78) must SURVIVE: keep-cost on
  a bare pre-evo ≈ 0, so no equal-tie flip without sunk investment (the f46 swing guard
  generalises: `their_keep_cost(bare Riolu) < the Supporter's cost`).
- `test_gust_round0_corpus.py` + REQ-GUST-0015 unit tests are the floor; the folded shadows'
  fixtures get re-pointed at the one term, not deleted.
- ep82753102 f109 (threat-forfeit) must keep standing down: the offensive band never outbids the
  defensive premium on the same board.
- /matchup-genie's Role-Sheet output contract (the deck-genie mirror) lands in the same motion as
  §2 — a Brief without roles is a deriver-only opponent, not an error.

## Anti-speculation (the standing verdict)

Round 0 measured 29 corrections and found the full equation unsupported; ADR-0066's three fixes
covered everything real. This design exists so ruling 1's second half is honored — ready, priced,
gated — and so no future session re-derives it from the seed. Build a leg when its evidence gate
trips in a future blunder round; fold, re-audit, and retire this doc into the ADR that does it.
