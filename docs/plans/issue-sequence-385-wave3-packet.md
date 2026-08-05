# Wave-3 packet — issue-sequence run (385, 386)

Gate flips from this batch, pending developer ruling. **Nothing was conformed into either
`baseline.json`** — a baseline is a ruling record, not something a sub-issue may recapture on its own
recognizance, and auto-recapture is exactly how the old Decision Gate died.

Issue #385 (POC-T4/4, the composer core, DARK) produced **zero** flips: both gates were byte-identical
at that commit, which was its acceptance line. Everything below comes from **Issue #386** (POC-T4/5,
the arming swap).

---

## 0 · Headline — the arming swap was BUILT, MEASURED, and is NOT LANDED

The swap Issue #386 specifies was implemented in full and run against both gates and the whole
suite. **The measurement says it must not land as specified**, and the reasons are two OWED DESIGN
RULINGS rather than defects in the build. The implementation is preserved in this branch's history so
a re-run costs a `git revert`, not a rebuild:

| | before (Issue #385 tip) | after arming |
|---|---|---|
| Decision Gate | **PASS** — 0 unruled | **FAIL** — 68 unruled REGRESSION |
| Decision Gate agreement | **251/340** | **169/340** (173 picks moved) |
| Leaf gate (re-pointed, §3) | **PASS** — 0 unruled | **FAIL** — 55 unruled `OK → MISS` |
| `pytest tests/ -q` | 5240 passed | **211 failed**, 4969 passed |
| composer-vs-ruled, MAIN frames | 79/270 (dark measurement) | unchanged — the composer itself did not change |

**All three of the track's named acceptance frames REGRESS**, which is Issue #386's own acceptance
criterion failing on its own terms:

| frame | case | human | composer | gate |
|---|---|---|---|---|
| `85046350\|0\|decision\|32` | **f32** | `[1]` | `[3]` | Decision (owner #165) |
| `86091435\|0\|decision\|35` | **f35** | `[1]` | `[0]` | Decision + Leaf (owner #165) |
| `85785609\|0\|turn\|8` | **f82** | `[1]` | `[4]` | Decision (owner #165) |

---

## 1 · Cause A — Issue #392 is still OWED, and it is what kills f32 / f35

Issue #392 (*"a retreat option is TARGETLESS, so 1-ply differencing cannot price it"*) declares itself
a blocker of Issue #385 and asks for a RULED beam-admission disposition. No ruling has been made. The
previous item in this batch re-measured its premise and found it SURVIVES: the ruled retreat is in
beam at **rank 4 of k=4 with margin 0.0**, on a frame where all five options price exactly 0.0 — it
survives on the tie-break, not on the leaf, and one positive-delta option pushes it out.

Armed, that is exactly what happens. f32 and f35 are the retreat-to-sacrificial-item-lock-wall
maneuver; the composer picks something with a positive 1-ply delta instead. **Issue #392's three
options (structural admission by kind / compound lookahead / accept-and-declare) are still the
decision, and it has to be made before this swap can land.**

## 2 · Cause B — the reveal-truncation ceiling, MEASURED for the first time

`common/composer.py`'s header declares this ceiling up front (Issue #385): *"A sequence that ends at
a REVEAL is a partial line. The engine re-presents the menu after a draw/search, so the composer stops
there and replans — which means such a candidate carries `EV(terminal) = 0` and is compared against
full attack lines that carry a prize."*

Armed, it bites at full strength, and the shape is unmistakable. Over the 270 MAIN single-pick corpus
frames that carry a ruling, by OPTION KIND:

| kind | human ruled | composer picks |
|---|---|---|
| `_PLAY` (a card from hand — Supporters, Items, benching a Basic) | **94** | **11** |
| `_ATTACH` (Energy) | 81 | **138** |
| `_ATTACK` | 45 | **69** |
| `_END` | 18 | 16 |
| `_EVOLVE` | 16 | 19 |
| `_RETREAT` | 12 | 17 |

The composer plays a card from hand on **11 of 270** frames where the human ruled one on **94**, and
makes up the difference in attaches and attacks. This is arithmetically correct on the composer's own
terms and is not a units bug — `attack_ev` returns PRIZES, the same unit `state_value` reports, so the
sum is commensurate. A draw/search Supporter's sequence TRUNCATES at the reveal and therefore scores
`state_value(one card less in hand) + 0`, while an attach→attack line scores
`state_value(end) + EV(attack)` with a prize in it. Setup plays lose to attacks by construction.

**This is a design question, not a tuning one**, and it is not in Issue #386's scope to answer.
Filed as Issue #400 (see §5).

## 3 · The leaf gate WAS re-pointed, as Issue #386 requires

`leaf_lab.board_leaf_values` scored every option via `planner._engine_leaf_value` — the exact function
the develop-rollout retirement deletes. It now reads `composer.compose(...).fanned`, the shipped
scorer's own depth-0 1-ply deltas, fanned across each Option-Equivalence class. Same question, same
corpus, same frame keys, same verdicts; a different and now-shipped scorer. The re-point is in the
reverted arming commit and comes back with it.

Its result is the 55 unruled `OK → MISS` above. Since the leaf gate and the Decision Gate now measure
the SAME scorer from two angles, their flip sets overlap heavily and should be ruled together.

---

## 4 · Flips — `wave_scan.py` shape (`frame | old | new | rec`)

Ready to post to Issue #263 by the developer. **Not posted by this run.**

### 4a · Decision Gate — REGRESSION rows

| frame | case | old | new | human | held-out owner |
|---|---|---|---|---|---|
| `81785223\|0\|decision\|12` |  | `[1]` | `[0]` | `[1]` | — |
| `81785223\|0\|decision\|38` |  | `[4]` | `[3]` | `[4]` | — |
| `81903490\|0\|decision\|10` |  | `[1]` | `[0]` | `[1]` | — |
| `81903490\|0\|decision\|5` |  | `[1]` | `[2]` | `[1]` | — |
| `81904064\|0\|decision\|17` |  | `[2]` | `[3]` | `[2]` | — |
| `81904064\|0\|decision\|49` |  | `[0]` | `[2]` | `[0]` | — |
| `81904064\|0\|decision\|9` |  | `[1]` | `[0]` | `[1]` | — |
| `81904451\|0\|decision\|15` |  | `[2]` | `[3]` | `[2]` | — |
| `81905063\|1\|decision\|10` |  | `[2]` | `[3]` | `[2]` | — |
| `81905522\|0\|decision\|10` |  | `[1]` | `[0]` | `[1]` | — |
| `81906131\|1\|decision\|26` |  | `[1]` | `[3]` | `[1]` | — |
| `81906755\|1\|decision\|77` |  | `[0]` | `[6]` | `[0]` | — |
| `82224509\|1\|decision\|41` |  | `[4]` | `[3]` | `[4]` | — |
| `82224509\|1\|decision\|67` |  | `[5]` | `[2]` | `[5]` | — |
| `82225643\|1\|decision\|34` |  | `[0]` | `[1]` | `[0]` | — |
| `82226116\|0\|decision\|48` |  | `[13]` | `[4]` | `[13]` | — |
| `82226116\|0\|decision\|7` |  | `[1]` | `[0]` | `[1]` | — |
| `82229122\|0\|decision\|45` |  | `[16]` | `[3]` | `[16]` | — |
| `82523811\|1\|decision\|15` |  | `[3]` | `[0]` | `[3]` | — |
| `82523811\|1\|decision\|79` |  | `[0]` | `[1]` | `[0]` | — |
| `82525101\|1\|decision\|102` |  | `[0]` | `[2]` | `[0]` | — |
| `82525101\|1\|decision\|92` |  | `[0]` | `[2]` | `[0]` | — |
| `82717711\|0\|decision\|18` |  | `[1]` | `[0]` | `[1]` | — |
| `82749168\|1\|decision\|21` |  | `[7]` | `[2]` | `[7]` | — |
| `82749168\|1\|decision\|61` |  | `[6]` | `[0]` | `[6]` | — |
| `82752604\|0\|decision\|14` |  | `[0]` | `[4]` | `[0]` | — |
| `82754875\|0\|decision\|52` |  | `[0]` | `[1]` | `[0]` | — |
| `82756664\|1\|decision\|37` |  | `[3]` | `[2]` | `[3]` | — |
| `82867148\|0\|decision\|34` |  | `[1]` | `[0]` | `[1]` | — |
| `83007714\|1\|decision\|65` |  | `[7]` | `[1]` | `[7]` | — |
| `83038055\|0\|decision\|40` |  | `[0]` | `[1]` | `[0]` | — |
| `83116081\|0\|decision\|76` |  | `[5]` | `[0]` | `[5]` | — |
| `83456015\|0\|decision\|35` |  | `[3]` | `[1]` | `[3]` | — |
| `83661652\|0\|decision\|29` |  | `[0]` | `[1]` | `[0]` | — |
| `83661652\|0\|decision\|33` |  | `[2]` | `[1]` | `[2]` | — |
| `83661652\|0\|decision\|40` |  | `[3]` | `[2]` | `[3]` | — |
| `83664340\|1\|decision\|45` |  | `[0]` | `[3]` | `[0]` | — |
| `83665798\|1\|decision\|12` |  | `[7]` | `[1]` | `[7]` | — |
| `83665798\|1\|decision\|39` |  | `[4]` | `[0]` | `[4]` | — |
| `83667237\|0\|decision\|120` |  | `[3]` | `[7]` | `[3]` | — |
| `83667237\|0\|decision\|87` |  | `[2]` | `[0]` | `[2]` | — |
| `83966336\|0\|decision\|44` |  | `[0]` | `[2]` | `[0]` | — |
| `83968638\|1\|decision\|17` |  | `[0]` | `[3]` | `[0]` | — |
| `84071010\|0\|decision\|30` |  | `[0]` | `[2]` | `[0]` | — |
| `84890060\|1\|decision\|11` |  | `[1]` | `[2]` | `[1]` | — |
| `84890060\|1\|decision\|12` |  | `[2]` | `[1]` | `[2]` | — |
| `84897262\|1\|decision\|100` |  | `[0]` | `[5]` | `[0]` | — |
| `85045840\|0\|decision\|6` |  | `[2]` | `[4]` | `[2]` | — |
| `85045840\|0\|decision\|8` |  | `[1]` | `[3]` | `[1]` | — |
| `85046350\|0\|decision\|79` |  | `[4]` | `[6]` | `[4]` | — |
| `85046350\|0\|decision\|81` |  | `[2]` | `[4]` | `[2]` | — |
| `85058051\|1\|decision\|4` |  | `[1]` | `[2]` | `[1]` | — |
| `85058574\|1\|decision\|16` |  | `[6]` | `[2]` | `[6]` | — |
| `85058574\|1\|decision\|69` |  | `[1]` | `[2]` | `[1]` | — |
| `85059103\|0\|decision\|84` |  | `[3]` | `[1]` | `[3]` | — |
| `85163079\|0\|decision\|30` |  | `[0]` | `[2]` | `[0]` | — |
| `85785067\|0\|decision\|14` |  | `[2]` | `[1]` | `[2]` | — |
| `85785067\|0\|decision\|42` |  | `[4]` | `[2]` | `[4]` | — |
| `85785067\|0\|decision\|54` |  | `[4]` | `[2]` | `[4]` | — |
| `85786096\|0\|decision\|24` |  | `[0]` | `[4]` | `[0]` | — |
| `85786096\|0\|decision\|38` |  | `[0]` | `[3]` | `[0]` | — |
| `85786096\|0\|decision\|70` |  | `[2]` | `[3]` | `[2]` | — |
| `85786096\|0\|turn\|2` |  | `[0]` | `[4]` | `[0]` | — |
| `86090147\|0\|turn\|3` |  | `[4]` | `[5]` | `[4]` | — |
| `86090164\|1\|decision\|40` |  | `[0]` | `[1]` | `[0]` | — |
| `86090676\|1\|decision\|39` |  | `[2]` | `[1]` | `[2]` | — |
| `86091435\|0\|decision\|30` |  | `[0]` | `[1]` | `[0]` | — |
| `86091728\|0\|decision\|19` |  | `[2]` | `[1]` | `[3]` | — |
| `81785223\|0\|decision\|44` |  | `[4]` | `[3]` | `[4]` | #263 |
| `81904064\|0\|decision\|44` |  | `[0]` | `[2]` | `[0]` | #263 |
| `81904064\|0\|decision\|59` |  | `[1]` | `[2]` | `[1]` | #263 |
| `81904451\|0\|decision\|24` |  | `[1]` | `[2]` | `[1]` | #263 |
| `81904451\|0\|decision\|53` |  | `[6]` | `[11]` | `[6]` | #263 |
| `81904451\|0\|decision\|9` |  | `[1]` | `[0]` | `[1]` | #332 |
| `81906755\|1\|decision\|9` |  | `[1]` | `[0]` | `[1]` | #332 |
| `82225138\|0\|decision\|82` |  | `[0]` | `[2]` | `[0]` | #263 |
| `82225643\|1\|decision\|11` |  | `[0]` | `[1]` | `[0]` | #263 |
| `82227388\|0\|decision\|50` |  | `[2]` | `[3]` | `[2]` | #263 |
| `82228017\|0\|decision\|16` |  | `[1]` | `[2]` | `[1]` | #263 |
| `82228017\|0\|decision\|4` |  | `[1]` | `[2]` | `[1]` | #263 |
| `82229122\|0\|decision\|17` |  | `[4]` | `[2]` | `[4]` | #263 |
| `82525101\|1\|decision\|69` |  | `[2]` | `[3]` | `[2]` | #263 |
| `82717711\|0\|decision\|37` |  | `[1]` | `[0]` | `[1]` | #369 |
| `83007714\|1\|decision\|8` |  | `[2]` | `[1]` | `[2]` | #369 |
| `83054602\|1\|decision\|32` |  | `[3]` | `[1]` | `[3]` | #263 |
| `83116501\|0\|decision\|70` |  | `[7]` | `[0]` | `[7]` | #263 |
| `83457493\|1\|decision\|20` |  | `[3]` | `[4]` | `[3]` | #332 |
| `83457493\|1\|decision\|31` |  | `[4]` | `[5]` | `[4]` | #369 |
| `83686860\|1\|decision\|29` |  | `[0]` | `[4]` | `[0]` | #369 |
| `83966968\|0\|decision\|45` |  | `[2]` | `[5]` | `[2]` | #369 |
| `84071010\|0\|decision\|15` |  | `[0]` | `[4]` | `[0]` | #165 |
| `84071010\|0\|decision\|64` |  | `[2]` | `[1]` | `[2]` | #332 |
| `85046350\|0\|decision\|21` |  | `[1]` | `[4]` | `[1]` | #263 |
| `85046350\|0\|decision\|32` | f32 | `[1]` | `[3]` | `[1]` | #165 |
| `85046350\|0\|decision\|85` |  | `[3]` | `[5]` | `[3]` | #351 |
| `85163634\|1\|decision\|41` |  | `[0]` | `[5]` | `[0]` | #143 |
| `85709280\|1\|decision\|42` |  | `[1]` | `[7]` | `[1]` | #369 |
| `85709280\|1\|decision\|55` |  | `[0]` | `[6]` | `[0]` | #369 |
| `85785609\|0\|turn\|8` | f82 | `[1]` | `[4]` | `[1]` | #165 |
| `86089638\|0\|decision\|18` |  | `[8]` | `[7]` | `[8]` | #263 |
| `86090164\|1\|turn\|2` |  | `[0]` | `[4]` | `[0]` | #332 |
| `86091435\|0\|decision\|35` | f35 | `[1]` | `[0]` | `[1]` | #165 |
| `81785223\|0\|decision\|32` |  | `[4]` | `[3]` | `[4]` | — |
| `81904451\|0\|decision\|58` |  | `[6]` | `[11]` | `[6]` | — |
| `82227388\|0\|decision\|7` |  | `[4]` | `[0]` | `[4]` | — |

**68 carry no owner** (the unruled set the gate fails on) and **34** are
already held out to a live owner. Recommendation for every row is the same and it is a single
decision, not 105 of them: **rule Issue #392 and Issue #400 first**; these flips are their
consequence, and ruling them one by one before the two causes are settled would be ruling a symptom.

### 4b · Leaf gate — `OK → MISS` rows (re-pointed scorer)

103 rows, 55 of them unruled. Same recommendation, same reason. Full list is
reproducible in one command against the reverted commit:

```
git revert --no-commit 7db12801 && python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json
```

| frame | old rank | new rank | held-out owner |
|---|---|---|---|
| `81903490\|0\|decision\|67` | 1 | 4 | — |
| `81903490\|0\|decision\|74` | 1 | 2 | — |
| `81904064\|0\|decision\|49` | 1 | 2 | — |
| `81904451\|0\|decision\|15` | 1 | 2 | — |
| `81905063\|1\|decision\|10` | 1 | 2 | — |
| `81906131\|1\|decision\|26` | 1 | 2 | — |
| `81906755\|1\|decision\|77` | 1 | 2 | — |
| `82224509\|1\|decision\|40` | 1 | 2 | — |
| `82224509\|1\|decision\|41` | 1 | 2 | — |
| `82224509\|1\|decision\|71` | 1 | 3 | — |
| `82225643\|1\|decision\|34` | 1 | 4 | — |
| `82226116\|0\|decision\|48` | 1 | 8 | — |
| `82226759\|1\|decision\|16` | 1 | 2 | — |
| `82227388\|0\|decision\|30` | 1 | 3 | — |
| `82523811\|1\|decision\|105` | 1 | 2 | — |
| `82523811\|1\|decision\|15` | 1 | 2 | — |
| `82523811\|1\|decision\|79` | 1 | 2 | — |
| `82523811\|1\|decision\|95` | 1 | 2 | — |
| `82524455\|1\|decision\|27` | 1 | 2 | — |
| `82525101\|1\|decision\|102` | 1 | 2 | — |
| `82525101\|1\|decision\|87` | 1 | 2 | — |
| `82525101\|1\|decision\|92` | 1 | 3 | — |
| `82748422\|0\|decision\|26` | 1 | 2 | — |
| `82749168\|1\|decision\|29` | 1 | 6 | — |
| `82749168\|1\|decision\|61` | 1 | 2 | — |
| `82752045\|1\|decision\|115` | 1 | 2 | — |
| `82752604\|0\|decision\|88` | 1 | 3 | — |
| `82754875\|0\|decision\|52` | 1 | 2 | — |
| `82754875\|0\|decision\|8` | 1 | 2 | — |
| `82756664\|1\|decision\|35` | 1 | 2 | — |
| `82756664\|1\|decision\|37` | 1 | 2 | — |
| `83007714\|1\|decision\|135` | 1 | 2 | — |
| `83038055\|0\|decision\|40` | 1 | 3 | — |
| `83053965\|1\|decision\|91` | 1 | 4 | — |
| `83116081\|0\|decision\|17` | 1 | 2 | — |
| `83116081\|0\|decision\|76` | 1 | 2 | — |
| `83456015\|0\|decision\|35` | 1 | 2 | — |
| `83661652\|0\|decision\|29` | 1 | 2 | — |
| `83661652\|0\|decision\|33` | 1 | 2 | — |
| `83661652\|0\|decision\|40` | 1 | 2 | — |
| `83664340\|1\|decision\|24` | 1 | 2 | — |
| `83664340\|1\|decision\|45` | 1 | 8 | — |
| `83667237\|0\|decision\|120` | 1 | 3 | — |
| `83968638\|1\|decision\|17` | 1 | 6 | — |
| `84071010\|0\|decision\|30` | 1 | 3 | — |
| `84897262\|1\|decision\|100` | 1 | 2 | — |
| `85058574\|1\|decision\|109` | 1 | 2 | — |
| `85058574\|1\|decision\|69` | 1 | 3 | — |
| `85058574\|1\|decision\|87` | 1 | 3 | — |
| `85163079\|0\|decision\|30` | 1 | 3 | — |
| `85785067\|0\|decision\|42` | 1 | 3 | — |
| `85786096\|0\|decision\|24` | 1 | 2 | — |
| `85786096\|0\|turn\|2` | 1 | 2 | — |
| `86090164\|1\|decision\|40` | 1 | 3 | — |
| `86091435\|0\|decision\|96` | 1 | 4 | — |
| `81785223\|0\|decision\|44` | 1 | 3 | #263 |
| `81904064\|0\|decision\|44` | 1 | 2 | #263 |
| `81904064\|0\|decision\|59` | 1 | 2 | #263 |
| `81904451\|0\|decision\|24` | 1 | 2 | #263 |
| `81904451\|0\|decision\|37` | 1 | 3 | #369 |
| `81904451\|0\|decision\|50` | 1 | 4 | #369 |
| `81904451\|0\|decision\|53` | 1 | 4 | #263 |
| `81905522\|0\|decision\|64` | 1 | 5 | #263 |
| `81906755\|1\|decision\|93` | 1 | 2 | #332 |
| `82225138\|0\|decision\|82` | 1 | 3 | #263 |
| `82225643\|1\|decision\|57` | 1 | 4 | #369 |
| `82226759\|1\|decision\|29` | 1 | 2 | #262 |
| `82227388\|0\|decision\|43` | 1 | 3 | #369 |
| `82227388\|0\|decision\|50` | 1 | 3 | #263 |
| `82228017\|0\|decision\|16` | 1 | 2 | #263 |
| `82228017\|0\|decision\|4` | 1 | 4 | #263 |
| `82229122\|0\|decision\|17` | 1 | 4 | #263 |
| `82229122\|0\|decision\|33` | 1 | 3 | #369 |
| `82522698\|1\|decision\|36` | 1 | 3 | #369 |
| `82523811\|1\|decision\|84` | 1 | 9 | #263 |
| `82525101\|1\|decision\|69` | 1 | 2 | #263 |
| `82717711\|0\|decision\|37` | 1 | 2 | #369 |
| `82749168\|1\|decision\|88` | 1 | 2 | #263 |
| `82752604\|0\|decision\|61` | 1 | 3 | #263 |
| `82866415\|0\|decision\|43` | 1 | 5 | #369 |
| `82866415\|0\|decision\|48` | 1 | 3 | #263 |
| `83037962\|0\|decision\|48` | 1 | 2 | #332 |
| `83116501\|0\|decision\|70` | 1 | 5 | #263 |
| `83661649\|0\|decision\|30` | 1 | 2 | #272 |
| `83661649\|0\|decision\|54` | 1 | 11 | #332 |
| `83661652\|0\|decision\|19` | 1 | 2 | #165 |
| `83661652\|0\|decision\|44` | 1 | 2 | #165 |
| `83664991\|0\|decision\|25` | 1 | 2 | #263 |
| `83666442\|1\|decision\|27` | 1 | 3 | #263 |
| `83966968\|0\|decision\|45` | 1 | 3 | #369 |
| `84071010\|0\|decision\|64` | 1 | 4 | #332 |
| `85046350\|0\|decision\|21` | 1 | 2 | #263 |
| `85046350\|0\|decision\|85` | 1 | 5 | #351 |
| `85163079\|0\|decision\|51` | 1 | 2 | #369 |
| `86089638\|0\|decision\|18` | 1 | 4 | #263 |
| `86090164\|1\|turn\|2` | 1 | 2 | #332 |
| `86091435\|0\|decision\|35` | 1 | 2 | #165 |
| `81785223\|0\|decision\|32` | 1 | 3 | — |
| `81904451\|0\|decision\|58` | 1 | 4 | — |
| `82525741\|0\|decision\|81` | 1 | 3 | — |
| `82756664\|1\|decision\|36` | 1 | 2 | — |
| `83662396\|1\|decision\|19` | 1 | 2 | — |
| `86091435\|0\|turn\|14` | 1 | 3 | — |

---

## 5 · What this run left behind

* **Issue #386 stays OPEN** at `status:3-build`. Its build is done and measured; what it lacks is two
  rulings, neither of which is a sub-issue's to make.
* **Issue #392** — already open, already declaring itself a blocker of Issue #385. This run is its
  first ARMED measurement and confirms it blocks Issue #386 too.
* **Issue #400** — filed by this run: the reveal-truncation ceiling, with the 94→11 measurement.
* **The arming commit is in this branch's history and immediately reverted.**
  `30f20fb8` is the build; `7db12801` reverts it and carries the measurement in its message.
  Re-running it after the rulings land is `git revert 7db12801` plus whatever the rulings change —
  not a rebuild.

