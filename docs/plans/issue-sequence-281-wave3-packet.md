# Wave-3 packet — issue-sequence run (Issues #281, #280, #343, #282, #345, #346, #284, #285, #286)

Gate flips from this batch, pending developer ruling. None conformed into either baseline.json —
a baseline is a ruling record, not something a sub-issue may recapture on its own recognisance.

Each sub-issue in this run measures its own contribution by an explicit **before/after A/B**: stash
the working tree, run the gate against the committed baseline, unstash, run it again, diff the two
reports. A clean baseline diff alone proves only *"no NEW unruled flip"*, which is not the same
claim as *"this change moved nothing"*.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|
| `81906755\|1\|decision\|9` | leaf (Discrimination) | Issue #280 | OK, rank 1/2, ruled option scores 480.70 | MISS, rank 2/2, ruled option 418.20 vs top 475.45 | **REVERT** — the reading is card-true, the resulting preference is not. See below. |

Issue #281: **zero** flips on either gate.
Issue #280: **one** leaf flip (above); Decision Gate **PASS, 0 picks moved, 0 rulings moved**.
Issue #284: **zero NEW** flips — and the leaf A/B moved in the GOOD direction (two ruled
regressions resolved, SOLE-top 32 → 33). Three lines owed to the developer all the same; see
*Issue #284* below.
Issue #343: **zero** flips on either gate — but read the section below before treating the leaf
half of that as evidence, because on this surface the leaf gate is blind by construction.

## `81906755|1|decision|9` — my own Energy raises their damage, and the leaf wants to dump it

**The frame.** Turn 1, `mega_starmie`, two options only: `[0] Retreat` / `[1] End`. The human ruled
**`[1] End`**, category `bad_retreat`, rationale *"dont waste energy by needlessly retreating"*. My
Active is a Staryu (70 HP) carrying the turn's one attached Basic {W}; two more bare Staryu sit on
the Bench. Their Active is **Teal Mask Ogerpon ex** with **zero** Energy; their Mega Kangaskhan ex
is Benched.

**What changed, mechanically.** Verified at source — `data/EN_Card_Data.csv` Card ID 96, Teal Mask
Ogerpon ex (TWM 25), Myriad Leaf Shower `{G}{G}{G}` 30: *"This attack does 30 more damage for each
Energy attached to **both** Active Pokémon."* That is the Damage Formula's `both_active_energy`
scaler at 30 per unit — the one **direction-symmetric** variable in the vocabulary (ADR-0083 §4).

On this board `both_active_energy` is **1**, and the one unit is *mine*: `atk_active_energy`
(theirs) = 0, `def_active_energy` (mine) = 1. Their Active cannot pay `{G}{G}{G}` until turn 3 under
the ceiling policy, and their Benched Kangaskhan cannot be promoted (Ogerpon's retreat is 1 and it
holds no Energy, so `_promotion_open` is shut). So the accumulating clock on my Active is:

| | t=3 | t=4 | t=5 | `turns_to_ko_me` |
|---|---|---|---|---|
| printed read (before) | 30 | 60 | 90 | **5** |
| with their damage context | 60 | 120 | — | **4** |

`docs/rules.md` §3 (line 89): a manual retreat is *"pay the Retreat cost in Energy"*. Retreating
discards that {W}, which takes `both_active_energy` to 0 and the clock back to 5. So the leaf now
scores Retreat above End by 57.25, and the human's option loses 62.50 in absolute terms.

**Why REVERT is recommended.** The scaler reading is exactly what Issue #280 exists to deliver and
is not in question: the card says what it says, and a printed-damage read could not see it. What is
in question is the *preference it produces*. Their Ogerpon is three turns from being able to use the
attack at all, and the play buys 30 damage of relief at turn 3 by throwing away turn 1's only
attach — which is the human's ruling in one sentence. The cost of the discarded Energy is priced by
`readiness`, which is CAPPED (`_READINESS_CAP`), while `survival` is uncapped and
prize-denominated, so on a two-option turn-1 menu the survival gain outbids the readiness loss by
construction rather than on the merits.

**This is a balance question, not a scaler question**, which is why it is a packet line and not a
fix inside Issue #280. Three dispositions are available and the ruling should name one:

1. **REVERT** (recommended) — record the leaf's ranking as wrong here and leave the frame failing
   the gate, as the wave-3 convention already does for 67 other frames. Nothing on disk changes.
2. Treat it as evidence for the standing `SATURATION` / cap-mismatch thread between `survival`'s
   uncapped prize denomination and the positional caps — the same asymmetry
   `data/leaf_lab/wave3-rulings.md` already records. That is a `state_value` design question, not
   this issue's.
3. CONFORM, if the developer judges that dumping Energy against a `both_active_energy` attacker is
   genuinely correct play. Only a CONFORM would move a baseline, and only the developer may.

**Live play is unaffected today.** The Decision Gate is PASS with 0 picks moved, so no shipped
decision changes; this is the leaf's isolated ranking, which Issue #263 (T4) is what makes live.

## What Issue #280 moved, in full — the A/B against the pre-change tree

Same 268 leaf frames, same committed baseline (`d8ef7a0`), the only difference being Issue #280's diff:

* **21 of 277 scored leaf rows changed VALUE**, across **13 distinct episodes** — 81785223,
  81906755, 82226116, 82226759, 82228017, 82228640, 82522726, 82753102, 82754875, 84889011,
  85163634, 85164605, 86089638.
* **6 rows changed RANK**, and they do not all move the same way — two IMPROVED
  (`82228640` 5→4, `82753102` 8→6) and four worsened (`84889011` 5→6, `82226116` 5→10,
  `82226759` 3→4, and the flip above, 1→2 with the OK→MISS).
* **1 OK → MISS**, the flip above. **0 MISS → OK.**
* Decision Gate: 0 picks moved, 0 rulings moved.

That 21-in-277 is the honest size of this change on the develop corpus, and it is consistent with
the independent read taken before the code was written: replaying both call sites over the whole
371-frame corrections corpus with and without the context moves **20 body clocks and 5 bench-empty
doom reads**. The change is real, small, and mostly invisible to rank.

## The 15 deferred `mega_starmie` frames: **0 of 15 moved, for the second time**

