# Gusting — grill-session seed: one equation for the gust target

**Status.** GRILLED and RESOLVED 2026-07-19. Round 0 measured first
(`gusting-round0-measurement.md`): the cluster dissolved to 3 small targeted failures. The grill's
three rulings (user, 2026-07-19):

1. **Scope — small build + design the full equation.** The three targeted fixes are BUILT
   (**ADR-0066**, suite-green); the full `their_keep_cost` equation is DESIGNED, not built —
   `gusting-keepcost-design.md` — and waits for corpus evidence before any construction.
2. **Denial ceiling — up to ~1 effective prize of override.** Denial credit may outweigh at most a
   ~1-prize difference (the existing γ-gated `_WINCON_DENIAL_PRIZES = 1.5` band is the ceiling's
   in-repo precedent); never more. ADR-0066 spends that allowance defensively (the threat-forfeit
   premium); the design doc owns the offensive exchange rate and the refuted-pin re-audit.
3. **Stall stays a separate small tactical + a marginality gate.** No currency conversion; the
   famine stall gained the with-vs-without swap gate (ADR-0066 §2). The spec's own "not everything
   must converge" branch, confirmed by measurement.

**Follow-up grill (same day), two more rulings:**

4. **ep86091435 f119 — refuted-by-better-line.** The ADR-0066 widened oracle's 2-prize
   drag-and-spread line supersedes the correction's 1-prize development line; recorded in
   `reviewed.json`, pinned as the ADJUDICATED case in `test_gust_round0_corpus.py`.
5. **`gust-for-the-loaded-equal-ko` ships at status `testing`** — the next /blunder-buster round
   over fresh ladder games adjudicates promotion (the house precedent; a gauntlet A/B on a
   rare-trigger rule would be underpowered).

The agenda below is kept for provenance; §1/§5/§6/§7 are answered by the rulings + ADR-0066, and
§2/§3/§4 are deferred into the design doc's evidence gates. Follows the hypergeometric-fetch-closure playbook (measure → grill → corpus-gate → converge
under the currency-zone rule). Named plainly: gusting.

## The musing (user, 2026-07-19)

> "What we did here was basically to replace the fetch and shuffle doctrines with a mathematical
> equation. Can we use this same strategy with Gusting? It would place a value on the opponent's
> benched Pokémon versus their Active. It would depend heavily on the scope read identifying the
> opponent's archetype and then understanding that archetype's weaknesses."

## The hypothesis (one sentence)

**The value of gusting up a benched target T is the opponent's keep-cost, pointed across the table** —
the SAME `card_worth` equation this repo already ships, with the inputs swapped sides:

```
gust_value(T) = P(KO T this turn) × [ prizes(T) + their_keep_cost(T) ]     ← the denial leg
              + stall(T)                                                   ← tempo to un-stick a helpless T
              − value(best line vs their current Active)                   ← opportunity cost

their_keep_cost(T) = their_role_value(T)                                   ← their role sheet (the Read)
                   × their_deadline_odds(T)                                ← their gates (visible board + rep)
                   × (1 − their_reaccess(T))                               ← their closure over their rep
                                                                             (decklist − tracker-observed)
```

`keep_cost` is player-agnostic math; only the inputs change sides. Killing their benched Drakloak
before it becomes Dragapult ex is worth exactly what THEY would compute as its keep-cost.

## Inventory — verified at source 2026-07-19 (don't re-derive; re-verify)

**Already an equation (leave alone unless a correction says otherwise):**
- The KO leg: `gust-for-the-ko` gates on the gust-KO beating any menu attack
  (`doctrine_gust._gust_best_ko_prizes`); the gamble gust Outcome Class (WP5,
  `planner._gamble_gust_ko_classes`); `_finish_turn_last`'s tier rules (KO-enabling gust → tier 0; a
  gust that forfeits an Active KO → tier 4).
- `_gust_snipe_synergy` (doctrine_gust.py:88) — real prizes, per-attack oracle-backed.

**The shadows (the convergence evidence — FIVE disjoint denial mini-currencies, each its own scale):**
| term | file:line | currency |
|---|---|---|
| `_gust_forward_denial` | doctrine_gust.py:121 | flat `_EVOLVING_GUST_DENIAL = 0.5` sub-prize tie-break for an evolving threat |
| `_gust_matchup_priority` | doctrine_gust.py:133 | MatchupPlan priority × `_MATCHUP_GUST_SCALE = 0.004` (ADR-0051 tie-break) |
| `_gust_wincon_denial` | doctrine_gust.py:146 | flat `_WINCON_DENIAL_PRIZES = 1.5` effective prizes × γ, role-scoped |
| `_gust_target_denial` | doctrine_gust.py:184 | my Active's prize value for a LIVE threat (ADR-0022) |
| `_gust_stall_target_tactical` | doctrine_gust.py:161 | `retreatCost + _STALL_EX_BONUS = 3` (ADR-0022) |

Five separately-scaled valuations of "what is this opponent body worth removing/stranding" — the same
four-shadows shape ADR-0065 collapsed for our own cards. Plus the rungs `gust-for-the-stall` and
`gust-to-strand-the-key-attacker` carrying their own flat weights.

