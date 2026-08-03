# Wave-3 packet — issue-sequence run (281, 280, 282, 284, 285, 286)

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