Issue #262's wave-3 packet deferred 15 REVERT-worthy frames to Issue #278 S13
([Issue #262 comment](https://github.com/richard-jh-mccrae/PokemonAI/issues/262#issuecomment-5153527951)),
13 of them `survival`-driven, on the hypothesis that S2 (Issue #280) and S3 (Issue #281) were the cause.

Both halves have now landed and the answer is the same from each:

| | frames moved, of 15 |
|---|---|
| Issue #281 (`threat`'s reachability gate) | **0** |
| Issue #280 (`survival`'s damage context) | **0** |

Checked per frame, not in aggregate: every one of the 15 appears in the leaf gate's HELD OUT block
with byte-identical `OK -> MISS` and `rank` before and after Issue #280's diff. The deferral comment's own
closeout question — *"passivity persists ⇒ a real signal; passivity evaporates ⇒ these were a
symptom of the two bugs"* — therefore resolves to **persists**, and the comment's stated consequence
follows: phase damping can now be designed against a measurement taken on a level field.

The comment predicted the two `†` frames (`82522698|1|decision|62`, `82749168|1|decision|88`) would
not move for an unrelated reason. They did not — but neither did the other 13, so that prediction
does not distinguish anything here.

Note also that the S13 hypothesis in that comment — *"`mega_starmie` is the deck whose attack
selection is explicitly weakness-conditional … if the printed-damage gate is what leaves `survival`
unopposed on these boards, this is the deck where it would show first"* — is now **refuted by
measurement**: the printed-damage gate was replaced (Issue #281) and the survival clock was made
damage-aware (Issue #280), and neither touched a single one of the 15. The cause is somewhere else.

## Issue #343 — the reads moved, no decision did, and the leaf gate could not have seen it

`pilot._opponent_target_rows` and `pilot._strip_delta_terms` now thread the THEIRS-direction damage
context into all four of their clock legs. Both gates are unchanged from the pre-change tree:

| | pre-change | post-change |
|---|---|---|
| Discrimination (leaf) | FAIL — 1 unruled, 67 ruled, 3 voided | FAIL — **1 unruled**, 67 ruled, 3 voided |
| Decision | PASS — agree 250/347, 0 picks moved | PASS — agree **250/347**, **0 picks moved** |

The one unruled leaf flip is Issue #280's `81906755|1|decision|9`, already ruled above. **Issue #343
adds no flip to either gate and neither baseline was touched.**

### The leaf A/B is 0 of 277 — and that is the instrument, not the change

Against the pre-change tree (not just the committed baseline): **0 of 277 scored leaf rows moved in
value, 0 in rank, 0 `OK -> MISS`, 0 `MISS -> OK`.** That number must NOT be read as *"this change
moves nothing"*, because the leaf gate cannot reach this surface:

* `planner._engine_leaf_value` scores `KO_SCORE x state_value(end board)`, and `state_value`'s
  `threat` family calls `needs.opponent_target_value(prize_advance=…, **survival_shift=0**, phase=…)`
  with the zero hardcoded (`state_value.py`, and its own `blind_to` says so). It never reads
  `_opponent_target_rows`' `survival_shift` or `_strip_delta_terms`' `strip_shift`.
* **Positive control, same lab and same corpus:** Issue #280 landed one commit earlier, on a read
  `state_value` DOES take, and moved **21 of 277** rows. So the lab demonstrably moves when the
  change is in its path. The 0 here is attributable to the surface.

So the load-bearing measurement for this issue is the **Decision Gate**, which replays the real
`decide()` over 372 frames and reports **0 picks moved**.

### What did move: the reads themselves

Read-only replication of both call sites with and without `model.damage_context(attacker="theirs")`
over the whole corrections corpus — **359 frames** with a live Active and a non-empty opponent board:

| read | frames / bodies whose value changes |
|---|---|
| `_opponent_target_rows` base clock | **15** |
| `_opponent_target_rows` removal Δ (`survival_shift`) | **32** |
| `_strip_delta_terms` strip Δ (`strip_shift`) | **14** |

**These are NOT the numbers Issue #343's body claims** (20 / 31 / 16 on 358 frames). The measurement
was re-taken independently for this build and did not reproduce; the issue was self-filed by the
previous sub-issue's implementer and its measurement section is corrected here rather than repeated.
Direction check, over the same sweep: **0** base clocks LENGTHENED, as required — a Damage Formula
scaler only ever adds damage, so learning to price one can only shorten a clock.

Two other claims in that self-filed issue also failed re-verification and are recorded so the
ledger is not left standing on them:

* its worked example calls frame `82753102|16`'s clock-setter *"their Alakazam"* — the corpus record
  holds Abra (741) Active with Dunsparce (305) and Abra benched, **no Alakazam in play**;
* it states that frame's base clock as `6 -> 1` and its removal Δ as `-4 -> 0`. Measured: base
  **`2 -> 1`**, Δ **`+4 -> 0`**. A removal Δ is `clock(board minus body) - clock(board)` and removing
  a body can only lengthen my clock, so a negative Δ is **structurally impossible** at that call site.

The issue's central factual claim — that these two sites passed no `context` while their siblings
did — **is true**, and was re-verified at `git show 764d5b93:src/common/pilot.py` before any code
moved. Only the surrounding measurements were wrong.

### No developer ruling was owed on the deny half

Issue #343 asks whether `_strip_delta_terms` belongs to Issue #228 (epic Issue #278's ruled-omission
ledger routes *"energy denial / resource strip (`deny_relevance` dark) → #228"*). It does not, and
the ledger entry's premise has decayed: **Issue #228 is CLOSED** (`status:4-done`, 2026-07-31) and it
is the issue that ARMED both switches — `src/common/runtime.py` ships `deny_relevance: True` and
`deny_strip_delta: True`. Nothing here is dark, there is no live ruling to re-litigate, and this
change adds no term to `state_value` (which is what that ledger entry governs). Both halves shipped.

## Issue #282 — the premise did not survive, and the fix was already in the tree

**No flip on either gate, and no line in the table above, because this issue changed no executable
scoring path at all.** That needs saying plainly rather than reported as a quiet zero.

### The claim, and what HEAD says

Issue #282's body asserts that `CardStat.damageBoost` is *"consumed by `damage.py:114-125` via
`context["atk_boosts"]` as `(amount, atype, vs_ex)` triples — **a context no family builds**"*, and
prescribes the fix as *"populate `atk_boosts` in #279's context from the homed `transient_grants`
zone"*. Re-checked against `HEAD` before any code moved, three of its premises are stale:

1. **`atk_boosts` IS built, by both suppliers.** Issue #279 shipped `_SideBase.damage_boosts`
   (`src/common/state_model.py`) — the tracker's this-turn Trainer plays plus the boost Tools
   attached to that side's Active — carried on `SideFacts.damage_boosts` and turned into the
   `atk_boosts` key by the one builder (`strategy/damage_context.py`).
2. **`transient_grants` is HOMED, not owed.** `snapshot_coverage.py` homes it at
   `mine.active.grant`, and it holds the ADR-0033 *attack* grants (`self_lock` / `same_lock` /
   `self_bonus` / `prevent_all` / `reduction`) — not the flat Trainer boosts. The prescribed route
   would have read the wrong zone.
3. **Gravity Mountain (1252) is not a damage modifier.** `data/EN_Card_Data.csv`: *"Each Stage 2
   Pokémon in play (both yours and your opponent's) gets **-30 HP**."* Its parsed `damageBoost` is
   `0`, and the shipped whole-pool inventory test agrees —
   `tests/scouting/test_tool_holder_facts.py`: `carriers("damageBoost") == {1141: 30, 1158: 50,
   1171: 30, 1211: 40}`. So the issue's *"Gravity Mountain is two facts, not one … this issue covers
   the damage half only"* section has no damage half to cover. Its HP half remains genuinely
   unmodelled and stays with the Stadium ruling and Issue #263.

Two further claims in the issue body did not survive either, both found by the Spec axis rather than
by the build:

4. *"`footprints_writing_unhomed()` … **works off per-card clause unions**"* — it does not. It
   iterates `apply_option.FOOTPRINTS`, which is per-KIND (`_ATTACH` / `_EVOLVE` / `_RETREAT`). The
   clause-union guard is the sibling `snapshot_coverage.clauses_writing_unhomed()`. The conclusion
   the issue draws from it is nonetheless RIGHT, for a reason one step over: `_PLAY` is deliberately
   absent from `FOOTPRINTS`, and the per-OPTION footprint T4 will supply for it *is* a clause union.
   The landed docstring states the mechanism correctly rather than repeating the issue's version.
5. *"`mega_lucario` runs **7**"* — the copy counts are right (4x Premium Power Pro, 1x Black Belt's
   Training, 2x Gravity Mountain) but only **5** of the 7 carry a damage boost, because the two
   Gravity Mountains do not (point 3).

### Measured, on the plumbing the issue says does not exist

Board: my Mega Lucario ex with `{F}{F}` attached and the turn's attach spent, against Dragapult ex.

| live boost | `atk_boosts` | reach | `threat` | `state_value` |
|---|---|---|---|---|
| none | `()` | 270 | 0.0 | −1.13 |
| Premium Power Pro `(30, {F}, False)` | 1 triple | 300 | 0.0 | −1.13 |
| Power Pro x2 | 2 triples | 330 | 0.10 | **−1.03** |
| Black Belt's `(40, None, True)` | 1 triple | 310 | 0.0 | −1.13 |
| a `{W}`-gated 30, same amount | 1 triple | **270** | 0.0 | −1.13 |

Both gates the issue asks to be carried through are already carried: the attacker-type gate refuses
the `{W}`-gated copy on a `{F}` attacker, and the defender-`{ex}` gate pays Black Belt's 40 against
Dragapult **ex**. Against a 320 HP defender two Power Pros cross the breakpoint and the scalar moves
by the whole `threat` term. There was nothing to build.

And the symptom itself, priced as the whole `_PLAY` transition rather than as a boost held fixed —
Power Pro in hand and no boost live, versus the card gone and the boost live, against a 300 HP
Dragapult ex, with a `needs.Resolution` supplying the held card's Worth at `TAG_TIER["gust"]`:

| | `hand` | `threat` | total |
|---|---|---|---|
| before — card in hand, no boost | 0.083333 | 0.0 | −1.046667 |
| after — card played, boost live | 0.0 | **0.100000** | **−1.030000** |

**The play is worth +0.016667 prizes.** With the boost unpriced the identical play is
**−0.083333** — exactly *"minus the hand value of the card spent"*, the epic's sentence to six
decimal places. The margin is narrow by construction, which is what makes the test a claim rather
than a coincidence.

### What this issue therefore shipped instead

Only the parts of its own body that were genuinely unbuilt, plus the enumeration gap the symptom
was really about:

* **The four acceptance tests from the issue's own `## Tests` section**, at the scalar
  (`tests/strategy/test_state_value.py`), plus a fifth for the transition above. Every link of the
  chain was covered in isolation and the chain end-to-end was covered nowhere, which is exactly the
  shape that breaks silently in the middle. Instrument verified in both directions: severing
  `damage_facts`' boost leg turns 5 of the 6 red (the no-boost regression case correctly stays
  green), and deleting both gates in `strategy/damage.py` turns the two gate tests red.
* **`snapshot_coverage.WRITABLE` gains `this_turn_damage_boosts`**, homed at
  `mine.damage_boosts,theirs.damage_boosts`. The zone was **absent**, which is a worse status than
  `owed`: an owed zone is a scheduled gap with an owner, an unenumerated one is invisible to every
  assertion in the module. That absence is the real mechanism behind the issue's symptom.
  It overturns **no ruling**: the epic's ruled-omission ledger routes *attached Tools · special
  conditions · retreat allowance · transient grants* to Issue #260 and this is none of them, and the
  entry is inert — `homes()` / `unhomed()` are read by the audit test and by nothing on any scoring
  path.
* **The limitation the issue asks to be recorded**, in `apply_option.footprints_writing_unhomed()` —
  which was ALSO carrying a stale finding (*"Not empty, and that is the finding"*; T1/Issue #260
  homed both zones and `test_snapshot_coverage.py` has asserted it EMPTY since). Both guards are
  keyed on declared write-sets, and Premium Power Pro (1141), Black Belt's Training (1211) and Brave
  Bangle (1175) return `None` from `card_effects.json` — no clauses at all, so the union is empty and
  neither guard can ever see them. Now asserted as a test, not only a docstring.
* **`planner._leaf_state_model`'s omission of `turn_boosts` is documented as DELIBERATE**
  (scope note). `_simulate_line` stops when the select passes to the opponent, so its board is my
  END-OF-TURN board and a *"During this turn"* boost has expired by then; threading the live tracker
  there would inject a dead boost into `threat` and over-claim a Knock Out I could not take. The
  boost's value is already on that board — the sim cashed it, so the prize is in `prize_race`. The
  next reader who greps `turn_boosts` will find that call site missing the kwarg, and this is what
  stops them "fixing" it.

### A/B against the pre-change tree

Both gates, stashed and re-run against the committed baselines:

| | pre-change | post-change |
|---|---|---|
| Discrimination (leaf) | FAIL — 1 unruled, 67 ruled, 3 voided | FAIL — **1 unruled**, 67 ruled, 3 voided |
| Decision | PASS — agree 250/347, 0 picks moved | PASS — agree **250/347**, **0 picks moved** |

Both reports are **byte-identical** pre vs post. The leaf report is 384 lines and prints every one
of the 277 leaf frames' scored values at full float precision (`correct=-1602.0130208333335
top=-1576.04296875`), so byte-identity is zero movement on every scored row rather than an empty
report. The one unruled leaf flip is Issue #280's `81906755|1|decision|9`, ruled above. Neither
baseline was touched.

**And that zero is not evidence of correctness — it is evidence there was nothing to measure**,
which is the distinction Issue #343's section above exists to draw. Proven rather than asserted:
parse each changed `src/*.py` at `HEAD` and in the worktree, strip docstrings, compare the ASTs —
`apply_option.py` and `strategy/planner.py` come out **identical** (docstring-only), and
`snapshot_coverage.py` is the single code change, one `Zone(...)` entry in a registry whose readers
(`homes()`, `unhomed()`) are the audit test and nothing else. The comparator's own control: it
returns False for `return 1` vs `return 2` under two different docstrings.

The measurements that ARE evidence are the two above: the table showing the path live and moving,
and the new tests going red when either the supplier or either gate is severed. The lab's ability to
see a `state_value` change on this corpus is separately controlled by Issue #280, which moved 21 of
277 rows one commit earlier in this same batch.

### What `/code-review` changed

The Spec axis re-derived the load-bearing claim independently — driving the **real**
`TurnBoostTracker` with real PLAY logs of 1141 / 1211 through the **real** `EngineCardStatProvider`,
rather than through this build's fixtures — and reproduced the table above exactly (reach 270 → 300,
`threat` 0.0 → 0.10, `state_value` −1.13 → −1.03, Gravity Mountain yielding `()`). Both subsidiary
claims confirmed at source. It found the two further spec errors recorded above (points 4 and 5), and
one **genuine gap in this build**, since closed:

> the A/B never puts the card in the `before` hand, so `_PLAY`'s *"the card leaves hand"* leg — the
> symptom itself — is untested.

That is what the transition table two sections up now measures and what
`test_PLAYING_the_boost_card_is_priced_as_a_gain_and_not_as_the_hand_loss` asserts. The criterion's
other half — *"byte-identical to Issue #281"* — is a cross-COMMIT claim no assertion inside one
commit can reach, so it stays where the evidence actually is: the byte-identical gate A/B below,
with the test naming it rather than pretending to cover it.

The Standards axis verified all eight card facts against `data/EN_Card_Data.csv`, confirmed
`docs/rulebook.txt` L337 is an exact quote, confirmed no file gained CRLF, and found no vacuous
assertion. Its prose findings (bare `#281`/`#279` in comments, "pin" used as a NOUN for a test) are
fixed. "Pin" as a VERB is left alone deliberately: `CLAUDE.md`'s rule is about the noun (*"A test
fixture/Correction is not a 'pin'"*), and the verb is the surrounding style in ~20 files including
`damage_context.py` and `state_model.py`.

### One follow-on filed

**Issue #345** — Brave Bangle (1175), which `slowking` ships, parses to `damageBoost=0`: its text is
a third sentence form (*"If the Pokémon this card is attached to doesn't have a Rule Box, the
attacks it uses do 30 more damage …"*) carrying a holder gate `CardStat` has no field for.
`holderNameFamily` / `applies_to_holder` express an owner-NAME family, not a Rule Box. Not built
inline: it needs a pool-swept predicate and a decision about where the second holder gate lives,
which is a different subsystem from this issue's.
---

# Issue #345 — Brave Bangle's holder gate: a Rule Box, not a name

## Flips

**Zero on both gates.** Leaf: `1 unruled` — the same `81906755|1|decision|9` carried from
Issue #280 and already ruled above; nothing new, and the shipped and pre-change reports are
**byte-identical**. Decision Gate: **PASS, 0 picks moved, 0 rulings moved**. No row is added to the
Flips table because this change produced none.

## The zero is EXPLAINED, and the instrument was proved to read the changed path

A clean baseline diff proves only *"no NEW unruled flip"*, and an A/B zero proves only *"nothing
moved"* — neither says whether the lab could have seen a move. Issue #343's 0-of-277 turned out to be
an instrument artifact, so this one carries both controls.

**A/B.** Stash the tree, run both gates, unstash, diff the two reports. Byte-identical on both.
Restore verified by `cmp` of the pre- and post-stash patches. Pre-change control: with the tree
stashed, `EngineCardStatProvider` reports card 1175 `damageBoost = 0` and `CardStat` has no
`holderNoRuleBox` attribute at all — so the "before" arm really was the before.

**Sensitivity control — does the leaf lab read `CardStat.applies_to_holder`?** Severed it to
`return False` (every holder gate refuses) and re-ran the leaf gate. It moved: the gated-frame count
went 198 → 197 and 14 report lines changed, including `ep83661652 correct=[0]` flipping
**`OK rank 1/8` → `MISS rank 5/8`** as its score fell `976.42 → −439.20`. The lab is therefore
demonstrably sensitive to the exact function this issue modifies.

**Exposure — why it nonetheless moved nothing.** Swept all 372 corpus frames for card ids, resolving
each occurrence to the zone it sits in:

| card | frames carrying the id | attached to a BENCH body | attached to an **ACTIVE** |
|---|---|---|---|
| 1175 Brave Bangle | 19 | 3 | **0** |
| 1171 Hop's Choice Band | 4 | 0 | **1** |
| 1158 Maximum Belt | 35 | 0 | 0 |
| 678 Mega Lucario ex *(positive control)* | 140 | — | — |
| 1031 Mega Starmie ex *(positive control)* | 256 | — | — |

`_SideBase.damage_boosts` reads `active.tool_ids` and nothing else — a boost Tool on the Bench
contributes zero by design, since only the Active attacks. Brave Bangle is attached to an Active in
**no frame of the corpus**, so the change has no frame to move. The Hop's Choice Band row is the
positive control *for this sweep specifically*: the same detector DOES find a boost Tool on an Active
when one exists, so its zero for 1175 is a fact about the corpus, not a silent instrument. (The first
version of this sweep returned 0 for **every** card including Mega Lucario ex — it globbed `*.json`
where the corpus is `corrections.jsonl`. That is the control doing its job.)

The corpus holds no `slowking` batch at all (54 `dragapult_ex`, 70 `mega_lucario`, 207
`mega_starmie`, 41 unlabelled), and `slowking` is the only deck that ships the card — 1 copy,
`src/agents/slowking/deck.csv` line 48. The 19 hits are the opponent's deck list and three benched
copies.

## What the SELF-FILED spec got wrong

Issue #345 was filed minutes earlier by Issue #282's own implementer. Its central claim held: 1175
parses to `damageBoost=0`, `CardStat` had no field for a Rule-Box gate, and `holderNameFamily` really
is an owner-NAME family. Its framing did not, and three further claims were corrected during the
build or by review.

1. **It presents the zero as an unnoticed gap.** The tree calls it a RULING.
   `tests/scouting/test_tool_holder_facts.py` shipped a dedicated test,
   `test_a_RULE_BOX_GATED_boost_still_parses_to_zero`, whose docstring reads *"Deliberately
   unmodelled"*, and the census generator hard-coded 1175 into `DELIBERATELY_UNMODELLED_TOOLS`. The
   issue cited neither, quoting only the inventory test.
2. **The ruling's REASON is what fails**, and it is why the ruling is overturned rather than merely
   revisited: *"`CardStat` models `ex`/`megaEx` but not Radiant, so a no-Rule-Box test would fail
   OPEN and over-credit."* That is a claim about the pool that was never measured against it. The
   `Rule` column of `data/EN_Card_Data.csv` takes exactly four values over 1267 ids — `n/a` 1087,
   `Pokémon ex` 121, `Mega Pokémon ex` 30, `ACE SPEC` 29 — with no Radiant, V, VMAX, VSTAR or
   V-UNION anywhere, and its Rule-Box body set has **empty symmetric difference** with the engine's
   `is_ex_body` (151 bodies). Exact, not fail-open. All 29 ACE SPEC cards are Trainers or Energy, so
   none is ever a holder.
3. **The refusal was also inconsistent with the tree**, which already reads the identical predicate
   the identical way twice: `fetch_closure._pokemon_body_matches` (`no_rule_box`, for Poké Pad and
   Lana's Aid) and `cgpy.chain._card_matches` (`noRuleBox`) — the engine twin's own answer.
4. **Its quotation of the card is incomplete**, dropping the trailing *"(Pokémon {ex}, Pokémon {V},
   etc. have Rule Boxes.)"* — the card naming the very Rule-Box categories the risk is about.
5. **It says there are "two consumers" of the gate. There are four**: `_SideBase.damage_boosts`,
   `Pilot._boost_lethal_tactical`, `doctrine_tool._tool_reaches` and
   `planner._gamble_pump_ko_classes`. All four inherit the second gate untouched, which is the design
   working — but the docstring asserting the count was itself wrong until review caught it.

The attached-Tools ruled omission (Issue #278's ledger → Issue #260) is **not** re-litigated:
`snapshot_coverage` already homes `Zone("attached_tools", …, HOMED, home="mine.active.tool_ids")` and
Issue #282 homed `this_turn_damage_boosts`. This change is a parse strictly upstream of that
plumbing, and `state_model.py` / `state_value.py` / `combat.py` / `snapshot_coverage.py` are all
absent from the diff.

## What `/code-review` changed

The Spec axis re-derived the load-bearing claim with an instrument this build never used — the CSV's
own `Rule` column rather than a card-name regex — and **confirmed** it, so the overturn stands. It
then found that `fetch_closure._body_predicates_match`, cited four times as the prior art for that
overturn, **does not exist**; the function is `_pokemon_body_matches`. The name had been inferred
from the function's docstring rather than read off its `def` line — the Issue #319 failure mode,
caught. All four citations are fixed. It also corrected a "four other Rule-Box texts" comment that
then listed five.

The Standards axis proved one new test **vacuous**:
`test_the_amount_and_the_RULE_BOX_gate_cannot_be_read_apart` claimed to assert the shared-prefix
guarantee and only round-tripped texts that satisfy both legs by construction, so it stayed GREEN
under exactly the drift it names. It now asserts the property on the patterns themselves and goes red
under that mutation. It further showed that the negative case's coin-gated leg parsed to 0 only by a
capitalisation accident — `_BOOST_TOOL_RE`, shipped byte-compatible at Issue #306, has **no coin
guard at all**, and *"Flip a coin. If heads, Attacks used by the Pokémon this card is attached to do
30 more damage …"* parses to 30 today. That is latent (no card in the pool prints the shape) and
belongs to a different sentence form, so it is **recorded in the test's docstring rather than fixed
here** — a developer may wish to rule on it.

## One follow-on filed

**Issue #346** — Brave Bangle's `{ex}` DEFENDER gate is missing from its `cgpy` ChainDef.
`chain_overrides.json` has `{"tool": {"attackBonus": {"n": 30, "holder": {"noRuleBox": true}}}}` with
no `"defenderEx": true`, so `cgpy/damage.py` adds the +30 against **every** defending Active while
the card restricts it to a Pokémon `{ex}`. Swept the whole `tool.attackBonus` inventory: three cards
carry one, and the other two agree with their printed text in both directions (1158 Maximum Belt
`{ex}`/True, 1171 Hop's Choice Band no-`{ex}`/False) — that agreement is the sweep's positive
control, and it makes 1175 a defect rather than a convention the file does not follow. Not built
inline: `cgpy` is the offline simulator the leaf gate runs on (`leaf_lab._cgpy_pilot_builder` sets
`pilot._search_api = cgpy_api`), so bundling a damage change there would make any future flip
unattributable. Queued immediately after Issue #345; nothing later depends on it.

---

# Issue #346 — Brave Bangle's `{ex}` defender gate in the cgpy twin

## Flips

**Zero on both gates.** Leaf: `1 unruled` — still `81906755|1|decision|9`, carried from Issue #280
and already ruled above; the pre-change and post-change reports are **byte-identical** (198 gated,
67 held out, 3 voided in both). Decision Gate: **PASS, 0 picks moved, 0 rulings moved**, `agree
250/347 -> 250/347`, also byte-identical. No row is added to the Flips table.

## Read this one differently: the change is to the MEASURING INSTRUMENT, not the measured code

Every other sub-issue in this run changed scoring code and asked the leaf lab whether the *decision*
moved. This one changes `src/cgpy/defs/chain_overrides.json` — a card definition inside **cgpy**,
which `leaf_lab._cgpy_pilot_builder` installs as `pilot._search_api`. cgpy *is* the rollout simulator
the Discrimination Gate runs on. So a flip here would not mean "the agent now prefers a different
option"; it would mean "the ruler changed length". A zero is therefore the *expected and desired*
result, and the interesting question is not "did it move" but "**could** it have moved" — which is
what the controls below answer.

## The zero is EXPLAINED, and the explanation is measured rather than inferred

Three layered controls, each pointed one step closer to the changed line.

| control | mutation | leaf gate |
|---|---|---|
| **C — is the host block reached?** | `dmg += 3000` unconditionally inside the same `if defender_is_active:` block that hosts the tool loop, `cgpy/damage.py` | **MOVED**: `1 unruled, 67 ruled, 3 voided` → `21 unruled, 55 ruled, 5 voided` |
| **A — is the tool-loop payload reached?** | every attached-tool `attackBonus` inflated: `dmg += ab["n"] + 3000` | **no movement** |
| **B — is card 1175 reached?** | Brave Bangle's own `"n": 30` → `3000` | **no movement** |

Control C is the positive control proper: the leaf lab demonstrably executes the exact region of
`attack_damage` this issue's data feeds, and reports a 20-frame swing when it changes. A and B are
the explanation of the zero, and they are consistent with each other — the payload is never reached,
so no per-card value inside it can matter.

**Direct measurement rather than inference.** Instrumented the loop itself (counter installed,
one leaf pass, `git checkout` to revert):

```
tools_seen=281  bonus_reached=0  tool_ids=[1159, 1174]
```

The loop over `attacker.tools` runs **281 times** in a full pass, on exactly two distinct Tools —
**1159 Hero's Cape** (`{"tool": {"hpBonus": 100}}`) and **1174 Air Balloon**
(`{"tool": {"retreatBonus": -2}}`). Neither carries an `attackBonus`, so the `if not ab: continue`
fires every single time and the bonus payload executes **zero** times. No `attackBonus` Tool is ever
attached to an attacking Active anywhere in a leaf-lab rollout. **No** ChainDef edit to
`tool.attackBonus` — this one or any other — can move this gate today, which is a fact about the
corpus, not about the fix.

This composes with Issue #345's corpus sweep from the other side of the seam: Brave Bangle appears in
19 of 372 corpus frames, on a Bench in 3 and on an **Active in 0**. The Pilot never sees it on an
Active; the twin never sees any boost Tool on an attacker.

## The self-filed spec, independently re-verified

Issue #346 was filed minutes earlier by Issue #345's own implementer, from inside this same batch
run. Per `CLAUDE.md` a self-filed issue is the implementer's reading, not a spec, so every claim was
re-run at source before any edit. **All four load-bearing claims held** — the first time in this run
that a self-filed issue's central argument survived verification intact. One *supporting* claim did
not; it is claim 5 below and it does not change the decision.

1. **Card text (`data/EN_Card_Data.csv` id 1175).** Verbatim, including the parenthetical the issue
   quoted in full: *"If the Pokémon this card is attached to doesn't have a Rule Box, the attacks it
   uses do 30 more damage to your opponent's Active Pokémon {ex} (before applying Weakness and
   Resistance). (Pokémon {ex}, Pokémon {V}, etc. have Rule Boxes.)"* Two gates: holder = no Rule Box,
   defender = Active Pokémon `{ex}`. **Supported.**
2. **The ChainDef.** `src/cgpy/defs/chain_overrides.json` lines 1852-1862 carried
   `{"n": 30, "holder": {"noRuleBox": true}}` and no `defenderEx`. The issue quoted it compacted onto
   one line; the file is pretty-printed, so the quote is a paraphrase of the literal bytes but
   semantically exact. **Supported.**
3. **The schema key is live, not invented.** `src/cgpy/damage.py:185` reads
   `if ab.get("defenderEx") and not (dstat.ex or dstat.megaEx): continue`. The issue's ten-line quote
   matches lines 181-190 verbatim. So this really is a one-key data fix and not an unmodelled
   mechanism. **Supported.**
4. **The 3-Tool sweep, re-run.** Merging `generated_chains.json` under `chain_overrides.json` in
   `load_chain_defs`'s own order gives 2823 entries, of which exactly **three** carry a
   `tool.attackBonus`: 1158 Maximum Belt (`defenderEx` True, text prints `{ex}` True), 1171 Hop's
   Choice Band (False / False), 1175 Brave Bangle (**False / True**). Count and both agreement
   directions reproduce exactly. **Supported.**
5. **Dependencies — "Independent of Issue #345, which changes only `src/common/scouting/` and is
   already merged on PR #340."** **CONTRADICTED, in both clauses**, found by the Spec axis. PR #340
   is `open` and `merged: false`; Issue #345 is commit `4fb1bf0a`, the unmerged HEAD of this very
   branch. And Issue #345 did not change only `src/common/scouting/` — `git show --stat 4fb1bf0a`
   also lists `src/common/strategy/planner.py`, `tools/apply_seam_coverage.py` and
   `src/common/CONTEXT.md`. The *conclusion* survives on its own evidence — the two changes share no
   file, and neither reads the other's output — but the stated grounds for it were wrong, and the
   phrase "already merged" would have been read by a later agent as a fact about `main`. Nothing was
   built on this claim, so nothing changes; recorded because a self-filed issue's supporting claims
   are exactly what nobody re-checks.

**One thing the issue's sweep did not surface, found by widening it.** Sweeping all 209 pool cards
whose text contains *"more damage"* rather than only those with an `attackBonus` turns up a fourth
Tool printing the same `{ex}` clause: **1178 Light Ball** — *"Attacks used by the Pikachu {ex} this
card is attached to do 50 more damage to your opponent's Active Pokémon {ex}"*. It is **not** a
`defenderEx` mismatch: its def carries `"deferred": "tool passive unpinned"` (plus the raw `_seed`
text) and no `attackBonus` at all, so there is no flag to disagree with. `deferred` is the file's own
record of a known-unmodelled
chain (`chain.is_deferred`), no shipped deck runs the card, and the omission under-credits rather
than over-credits. **Recorded here and in the sweep test's docstring rather than filed** — same call
Issue #345 made on the missing coin guard. The turn-marker family (Kieran 1191, Black Belt's Training
1211) spells the same restriction under a *different* key, `defenderExOnly` (`damage.py:172`), and
both carry it correctly; Premium Power Pro 1141, whose text has no `{ex}`, correctly omits it. That
is a second, independent instance of the convention holding.

## Exposure

`slowking` runs 1× Brave Bangle (`src/agents/slowking/deck.csv` line 48) and is the only deck that
ships it. The over-credit was one-sided — it only ever ADDED 30 — so in a rollout it could turn a
non-lethal line lethal but never the reverse, which is precisely the phantom-KO class the Turn
Planner's soundness guard exists to distrust. The corpus holds no `slowking` batch, so nothing
measured today was affected; the fix is for the shipped agent, not for the lab.

## Rulebook check

`docs/rulebook.txt` L337: *"Mega Evolution Pokémon ex are considered to be Pokémon ex, so any card
effects that affect Pokémon ex also affect Mega Evolution Pokémon ex."* `damage.py` already tested
`(dstat.ex or dstat.megaEx)`, so the Mega leg needed no code change — but it was untested, and
`Mega Kangaskhan ex` (756, in `slowking`'s own deck) carries `megaEx` and **not** `ex`, so a gate
written against `ex` alone would silently exclude the 300-HP bodies the boost matters most against.
Now asserted, and the assertion goes red under exactly that mutation.

## What `/code-review` changed

**Standards** proved the sweep test **vacuous along the axis it advertised**. It had re-implemented
`chain.load_chain_defs`'s merge inline (`_merged_chain_defs`), justified by a docstring claiming the
local copy was needed "so the sweep sees the shipped files" — which is **false**: `load_chain_defs`
also reads those exact files from disk. Demonstrated by mutation: with `chain.load_chain_defs`
monkeypatched to `{}` the sweep stayed **green**. So the test named "wrong merge order" among the
failures its positive control would catch while being structurally incapable of catching it. It now
calls `load_chain_defs()` directly, and three mutations were re-run to prove the guard is live:
loader returns `{}` → **RED**; the merge inverted so `generated_chains.json` wins over
`chain_overrides.json` → **RED**; the card-text reader returning no rows → **RED**. That second one
is the drift that matters: it is the exact way the unflagged seed def could come back.

Standards also caught the CSV read being `last-row-wins` over a table where **723 of 1267 Card IDs
occupy more than one row** (one row per attack; 2022 rows total) — harmless for these three
single-row Trainers, latent for anything else — now accumulated per id. Its report said "1478 rows",
which re-measurement does not support: `csv.DictReader` yields **2022**. The 723 figure it named,
which is the one the fix rests on, does reproduce. And the `list[int] = ()` type lie on `make_state`'s
parameters, now `Sequence[int]` on both the new parameter and the pre-existing `defender_bench`
beside it.

**Spec** confirmed the load-bearing claim at source in both halves — the pre-change entry via
`git show HEAD:src/cgpy/defs/chain_overrides.json`, and `damage.py:185` as the *only* hook (the two
neighbouring `ex` reads, `:172` `defenderExOnly` on `turn_markers` and the defender-side
`preventDamageFromEx`, are different mechanisms). It reproduced the card text, the 3-Tool sweep in
both directions, and rulebook L337 independently. Its one finding is claim 5 above. It also noted
that its own first count of the "more damage" pool sweep came back 153 rather than 209 because of a
dict-dedup bug in its instrument — caught by re-running, which is the point of the rule.

---

# Issue #284 — standing chip on their bench is an asset

`_reachable_target_values` widened from their Active to `model.theirs.bodies`, with a damage route
per SEAT: the Active through Issue #281's `best_reachable_damage_vs`, the Bench through the new
`CombatMath.best_reachable_bench_damage` / `MySide.best_reachable_bench_damage` (the attack's
single-target snipe rider, same Attach-Budget affordability filter, fail-closed on a bench-immune or
unreadable body).

## Gate result — no new unruled flip, and the leaf moved the right way

Measured as an explicit before/after A/B against the **same committed baseline**, from HEAD
`07ebc5ef`: run the gate with the working tree clean, apply the change, run it again, diff the two
reports. Neither `data/leaf_lab/baseline.json` nor `data/decider_lab/baseline.json` was touched.

**Discrimination Gate** — unruled count **unchanged at 1**. That one is Issue #280's
`81906755|1|decision|9`, already tabled above; it is not this issue's.

| | before | after |
|---|---|---|
| leaf picks `correct` (SOLE top) | 32/249 (13%) | **33/249 (13%)** |
| shared-top | 130/249 (52%) | 131/249 (53%) |
| avg top-tie | 2.0 | 2.1 |
| gated on / ruled / voided | 198 / 67 / 3 | 200 / 65 / 3 |

Three frames changed their standing against the baseline, and all three are accounted for:

| frame | before | after | reading |
|---|---|---|---|
| `82229122\|0\|decision\|17` | `REGRESSED OK → MISS`, rank 1 → 2, `owner=#263` | **no longer regressed** — `OK`, rank 1/8 | a ruled regression this change RESOLVES |
| `82525101\|1\|decision\|69` | `REGRESSED OK → MISS`, rank 1 → 2, `owner=#263` | **no longer regressed** — `OK`, rank 1/5 | a ruled regression this change RESOLVES |
| `81903490\|0\|decision\|49` | `IMPROVED MISS → OK` | **no longer improved** — back to the baseline's `MISS` | a windfall improvement LOST. Not a regression *against the baseline*, which is why the unruled count did not move |

`ruled` falls 67 → 65 and `gated on` rises 198 → 200 because the two resolved frames leave the
held-out REGRESSED set and rejoin the gated population.

**Decision Gate — PASS, and the two reports are byte-identical.** `agree 250/347 -> 250/347`,
**0 picks moved, 0 rulings moved**, 24 voided. `diff` of the before/after reports is empty.

## The positive control — because a clean diff is not by itself a result

A cumulative baseline diff proves only *"no NEW unruled flip"*. It cannot show the changed path was
reached at all, and this batch has already burned four instruments that were silently blind. So the
bench leg was instrumented directly: `MySide.best_reachable_bench_damage` wrapped with a counter,
and every frame in the corrections corpus scored through the same `state_value` the leaf scores.

| | |
|---|---|
| corpus frames scored | **371** (0 errors) |
| frames with a non-empty opponent Bench | 319 |
| times the bench leg was **ASKED** | **904** |
| …returning a **non-zero** reach | **338** |
| frames where `threat` **moved** | **13** — all `mega_starmie`, every one `0.0 → 0.1` |

So the instrument reaches the changed path 904 times and the path is live 338 times. The
`0.0 → 0.1` shape of all 13 moves is itself the finding in **L2** below. Both runs of this control
were re-run after the review fixes and are byte-identical.

The same question was asked of the **tests**, since a test that passes with and without the code it
claims to cover is vacuous. Three mutations, applied in-process against the seven new cases:

| mutation | new tests failing |
|---|---|
| none (control) | 0 of 7 |
| the bench leg always returns `0.0` | **6 of 7** |
| the fail-CLOSED guard removed (immune / unreadable bodies credited) | **2 of 7** — exactly the two that assert it |
| the leg reads `_bench_rider` (snipe **+** spread) instead of `rider_snipe` | 0 of 7 |

The survivor under the first mutation is
`test_the_bench_rider_never_leaks_into_the_ACTIVE_reachability_read`, which asserts the rider does
**not** reach the Active — deleting the bench leg leaves it true by construction, which is the
intended asymmetry rather than a gap.

The last row is recorded because it is a **zero that means something**: the fixture boards cannot
discriminate the snipe-vs-spread decision, because the fixture's only bench route (Jetting Blow)
prints no spread. That decision is pinned one seam over instead, by the pool sweep
`test_no_attack_in_the_pool_prints_both_a_bench_SNIPE_and_a_bench_SPREAD`, whose own positive control
is that both inventories come back non-empty.

## L1 — two `owner=#263` rulings may now be retirable

`82229122|0|decision|17` and `82525101|1|decision|69` were both ruled regressions owned by
Issue #263, and both now pass. **Recommendation: KEEP both rulings, re-check at Issue #291's
closeout.** A ruling records a human's verdict about a frame, not a gate's current colour; a change
that happens to make the frame pass does not retire the verdict, and Issue #291 is the pass that
exists to reconcile exactly this.

## L2 — the family now SEES their bench and still cannot GRADE it

This is the ceiling on what Issue #284 could deliver, and it is worth stating plainly because the
issue's symptom is only half-cured.

`threat` is `min(_THREAT_CAP, sum)`, and its own `blind_to` already records the measurement: **the
cap binds on every non-empty input** (0.0 on 20 of Issue #262's 22 gating frames and exactly the cap
on 2, never a value between). So a second reachable body adds exactly **0**. The bench leg therefore
moves the scalar only where the ACTIVE leg reads nothing — which is precisely the shape the control
above measured: 338 live bench reaches, 13 frames moved, every one of them `0.0 → 0.1`.

A chipped bench under an already-reachable Active still scores identically to a fresh one. That is
the issue's own headline symptom surviving in the case where their Active is also reachable.

**Recommendation: no action inside this track.** The unlock is not more reachability — it is the
parked `_THREAT_CAP / _MAX_PRIZE_VALUE` scale anchor, which is already derived, already measured,
and deliberately not applied because applying it alone measured as a corpus regression (65 → 68
unruled, two `MISS → OK` improvements lost). Recorded in `threat.blind_to` as a named entry so the
next reader meets it as a measurement rather than as a surprise. If the wave wants the bench chip
graded rather than merely seen, the anchor and this widening should be measured **together**, which
is a calibration decision this track was told not to make.

## L3 — two defects in Issue #284's own spec, recorded for the epic's author

Neither changed what was built; both would have if followed literally.

**(a) The named instrument is the wrong one.** The issue says *"The instruments are
`CardStat.benchSnipeDamage` (`provider.py:79`) and `snipe_relevance.py`."*

`CardStat.benchSnipeDamage` is filled in `_build_cache` from `parse_attack_bench_snipe` **alone**,
while `AttackStat.benchSnipe` is filled from that parser **or** `build_attack_stats`'
`free_target_snipe` branch — the *"does N damage to 1 of your opponent's Pokémon"* phrasing. Verified
against the real pool:

| card | attack | `AttackStat.benchSnipe` | `CardStat.benchSnipeDamage` |
|---|---|---|---|
| Mega Starmie ex (1031) | Jetting Blow | 50 | **50** |
| Fezandipiti ex (140) | Cruel Arrow | 100 | **0** |
| Kyurem (144) | Trifrost | 110 | **0** |
| Zeraora (377) | Thunder Raid | 0 | 0 |

Cruel Arrow and Trifrost are the bench routes of `dragapult_ex` and `slowking` — two of the three
decks the issue names as exposed. **Built on the card-level field, the fix would have been inert on
both and live only on `mega_starmie`.** The read is `AttackStat.benchSnipe` through
`CombatMath.rider_snipe`; `tests/scouting/test_attack_riders.py` pins the difference against the
real 1556-record pool. The line reference is stale too — the field is at `provider.py:116`.

`snipe_relevance.py` is deliberately not called: `target_relevance` answers *should I aim this
turn's snipe here*, which is the CONVERSION decision the issue's own *"Respect the ruled boundary"*
section forbids this term from re-pricing, and its inputs are Pilot plumbing no `StateModel`
supplies. Recorded in `_reachable_target_values`' docstring.

**(b) Test 4 asks for something Issue #281 already delivered.** The issue asks for *"`dragapult_ex`
cross-turn shape: after a Phantom Dive, the follow-up gust-and-convert line outscores the same gust
on a fresh board."* After the gust the chipped body is **Active**, and the Active leg has read its
remaining HP since Issue #281 — so on the post-gust pair both boards are reachable and `threat` is
equal. The half this issue adds is the **pre**-gust one, while the body is still benched. The test
asserts both halves explicitly rather than substituting one for the other silently.

**Recommendation: accept as built.** Worth correcting in Issue #285 if it inherits the same
instrument pointer — its audit finding (F5) is the *valuation* half of the same family and the same
per-body loop.

## Scope boundary with Issue #263 — checked, not crossed

The epic's ruled ledger gives *"The Stadium · Their board topology · Ability readiness · Who is
Active"* to Issue #263. Widening `threat`'s TARGET set is not valuing their board topology, and the
registry already drew that line itself: `development.blind_to` says *"their board topology —
development is MY-side only … `threat` reads their bodies as targets, not as development."* This
change stays inside `threat`'s declared subject (`opponent_target_value` over reachable Knock Outs)
and adds no read of their line topology, their bench count, or their development. No ledger line is
disputed.

---

# Issue #285 — sniping a pre-evolution denies a forward payoff

`_reachable_target_values` priced a target by `prize_value` alone — what the body yields NOW — so
killing a Staryu scored exactly as much as killing any other 1-prize body, while the doctrine's whole
point is that it erases three. `prize_advance` now carries the forward payoff the removal DENIES:
`TheirSide.forward_payoff` (the mirror of `MySide.forward_payoff`) through
`state_value._denied_forward_payoff`, on `development.evolve_marginal`'s own expression
`_READINESS_W x (owed_damage / PRIZE_DAMAGE_RATE) x halve(hops)`. **No new constant.**

## Flips

**Zero on both gates, and both reports are BYTE-IDENTICAL to the pre-change tree.** Leaf: `1
unruled` — still `81906755|1|decision|9`, carried from Issue #280 and ruled at the top of this
packet; 65 ruled, 3 voided, 200 gated, unchanged. Decision Gate: **PASS, `agree 250/347 -> 250/347`,
0 picks moved, 0 rulings moved**, 24 voided. Neither baseline touched. No row is added to the Flips
table because this change produced none.

Measured as an explicit A/B from HEAD `35d25999`: run both gates with the change in the tree, `git
stash push -u`, run both again, `diff` the two reports. Both diffs are empty, over a 381-line leaf
report that prints every one of the 277 scored leaf rows at full float precision — so byte-identity
here is zero movement on every scored row, not an empty report.

## L1 — the fix is CORRECT and STRUCTURALLY INVISIBLE to both gates, and that is the headline

This is not a quiet zero to be reported and moved past. **The credit cannot move `state_value` on any
board, by arithmetic, and the reason is the cap Issue #284 already flagged — one step worse.**

`threat` is `min(_THREAT_CAP, sum)` with `_THREAT_CAP` **0.1**. Every value the loop appends is
`opponent_target_value(prize_advance >= 1.0, survival_shift=0, …)`, because `CombatMath.prize_value`
returns 1, 2 or 3 and never less. So the sum exceeds the cap by at least 10× the moment the loop
appends **anything**, while the largest credit measured anywhere on the corpus is **0.054 prizes** —
**Riolu (30) → Mega Lucario ex (270)**, owed 240: `0.045 x 240/100 x halve(1)`. The doctrine's own
headline line is *smaller*: Staryu (20) → Mega Starmie ex (210) is owed 190, i.e. **0.043**.

*(Corrected by `/code-review`: three places in the first draft attributed the 0.054 maximum to
Staryu and then showed working — `0.045 x 190/100 x halve(1)` — that evaluates to 0.043. Both halves
were wrong at once, which is why the number is now stated with its card and its arithmetic together.)*

Issue #284's L2 said the family *"now SEES their bench and still cannot GRADE it"*, and could still
point at 13 frames that moved `0.0 → 0.1` because widening the loop changes whether it is EMPTY.
Issue #285 changes only the VALUE of an entry that already exists, so it has no such escape: it
moves `threat` on **zero** frames and always will, until the anchor lands.

**Measured, not asserted** — `_denied_forward_payoff` instrumented over all 371 corrections-corpus
frames, each scored through the same `state_value` the leaf gate scores, with the credit severed
in-process for the B arm:

| | |
|---|---|
| corpus frames scored | **371** (0 errors) |
| `_denied_forward_payoff` **ASKED** | **270** — once per reachable target |
| …returning a **non-zero** credit | **110** |
| frames carrying ≥1 non-zero credit | **51** |
| frames where `_reachable_target_values` **MOVED** | **51** — 49 `mega_starmie`, 1 `dragapult_ex`, 1 `mega_lucario` |
| frames where **`threat`** moved | **0** |
| credit min / median / max | 0.0045 / 0.0180 / **0.0540** |

**Positive control C — can that harness see a `threat` move at all?** The identical A/B with the
*reachability* read severed instead (`MySide.best_reachable_damage_vs` and
`best_reachable_bench_damage` → 0.0, i.e. Issue #281's and Issue #284's own legs) moves
`_reachable_target_values` on **114** frames and `threat` on **114**. So the instrument is live and
the 0 above is a fact about `_THREAT_CAP`, not about the measurement. Without this control the two
numbers "0" and "my harness is blind" would have been indistinguishable — which is the failure this
batch has now hit five times.

**Recommendation: ACCEPT AS BUILT, and rule the anchor as one decision covering three issues.** The
valuation is right, it is exercised 270 times on the corpus and live on 110, and the seam it changes
(`_reachable_target_values`) is what Issue #263's composer consumes. What it cannot do is reach the
scalar, and no amount of further reachability or valuation work inside `threat` will change that. The
unlock is the parked `_THREAT_CAP / _MAX_PRIZE_VALUE` scale anchor — derived and measured in
`threat.blind_to`'s SATURATION entry, and deliberately not applied because applying it ALONE measured
as a corpus regression (65 → 68 unruled, two `MISS → OK` improvements lost). Those five regressing
frames were all *"winning by a margin SMALLER than the 0.067 prizes of threat advantage the
saturation handed them"* — which is exactly the windfall that Issue #284's widening and this issue's
credit both change. **The anchor should therefore be measured TOGETHER with both, not alone**, and
that is a calibration decision this track was told not to make.

## L2 — what the credit's SIZE says, before anyone fits the anchor

Worth putting next to the ruling above, because it is the number that will decide whether the anchor
alone is enough. With the anchor applied, a 1-prize target lands at 0.033 and a 3-prize target at
0.1. The largest denial credit measured is 0.054 **before** that rescaling, i.e. it would itself be
divided by `_MAX_PRIZE_VALUE` and land near 0.018 — still under the 0.033 step between prize tiers.

So under the derived anchor a Staryu still prices below a bare 2-prize body, which is arguably right
(a denied payoff is not a prize) and arguably not (the doctrine says *"trade 1 prize for a denied
3"*). The issue's own instruction — *"cross to prizes on the same anchors `development` uses; do not
introduce a new constant"* — is what fixes the scale here, and it is `_READINESS_W` 0.045, a
POSITIONAL band deliberately far below a prize. **If the developer wants the denial to compete with a
prize count, that is a different constant and a separate ruling; this build declined to invent one.**

**And the currency is DAMAGE, not prizes — which is the sharper half of the same point.** The credit
reads `owed_damage` alone, so a pre-evolution whose forward form is a 3-prize Mega ex and one whose
forward form is a 1-prize body of the same printed damage price **identically**. The doctrine's
sentence is *"trade 1 prize for a denied 3"* and it is about PRIZES; this term answers in damage.
That is not an oversight — `ForwardPayoff` carries no prize leg and `development.evolve_marginal`
prices its my-side mirror the same way, so adding one on the opponent side alone would give the same
card two valuation bases. It is now named in `threat.blind_to` rather than left implied, and it is a
second reason the anchor ruling should be taken as one decision rather than piecemeal.

## L3 — the audit's named instrument is incomplete, and the missing half needed an extraction

Issue #285's spec is **not** a repeat of Issue #284's wrong-instrument defect: every instrument it
names is real and was verified at HEAD — `MySide.forward_payoff` / `ForwardPayoff`
(`state_model.py`), `grading.halve`, `development.evolve_marginal`, `EvolveBody.p_arrive`
(`evolve_value.py`), and `TheirSide._forward_ids`, which really is threaded into `turns_to_afford`
(`state_model.py`, `forward_ids=self._forward_ids`). Its central claim also holds: no `blind_to`
entry anywhere names the VALUE of a denied forward payoff, only the reachability of a benched body.

One capability claim is nonetheless misleading, and it changed what had to be built. The issue says
*"`owed_damage` / `hops` — computable. The forward index is already threaded on `TheirSide`"*, and
the audit's F5 says the fix *"reuses the shipped forward index … no new oracle"*. **The forward index
carries no hops.** `_ForwardIndex.forward_card_ids` returns a FLAT frozenset over
`_descendant_names`, whose whole job is to discard depth. The only shipped depth walk is the
`evolvesFrom` name-chain inside `CombatMath.turns_to_afford`, which folds it into a `max` with the
energy leg and exposes neither. And that `max` is the DEEPEST form, while a forward payoff needs the
hops to the best-DAMAGE form — a different aggregation over the same walk.

So the build extracted `CombatMath._forward_hop_depths` (`{form name: depth}`) and gave
`turns_to_afford` the `max` of its values, leaving that oracle's result byte-identical, then added
`CombatMath.forward_payoff_terms` as the caller-facing `(owed_damage, hops)` read. Re-deriving the
walk in `state_model` would have left two copies of a depth rule free to drift — the failure
`card_level_damage` was extracted to end, in the same file.

Stale line references, recorded for the epic's author but pre-excused by its own *"re-locate by
function name"* instruction: `needs.py:253` for `opponent_target_value` is `:318`, and
`state_model.py:852` for `MySide.forward_payoff` is `:1322`.

## The two legs that could not be mirrored, and why both fail OPEN

`MySide.forward_payoff` returns three legs. Two are card knowledge and mirror cleanly; the third is
not, and the direction it degrades in is a decision rather than an accident.

| leg | my side | their side |
|---|---|---|
| `owed_damage` | best printed damage in the forward closure minus own | same, via `forward_payoff_terms` |
| `hops` | BFS depth over my DECKLIST's children map | `evolvesFrom` name-chain depth over the POOL closure |
| `reachable` | `unseen_counts` + `hand_ids` — provable | **hardcoded True** |

Their deck is untracked and their hand is a COUNT (`TheirSide.hand_size`), so *"is a copy of that
form still gettable"* has no sound answer. It fails OPEN because the alternative — claiming their
line is dead — would cancel a denial credit against a threat that is perfectly real, and
`development.line_topology` only gets to CANCEL on my side because my side can prove it. The same
asymmetry makes the pool-level index deck-agnostic: a Staryu on their board carries the Mega Starmie
ex credit whether or not they run one. Both over-reads are named in `threat.blind_to`. The eventual
narrowing supplier is the archetype Read, which is a matched-Brief probability rather than a
decklist; consuming it here would give this family a second opinion about the Read, which the
sole-supplier ruling forbids.

Two further blind spots are recorded there rather than fixed: the credit reads printed `maxDamage`
(so denying an Abra credits almost nothing — Alakazam's threat is a scaling term), and it prices what
the line OWES without asking whether they can actually evolve it (the evolution card in hand, a Rare
Candy, the played-this-turn gate). The printed read is deliberate: `forward_threat_ceiling` is the
board-priced instrument, and using it on one side only would give the same card two valuation bases
while using it on both would retune `development.evolve_marginal`, which ADR-0070 rules.

## Scope boundary with Issue #263 — checked, and it is a closer call than Issue #284's

The epic's ledger routes *"their board topology"* to Issue #263, and this credit is derived from
their evolution line. The reason it is nonetheless in scope, stated explicitly so a developer can
overrule it:

* What `development.blind_to` rules out is **valuing their development as a positional term** —
  *"their bench filling up, or their line completing, moves nothing here"* — and the same entry says
  in the next clause that *"`threat` reads their bodies as targets"*. This prices one target more
  precisely; it adds no positional term about their board.
* Nothing here reads their BOARD. The credit is card knowledge about one body — its `evolvesFrom`
  chain and printed damage — which is the same class of fact `prize_value` already is, off the same
  `CardStat`. Their bench count, their development, their hand and their deck are all still unread.
* The audit says so itself, at F10's ledger row: *"**Their board topology** … Accepted POC asymmetry
  — but see **F5**, which is the *valuation* half and is **not** ruled."* F5 is this issue.

## Tests, and whether they are worth anything

Seven new cases in `tests/strategy/test_state_value.py`, mutation-checked in-process:

| mutation | new cases failing |
|---|---|
| none (control) | 0 of 7 |
| the denial credit always returns 0.0 | **5 of 7** |
| the hop discount `halve(hops)` removed | **1 of 7** — the two-hop case, exactly the claim it isolates |
| `TheirSide` reachability fails CLOSED instead of open | **1 of 7** — exactly the case that asserts it |
| the hop walk returns depth 1 for every form | **2 of 7** — the extraction's two consumers |
| the `hops > 0 and owed > 0` guard removed | **0 of 7** |

The two survivors of the first mutation are the hop-count assertions (they assert `hops`, not the
credit) and the best-form case (it asserts the credit is 0, which severing preserves) — both intended.

**The last row is a zero that is recorded rather than glossed.** Deleting that guard changes no
result, because `forward_payoff_terms` returns `(0.0, 0)` for both conditions together and
`_READINESS_W x 0 x halve(0)` is already 0. It is kept because the coupling is a property of that
oracle's current shape rather than an invariant — a future reading that returned owed damage at 0
hops would be priced UNDISCOUNTED, since `halve(0)` is 1.0 — and `_development_legs` carries the same
guard for the same reason. The docstring says so, so the guard does not read as tested.

The hop-discount case is a pair that INVERTS without the discount, which is why it is the test and a
same-owed pair would not be: **Dreepy** is two hops from Dragapult ex and owed **160**, **Drakloak**
is one hop and owed **130**, so undiscounted Dreepy prices ABOVE Drakloak and only `halve(hops)` can
reverse it. A same-owed pair passes under any monotone discount, including one applied to the wrong
quantity.

Card facts verified at `data/EN_Card_Data.csv` and asserted by number rather than left implied —
Staryu (1030) → Mega Starmie ex (1031) is **one** hop with no "Starmie" in this set, Riolu (677) →
Mega Lucario ex (678) is **one** with no "Lucario", and Dreepy (119) → Drakloak (120) → Dragapult ex
(121) is a genuine **two**. `test_the_hop_counts_are_THIS_SETS_and_a_mainline_chain_would_fail_here`
is the executable form of the issue's own last test, and the two-hop line is what stops it being a
test that everything is one hop.

`test_the_denial_credit_is_INVISIBLE_once_the_cap_binds` asserts L1 above as a test: the seam
discriminates the two boards, `threat` reads exactly `_THREAT_CAP` on both. It turns red the day the
anchor lands, which is where the packet line will be wanted.