**The precedents that make the mirror principled:**
- ADR-0062 ("energy denial is what the strip actually takes away") + ADR-0063 ("a doomed body denies
  nothing") — denial is MARGINAL, with-vs-without, never a flat bounty. Opponent keep-cost is that
  ruling applied to bodies.
- ADR-0064 — the opponent side stays budgeted by the READ; ADR-0051's MatchupPlan already carries
  γ-gated opponent ROLES (`prize_liability`, `fragile_preevo`, …) from the matchup briefs — a partial
  opponent role sheet EXISTS.
- `card_worth.role_value`/`keep_cost` + `fetch_closure` (ADR-0065) — the player-agnostic math.
- The rep build + `copies_left_odds` — their decklist minus tracker-observed plays.

## Round 0 — the measurement pass (DO THIS BEFORE THE GRILL)

The combat-tempo lesson: clusters dissolve under measurement. 29 gust-adjacent corrections exist in
`data/corrections/` (grep boss/gust/counter-catcher/heave-ho in rationale+labels):
`83053965-91, 82224509-46, 85785067-41, 85785606-19, 83667237-107, 83661652-19, 85058574-109,
85045840-10, 85045840-8, 85046350-79, 85046350-81, 85163079-30, 85786096-70, 82523164-55,
82525101-14, 82525741-58, 83456015-38, 83457493-20, 83457493-31, 81904451-15, 83966968-78,
82751468-57, 82751468-70, 82753102-109, 82754875-52` (+4 more; re-run the grep). Join
`reviewed.json` first; replay each through the real `explain()` with a FRESH pilot per replay (the
statefulness lesson); classify: already-passing (pins) / KO-leg / target-selection / stall /
whether-to-gust-at-all. **Only the legs the corrections actually flag get converged.** Expect many to
already pass — several of these ids are in the hyperclosure corpus as pins.

## The grill agenda (open questions — settle with the user, in rough order)

1. **When may denial OUTRANK a prize?** The five shadows were deliberately built as SUB-prize
   tie-breaks ("never override a real prize difference") — except `_gust_wincon_denial` (1.5 eff.
   prizes, γ-gated), which already does. A full `their_keep_cost` term (wincon tier 30 ≈ the scale of
   our own worth points, vs KO_SCORE ≈ 1000-per-prize) needs an explicit exchange rate between worth
   points and prizes, and a ruling on when plan-denial beats prize-greed. This is the core question —
   the mirror of Round 8 §6's horizon discipline (the hard rungs own the match scale).
2. **Their role sheet: derive vs declare.** Lines are derivable from their rep's `evolvesFrom` chains
   + damage ceilings (deck-agnostic, the Round 9 deriver mirrored); the matchup brief declares the
   residue (a /matchup-genie Role-Sheet output contract — the mirror of deck-genie's). Meowth-ex
   lesson doubled: a wrong GUESSED archetype poisons every target valuation → the γ-gating precedent
   (unrecognized opponent ⇒ no denial credit) must survive the convergence.
3. **Their closure coverage.** `card_effects.json` FETCH clauses were audited for OUR three decks;
   their re-access runs through THEIR tutors. Under-counting their closure OVER-values the denial
   (the kill looks permanent when they can rebuild) — an endorser inflating, the +76 shape. Ruling
   needed: extend clause coverage to the meta decks' tutors (coverage gate), or a deliberate haircut
   on `1 − their_reaccess`, or fail the denial leg toward 0 on uncovered decks.
4. **Their deadline/gates.** Their hand is hidden — `their_deadline_odds` must resolve from the
   visible board + rep only, and must fail toward "rebuildable/live" (less denial credit), never
   toward "dead" (which would inflate). Which of the gate library's gates even resolve opponent-side?
5. **The stall leg's currency.** `retreatCost + EX bonus` is its own unit today. What is a stranded
   turn worth in the one currency (relate to ADR-0064's development budget? their switch-outs from
   `copies_left_odds`?) — or does stall deliberately STAY a separate small tactical (a legitimate
   answer; not everything must converge — see the grab/pitch finding).
6. **Which shadows fold, which survive.** Snipe synergy (real prizes) and the KO leg survive as-is.
   The four flat denial terms are the fold candidates — per the currency-zone rule, a graded
   `their_keep_cost` REPLACES them and re-audits their pinned tests (`test_gust_*`, ADR-0022/0051
   fixtures), never stacks.
7. **Opportunity cost.** Already structural (gust-for-the-ko's beat-the-menu gate + the tier rules)?
   Verify nothing else is needed before adding a term.

## Hazards (paid for elsewhere — don't re-buy)

- **Endorser inflation** (+76/ADR-0060): every opponent-side unknown must reduce denial credit,
  never increase it. Fail directions: unrecognized archetype → 0; uncovered closure → assume
  rebuildable; hidden hand → assume outs live.
- **Wrong declared role is worse than none** (Meowth-ex): brief-declared opponent roles are
  corrections to the deriver, not a parallel system.
- **Currency-zone rule**: replace + re-audit the five shadows' test surface; no bolt-ons.
- **Anti-speculation**: if Round 0 shows the corrections cluster on the KO leg (already converged),
  the right outcome may be a much SMALLER build than this doc imagines — or none. The grab/pitch
  investigation (ADR-0065) is the precedent for "measured, found already-subsumed, built nothing."

## Build shape (IF the grill confirms)

Mirror of the ADR-0065 arc: corpus family from Round 0 (pins + xfail targets) → an opponent-side
worth input (their role sheet via MatchupPlan/brief + the derived residue; `card_worth` stays the one
currency — likely a thin `their_role_value` input layer, NOT a second tier table) → converge the
flat denial terms under the corpus + score-diff gate, staged → earns its own ADR (or amends
ADR-0065). deck-align/matchup-genie gain the opponent Role-Sheet contract in the same motion.
