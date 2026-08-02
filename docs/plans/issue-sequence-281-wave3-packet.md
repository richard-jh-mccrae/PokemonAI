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
