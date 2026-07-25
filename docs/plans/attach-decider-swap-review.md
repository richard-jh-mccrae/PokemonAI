# Attach decider swap — the batched corpus review (#139, ADR-0069 §8)

The swap protocol rules that **no decision may flip silently**: the new decider is built behind the
flag, the corpus is swept flag-ON vs flag-OFF **while both deciders still exist**, and every flip is
put in front of the user in ONE sitting with its axes breakdown before the deletion commit lands.
This is that table.

**Instrument.** `tools/train/probes/attach_decider_sweep.py`, run at the shipped constants against a
tree that still carries the rungs (NEW = the decider with the 19 retired rungs forced to weight 0 —
exactly the post-deletion agent; OLD = `attach_value` OFF with the pile at its shipped weights).
Comparison is by resolved target SLOT `(area, position)`, never the raw option index. After the
deletion commit the probe's OLD arm is degraded mode rather than the pile, so this table is the
record.

## Tally

| | frames | agree | flip | FIX | REGRESSION | DIVERGENT | unlabelled |
|---|---|---|---|---|---|---|---|
| corpus | 133 | **126** | 7 | 3 | 1 | 2 | 1 |

`FIX` = the new decider matches the human `correct` where the pile did not. `REGRESSION` = the
reverse. `DIVERGENT` = neither matches. `unlabelled` = the frame carries no `correct`.

## The seven flips

| frame | agent | NEW | OLD | correct | verdict | why |
|---|---|---|---|---|---|---|
| 82523811-59 | mega_starmie | ACTIVE 0 | bench 0 | ACTIVE 0 | **FIX** | Build the survivable 400-HP ACTIVE carrier (opp Hariyama 150 / Riolu 180 need Nebula 210) instead of starting a fresh bench Mega. Convexity + the survival gate, arithmetic. |
| 83664340-45 | mega_starmie | ACTIVE 0 | bench 0 | ACTIVE 0 | **FIX** | Arm the doomed Active with the attack it unlocks TONIGHT (Jetting Blow 120 > a ~23 bench build step). The rung layer lost this because its arm exemption was biggest-attack-only. |
| 86088989-63 | mega_lucario | bench 2 | bench 3 | bench 2 | **FIX** | Over-attach: no 3rd Energy on a 2-cost Lucario. The typed slot-fraction reads the maxed body as zero. |
| 85046350-21 | dragapult_ex | ACTIVE 0 | bench 0 | bench 0 | **REGRESSION** | Ruling 1 below. |
| 85058574-121 | mega_lucario | bench 1 | bench 2 | bench 3 | DIVERGENT | **Pre-ruled out of scope.** ADR-0069 §6 names this as the sole frame that wanted prize math; Ruling 4 keeps it out and the corpus protocol re-tags it as **#145 evidence**. No local term is at fault. |
| 86089617-4 | mega_lucario | ACTIVE 0 | (no attach) | (no attach) | DIVERGENT | Ruling 2 below. |
| 86090164-78 | dragapult_ex | bench 5 | ACTIVE 0 | — | unlabelled | Both attach; the frame carries no label. The decider prefers the bench Line body's build to the Active's. No action. |

### Ruling 1 — 85046350-21 (dragapult, turn 2): typed build re-reads the frame

