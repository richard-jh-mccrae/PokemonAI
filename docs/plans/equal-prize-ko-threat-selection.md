# Equal-prize KO selection is threat-blind (handoff, 2026-07-22)

A grill residual surfaced walking the gust-adjacent corpus (`valuation-systems-coverage-review.md`,
the gusting grill). Anchor **ep82753102 f109** (mega_starmie, human-flagged CRITICAL). The tagged
*live* blunder — playing Boss's Orders instead of attacking — is **already fixed** (Boss's now scores
0). What remains is a **different, out-of-gust-scope** disagreement about **which attack to take when
two lines net the same prizes this turn**. Recorded here, corpus-scoped, so it is not blind-built.

## The frame — verified at source 2026-07-22

- **My Active:** Mega Starmie ex (1031), 3 {W}. Two attacks (data/EN_Card_Data.csv id 1031):
  - **Jetting Blow** {W} — 120, *plus 50 to 1 benched Pokémon*.
  - **Nebula Beam** ●●● — 210 (ignores Weakness/Resistance).
- **Opp Active:** **Alakazam (743), 140 HP, 0 energy** — *Powerful Hand* {P}: "place 2 damage
  counters on your opponent's Active for each card in your hand" = **20 damage × their hand size**, a
  scaling hand-size attacker (id 743, verified).
- **Opp bench:** Dudunsparce 140 · Genesect 110 · Dunsparce 70 · **Abra 50**.

Two KO lines, each **1 prize this turn**:

| option | line | result | prize |
|---|---|---|---|
| `[4]` 1487 **Jetting Blow** {W} | 120 → Alakazam (survives at 20); **50 snipe KOs the 50 HP Abra** | benchsitter dies, threat lives | 1 |
| `[5]` 1488 **Nebula Beam** ●●● | **210 KOs the 140 HP Alakazam** | the scaling threat is removed | 1 |

Human `correct = [5]` Nebula Beam. Equation picks `[4]` Jetting Blow.

## The gap — measured at `Pilot._attack_tactical` (src/common/pilot.py:1481–1510)

Both options resolve to `KO_SCORE + 1 prize − eff`, where `eff = _EFFICIENCY × _attack_cost` (pilot.py:1494):

- Jetting Blow: Active survives (120 < 140) → the `if bench_ko:` branch (pilot.py:1509) returns
  `KO_SCORE + 1 − eff({W}, cheap)` = **1000.9**.
- Nebula Beam: Active KO (210 ≥ 140) → `KO_SCORE + prize_value − eff` (pilot.py:1508) = `1000 + 1 −
  eff(●●●, 3-cost)` = **1000.7**.

The two 1-prize KOs tie at `KO_SCORE + 1`, so **the only separator is efficiency — the cheaper
attack wins**. Cost is **threat-blind**: it cannot see that Nebula removes a live, hand-size-scaling
Alakazam while Jetting's snipe removes a 50 HP Abra that does 10. The equation has **no term
crediting "this KO removes the bigger threat"** among equal-prize lines, so the cost tie-break breaks
it toward the wrong body.

This is the **attack-side twin** of two primitives the repo already has on other axes:
- the **gust threat-forfeit premium** (ADR-0066): when the menu KO would remove the very body dooming
  my Active, the gust must beat the menu by MORE than a prize — i.e. removing the *threat* is worth
  more than the raw prize. The same logic, unbuilt, applies to *which attack* takes the prize.
- the **Scenario-A threshold race** (turn-planner-snipe-and-gust-scenarios.md §A): choosing a target
  by threat/race math, not just prize count.

## Why this is a HANDOFF, not a fix

1. **It is a genuine strategic call, not an obvious bug.** Jetting Blow is *defensible*: 1 prize now
   AND it chips Alakazam to 20 (a trivial KO next turn) — "prize now + soften the threat." The human,
   reading posture, judges Alakazam dangerous enough (Powerful Hand scales with the opponent's
   rebuilt hand; opp hand = 0 *now* but refills) that it should not get even one attack. A
   threat-weighted term must not regress the many equal-prize frames where the cheaper/snipe line IS
   right (the `snipe-for-the-ko` corpus is at 16/19 and tangled — see §A).
2. **Single anchor.** No other corpus frame yet isolates "two equal-prize KO lines, one removes the
   live threat." Building a threat-weighted equal-prize tie-break off one frame risks the
   anti-speculation trap (board-state-valuation-grill.md). The Alakazam-threat magnitude is itself
   uncertain here (my Mega Starmie is 300 HP; Powerful Hand at opp hand-size 0 threatens nothing *this
   turn*) — the ruling hinges on how a threat read prices a *scaling, next-turn* attacker.

## Where a build would live (when corpus-supported)

- `Pilot._attack_tactical` (pilot.py:1481) — add a **sub-prize** threat-weighted tie-break among
  equal-`KO_SCORE + prize` lines: prefer the attack whose KO removes the higher-threat body. Sub-prize
  (breaks the tie, never overrides a real prize gap), mirroring the gust denial terms' discipline.
- The threat-read primitive largely exists: `board.strongest_threat_rank`, `_forward_danger`
  (doctrine_gust.py:376), and the hand-size-attacker signal `_hand_size_relief` (built inert,
  telemetry-only, in the hand-disruption grill 2026-07-19 — the Alakazam/Powerful-Hand class is
  exactly its subject). A threat-weighted KO tie-break is a natural promotion gate for it.

## Recommended next step

Capture more **equal-prize-KO-threat-selection** frames during play (two lines, same prizes, one KO
removes a scaling/live threat), then grill frame-by-frame for the exchange rate (how much sub-prize a
threat-KO earns over a cheaper equal-prize KO), then bench over the attack-select corpus. Do NOT
blind-build off this single anchor. Pair with the `_hand_size_relief` promotion gate — the Powerful
Hand class is the shared subject.