Hand holds one `{D}`. Phantom Dive costs `{R}{P}`; Dreepy's own attacks are `{P}` and `{R}{P}`. Under
**typed** slot-fraction build a `{D}` fills NO slot on any Dreepy, so every bench attach scores a
genuine **zero** — which is the point of user stories 4/6 (off-type waste as an emergent zero). The
human label (`bench 0`, "concentrate on the started Dreepy") predates typed build and was really a
ruling about *not* powering the Dunsparce draw engine — which the decider satisfies outright (the
role gate zeroes the engine's attack axis). With every bench option at zero, the decider banks the
only value left on the board: Retreat Equity on the Active.

**Question:** is "put the dead `{D}` where it at least buys a pivot" right, or should the decider
decline to attach when no option buys attack progress? Declining means an explicit worthless-attach
floor, which ADR-0069 rejected once already (an unconditional attach-anyway is a measured blunder
class); the mobility channel is the priced alternative. If you want the label kept, the honest move
is to re-label the frame to `(4,0)` rather than change code.

### Ruling 2 — 86089617-4 (mega_lucario): the desperation floor firing where the human declined

The only priced option is a `{F}` onto the doomed Active; every axis is zero except Retreat Equity
(3.0), so the attach clears End. The human's label is "no attach".

This is what user story 8 asks for (a mobility attach is a *priced* play), pointed at a case where
the human disagreed. Note the mobility is real even on a doomed body — a doomed Active retreating
THIS turn is precisely the pivot the Energy pays for.

**Question:** accept, or should Retreat Equity require the retreat to be *legal on this menu*, the
way the new arm stand-down does? The second is a small, well-scoped change (the same menu read) and
I can make it if you want the floor tightened.

### Ruling 3 — the Munkidori fuel doctrine (no corpus flip; two follow-up pins)

`tests/strategy/test_counter_mover_attach.py` carries the 2026-07-19 user doctrine: *once the benched
line is fed*, the `{D}` fuel — and then the `{P}` — should go to a stuck Active Munkidori. Two of its
three pins are now EMERGENT and pass with no rung at all: the line eats first (the board-evaluated
role gate zeroes a `counter_mover`'s attack axis while a Line member is in play), and the `{D}` wins
the turn once the line is fed (a second `{P}` fills no remaining slot of Phantom Dive's `{R}{P}`, so
the line credits zero and the additive channels carry it). The THIRD — the stuck-Active `{P}` arm-up
— does not reproduce, because ADR-0069 §4 states the gate on "an attacker alternative is **IN
PLAY**", not on "still needs Energy", and one `xfail` records it.

I measured the per-colour alternative (gate stands down when no attacker can use THIS colour): it
makes both doctrine pins pass and **inverts the committed 86091728-19 correction**, where the human
ruled the line eats the `{P}` first even though the `{D}` beside it is dead to the line. So the
committed correction wins and the doctrine pins are marked, not the reverse.

**Question:** keep the ADR-literal gate (recommended — the correction outranks the follow-up pins,
and the doctrine's real content is a resource-sequencing claim about *which Energy to spend this
turn*, which no gate expresses), or re-rule the gate per-colour and re-label 86091728-19?

### Ruling 4 — target choice among live attackers (fixture frames, not in the sweep)

Three committed FIXTURE corrections keep their content but not their exact target, and their pins now
assert the content:

- `ml_aurajab_dont_load_the_engine_f121` — the engine (Lunatone) is excluded structurally ✓; the load
  goes to a Solrock whose Cosmic Beam one `{F}` completes rather than the second Mega Lucario ex the
  human tagged. Cause: the decider prices ONE routed unit at a time, so it cannot see that the Mega
  absorbs three while the Solrock's next two are worthless. Multi-unit routing is out of Phase 1a.
- `dragapult_dont_feed_draw_engine_f21` — the draw engine is excluded ✓; same `{D}`-fills-no-slot
  situation as Ruling 1.
- `dp_charge_the_line_f29` — the evolve still WINS the turn ✓, but now by ORDERING (free development
  is tier 0, the irreversible attach tier 2) rather than by out-scoring it. With the marginal a real
  damage currency, a 37.5-damage build step out-numbers a +20 evolve rung; the sequencer is what
  keeps the evolve first, which is the more honest mechanism for it anyway.

## What the review changed before the deletion commit

Five findings were fixed in code rather than ruled, because each was the decider being wrong rather
than the human:

1. **The Active-preference prior overrode real build steps.** At the shadow-era `+8`, sized against a
   flat `+15` rung floor, the prior was worth a whole 8-damage build step against a continuous
   marginal. Re-derived to `+1` under a test-asserted band (below one scaled build step).
2. **A doomed Active was armed in front of an available pivot** (83007714-65 — the charter frame of
   the deleted `dont-feed-the-doomed`). The survival gate gained its THIS-TURN half: tonight's credit
   stands down on a doomed Active when a ready benched win-condition exists **and the engine is
   actually offering the retreat**. The menu read is load-bearing — at 82525101-69 the bench Mega is
   "ready" but cannot pay its 2-cost retreat, and arming the doomed Active for 120 IS the play.
3. **A `discard_eot` burst was earning durable BUILD credit.** Ignition's honest 3 units read as a
   full Nebula Beam build and beat the reusable Basic even where its attack could not KO — the
   83116501-70 blunder the no-KO cap exists to prevent, which the cap alone could not reach because it
   caps `this_turn` while the build axis quietly out-bid it. A burst now earns `this_turn` only.
4. **An ATTACH_FROM recipient's board AREA was hardcoded to the Bench**, so the survival gate could
   not see a doomed ACTIVE recipient and accelerated Energy sank into a body dying with it.
5. **The role gate mis-read a secondary attacker's Line base.** `evolution_base` (Makuhita on the
   Makuhita → Hariyama prize-wall line) is a Role that names a Line stage rather than an attack, so
   the declared-role test gated it. The gate now reads ADR-0048's broadened line set.

The scale itself was retuned constraint-first: the written inequalities gave a feasible region, and
corpus agreement is flat over `[1.0, 1.5]` and 3 regressions worse at the shadow-era 0.3 (a real
early build step then scores below a +8 Tool equip). 1.0 is the region's lower edge and makes the
marginal a direct damage currency.

## The paired A/B gauntlet — RUN (merge evidence, directive 6)

`tools/sim/gauntlet_swap_ab.py`. A flag A/B would have been the wrong instrument: with the 19 rungs
deleted, `attach_value` OFF is degraded mode, not the incumbent, so an on/off delta measures the
decider against nothing. This A/Bs two BUILDS — candidate (`463a508`) against the pre-swap commit
(`2ba1035`) staged as self-contained bundles, opponent held FIXED at the incumbent so the raw deck
matchup subtracts out. Six directed matchups, both arms seat-balanced (ADR-0021), n=200 per arm.

| matchup | candidate | incumbent | delta |
|---|---|---|---|
| dragapult_ex vs mega_lucario | 72/200 = .360 | 65/200 = .325 | **+3.5 pp** |
| dragapult_ex vs mega_starmie | 22/200 = .110 | 17/200 = .085 | **+2.5 pp** |
| mega_lucario vs dragapult_ex | 145/200 = .725 | 129/200 = .645 | **+8.0 pp** |
| mega_lucario vs mega_starmie | 69/200 = .345 | 58/200 = .290 | **+5.5 pp** |
| mega_starmie vs dragapult_ex | 172/200 = .860 | 172/200 = .860 | +0.0 pp |
| mega_starmie vs mega_lucario | 139/200 = .695 | 143/200 = .715 | −2.0 pp |

**AGGREGATE delta +2.92 pp, 95% CI [−0.46, +6.30] pp, 0 crashes in 2400 games (45.6 min).**

**FLIP: True** — the grilled rule is `delta >= 0 AND CI-lo >= -1% AND crashes == 0`, and −0.46 pp
clears it. Read the precision beside the verdict: at ±3.4 pp this interval is nowhere near tight
enough to have cleared −1% on width alone (that needs thousands of games per arm per matchup); it
clears because the delta is clearly positive. What the run establishes unconditionally is the crash
gate — a hard zero over 2400 games on the real engine, across every deck pairing — and that no
regression worse than 0.46 pp is consistent with the data. Five of six matchups improve or hold; the
one negative (−2.0 pp) sits well inside its own sampling noise at n=200.

Raw: `swap_paired_ab.json` from the run (`reports/` is gitignored, so the numbers are transcribed
here rather than committed).

## Still owed

- **Answers to Rulings 1–4.** The code shipped under the recommendation stated in each; the deletion
  commit could not wait on the answers without leaving two deciders alive indefinitely, which the
  protocol forbids for a different reason. Each ruling names the concrete change if you decide the
  other way, and each is a small, contained edit.
- **Orphaned Context surface.** The 19 deletions left `attach_target_is_priority_wincon`,
  `attach_from_target_is_concentrate` and `attach_from_target_needs` on `Context` with no reader, and
  their `Board` sources (`priority_wincon_slot`, `attach_from_concentrate_slot`) still compute per
  decision. Deliberately NOT cut here: `priority_wincon_slot` is independently pinned as a Board fact
  by three tests, and unpicking that chain is deck-layer attach work, which ADR-0069's Out of Scope
  routes to `/deck-align` after this lands. Flagged so it is a visible debt rather than a silent one.
