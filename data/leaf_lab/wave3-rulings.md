# Wave-3 ruling record — the POC-T3 leaf swap (Issue #262)

The developer's per-frame verdicts on the wave-3 packet
([Issue #262 comment](https://github.com/richard-jh-mccrae/PokemonAI/issues/262#issuecomment-5152637450)),
recorded here because most of them change **nothing on disk**: a `REVERT` leaves the recorded label
standing, needs no ledger entry, and shows up only as the Discrimination Gate staying red on that
frame. Without this file the gate's red state has no name attached to it, which is the one thing
`CLAUDE.md` says a ruling record exists to prevent.

This is a **record, not an instrument**. Nothing reads it. `data/leaf_lab/baseline.json` is still the
gate's reference and is still untouched.

**It has a second consumer, by the developer's intent (2026-08-02):** the rationales are being
written as *ideal turn sequences* so these corrections can be checked against the **Turn Planner**
(Issue #263, POC-T4) once it exists. That makes the sequences an acceptance corpus, not commentary —
so they are reproduced **verbatim** below, typos and all, rather than paraphrased into the verdict
table. A sequence rewritten in my words is a sequence T4 would be graded against having already been
interpreted once.

## Verdict vocabulary

| verdict | what the developer said | what it changes |
|---|---|---|
| `REVERT` | my recorded pick stands; the new T3 leaf is wrong | nothing — the frame keeps failing the gate |
| `REFUTED` | my recorded pick was wrong too | `reviewed.json` gains a `refuted` entry; the frame stops grading |
| `UN-VOID` | a standing refutation of my pick is withdrawn | that `reviewed.json` entry is removed; the frame re-enters gating |
| `CONFORM` | the new leaf's pick is right; absorb it | the baseline re-captures that row |

## Verdicts

### Batch 1 (2026-08-02, commit `97c3d76`)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `81785223\|0\|decision\|32` | CONFORM | **REFUTED** | Pokégear is not the play with nearly every Supporter already in hand — evolve Staryu → Mega Starmie ex, Hilda for Energy, attach to the Active, Jetting Blow |
| `81785223\|0\|decision\|44` | CONFORM | **REFUTED** | as 32 |
| `81904064\|0\|decision\|44` | REVERT-worthy † | **REVERT** | Lillie's stands; retreating is absurd with the opponent's Active on no Energy and three Energy up off Ignition — Nebula Beam |
| `81904064\|0\|decision\|59` | REVERT-worthy † | **REVERT** | Salvatore stands; evolve the benched Staryu and Jetting Blow for the Knock Out |
| `81904451\|0\|decision\|24` | CONFORM | **REVERT** | Hilda stands — fetch Starmie, evolve, then attack |
| `81904451\|0\|decision\|37` | CONFORM | **REVERT** + UN-VOID | as 24 |
| `81904451\|0\|decision\|50` | REVERT-worthy † | **REVERT** | as 24 |
| `81904451\|0\|decision\|53` | CONFORM | **REVERT** + UN-VOID | as 24, with a Mega Signal in hand |

### Batch 2 (2026-08-02, commit `fab1fb0`)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `81905522\|0\|decision\|28` | CONFORM | **REVERT** | evolve the active Staryu, Lillie's, attach, Knock Out the Active and snipe Riolu |
| `81905522\|0\|decision\|64` | CONFORM | **REVERT** + UN-VOID | attach to Staryu first; Mega Lucario ex is out of one-shot range, so gust up Hariyama (no Energy) and Jetting Blow it, sniping Lucario into Nebula Beam range |
| `81906131\|1\|decision\|25` | CONFORM | **REVERT** | Buddy-Buddy Poffin is vital BEFORE attacking with Turbo Flare |
| `81906755\|1\|decision\|93` | CONFORM (low conf.) | **REVERT** + UN-VOID | attach to the active Starmie before attacking, Salvatore to evolve a benched Staryu, attack and snipe Raging Bolt ex |

### Batch 3 (2026-08-02)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `82225138\|0\|decision\|82` | REVERT-worthy † | **REVERT** | Buddy-Buddy Poffin, then Pokégear, re-decide on the new information (Hilda to fetch Energy for Staryu, or Salvatore to evolve it), then Nebula Beam |
| `82225643\|1\|decision\|57` | REVERT-worthy † | **REVERT** | Items should be used before attacking when they help — with no mainline attacker to replace the Active, Ultra Ball finds a Staryu to evolve next turn, and Hero's Cape gives the mainline attacker more HP |
| `82227388\|0\|decision\|43` | REVERT-worthy † | **REVERT** | the Active is doomed but we have healing — Wally's Compassion, attach Ignition Energy, Nebula Beam |
| `82227388\|0\|decision\|50` | REVERT-worthy † | **REVERT** | as 43: doomed, so heal, then sequence before attaching Ignition Energy and attacking with Nebula Beam |
| `82228017\|0\|decision\|16` | CONFORM | **REVERT** | Cinderace's Turbo Flare gives 3 Energy to Benched Pokémon, so lay down a bench at any cost while it is empty before attacking — Buddy-Buddy Poffin first |

### Batch 4 (2026-08-02)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `82228017\|0\|decision\|4` | CONFORM (low conf.) | **REVERT** | the leaf's Hero's Cape is a card with no value to the game right now that is better kept as Ultra Ball fodder — play Buddy-Buddy Poffin, attach to Cinderace, attack Turbo Flare |
| `82229122\|0\|decision\|17` | CONFORM | **REVERT** | too eager to attack: the turn could have filled the Bench with Buddy-Buddy Poffin AND attached Energy AND evolved Staryu to the main attacker |

### Batch 5 (2026-08-02)

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `82229122\|0\|decision\|33` | CONFORM | **CONFORM** | "Play Crushing Hammer against the benched Crustle is a fine move." |
| `82522698\|1\|decision\|36` | REVERT-worthy † | **REVERT** | attach Energy first, before shuffling the hand away or attacking |
| `82522698\|1\|decision\|62` | REVERT-worthy † | **REVERT** | a lethal decider — the Knock Out to win the match is available, take it and do nothing unnecessary |
| `82522726\|1\|decision\|7` | CONFORM | **REVERT** | attach Energy to the **active** Staryu |

**`82229122|0|decision|33` is the first CONFORM in 23 frames**, and it holds up at source: Crustle's
Ability *"Prevent all damage done to this Pokémon by attacks from your opponent's Pokémon {ex}"*
means an ex attacker cannot damage it at all, so stripping its Energy with Crushing Hammer is a real
line — and the Correction's own recorded rationale, *"play useful cards in hand first before
attacking"*, is satisfied by it. It cannot be absorbed on its own: `capture` is all-or-nothing and
refuses while any fail-direction frame is unruled, so this row waits with the rest.

**`82522726|1|decision|7` is a correction to the developer's own read.** The ruling was given as
*"as correction states and what it seems you do"* — but the leaf does **not** do that. The frame
offers the same Basic {W} Energy onto three different Staryu (ACTIVE, BENCH0, BENCH1); the leaf ranks
the **bench** attach first and the ruled ACTIVE attach 3rd of 5. Recorded as REVERT.

**`82522698|1|decision|62` is the most serious frame ruled so far.** Category `missed_win`, recorded
rationale *"When the choice is present to win the game, always take that choice immediately"* — and
the leaf plays **Harlequin** (a Supporter that shuffles both hands into their decks) instead of the
match-winning Knock Out. A prize outbid by a positional term is exactly what the `ko-score-band`
sound-rule entry forbids, so this is a rule breach and not a preference.

### Batch 6 (2026-08-02) — the first nine of the triaged 17

| frame | verdict | developer's line |
|---|---|---|
| `82866415\|0\|decision\|43` | **REVERT** | don't attach the Cape to a benched pre-evolution when our wincon is Active and energized |
| `82867148\|0\|decision\|62` | **CONFORM** | "leak plays buddy buddy and doesnt retrat. good!" |
| `85163634\|1\|decision\|17` | **REVERT** | don't play Lillie's — we want the Crushing Hammer and Ultra Ball next turn |
| `83007714\|1\|decision\|8` | **REVERT** | just end the turn |
| `83054602\|1\|decision\|32` | **REVERT** | Jetting Blow cannot hurt the Crustle, there is nothing to snipe, and we are not doomed — just end the turn |
| `83457493\|1\|decision\|33` | **CONFORM** | Buddy-Buddy Poffin is worthless here (all three Staryu/Starmie are already out), but playing both to THIN the deck is a good idea — then Harlequin |
| `85046350\|0\|decision\|21` | **REVERT** | attach to the active Dreepy so it can retreat to Budew, evolve Dreepy to Drakloak, Recon Directive, re-decide; don't play Ultra Ball; attack Itchy Pollen |
| `82525101\|1\|decision\|69` | **REVERT** | attach to the active Starmie even though it is doomed, so it can Jetting Blow and snipe the other Lucario — sometimes accepting the Knock Out is the aggressive line; Harlequin before attacking |
| `82750161\|1\|decision\|60` | **REVERT** | Buddy-Buddy Poffin does nothing for us — attack with Jetting Blow |

**Two CONFORMs, the first that turn on the leaf being RIGHT rather than on a mis-tag.** Neither can
be absorbed on its own: `capture` is all-or-nothing and refuses while any fail-direction frame is
unruled, so both wait with `82229122|33` from batch 5.

`83457493|33` is the more interesting of the two — the leaf's Buddy-Buddy Poffin is endorsed for a
reason the recorded rationale never mentions (**deck thinning**, not bench-filling), against a board
where its stated purpose is already satisfied. No term in the registry prices deck thinning; it is
now named in `blind_to` rather than left as a silent zero.

**`82866415|43` resolves the contradiction the triage flagged, and it resolves into a RULE**, not a
coin-flip between two rulings: *don't attach the Cape to a benched pre-evolution when our wincon is
Active and energized.* That is consistent with f48 five frames later (*"attached to the benched
Staryu … to protect it from Jetting Blow"*) because the boards differ — on f43 the wincon is the
Active Mega Starmie ex at 280/330 with three Energy, on f48 it is not. The Cape's target is
**conditional on where the wincon is**, which is a fact `state_value` has no term for today.

### Card facts, verified at source for this batch

- **Dreepy** is a Basic with **retreat 1**, so the attach in `85046350|21` *is* the retreat cost —
  the line is exact, not approximate. **Budew** is a Basic, 30 HP, whose **Itchy Pollen** costs *no*
  Energy for 10 damage and *"During your opponent's next turn, they can't play any Item cards from
  their hand."* **Recon Directive** is **Drakloak's Ability** (look at the top 2, put 1 into hand),
  not an attack — so "play Recon Directive, redecide" is an evolve-then-Ability line.
- **Crustle**'s Ability is *"Prevent all damage done to this Pokémon by attacks from your opponent's
  Pokémon {ex}"*, which is exactly why `83054602|32` says Jetting Blow cannot hurt it: Mega Starmie
  ex is an ex.

**A second mid-turn re-plan appears here.** `85046350|21`'s *"Play Recon Directive, redecide"* is the
same shape as `82225138|82`'s *"redecide on new info"* — the plan branches on what the Ability
reveals. Two independent instances now, both pointing at
[ADR-0095](../../docs/adr/0095-information-precedes-commitment.md) and both unrepresentable by a turn
plan fixed at the start of the turn. Recorded for Issue #263.

### Batch 7 (2026-08-02) — the last eight of the triaged 17. **All REVERT.**

| frame | verdict | developer's line |
|---|---|---|
| `82752604\|0\|decision\|16` | **REVERT** | just attack, as the rationale says |
| `83037962\|0\|decision\|49` | **REVERT** | just attack, as the rationale says |
| `83038055\|0\|decision\|51` | **REVERT** | the hand is strong, so don't shuffle it away — attack with Nebula Beam |
| `83053965\|1\|decision\|6` | **REVERT** | play Mega Signal |
| `83456015\|0\|decision\|38` | **REVERT** | attack with Nebula Beam for the Knock Out |
| `83966968\|0\|decision\|45` | **REVERT** | play Harlequin first, before attacking |
| `86089638\|0\|decision\|18` | **REVERT** | energize Dreepy with the {P} Energy |
| `86090164\|1\|turn\|2` | **REVERT** | attach to the active Dreepy, retreat to Budew, do NOT play Lillie's this turn, because we want to evolve our Dunsparce next turn |

**`86090164|1|turn|2` was never missing a rationale — my scan sheet was.** It reached the developer's
triage list labelled *"no rationale is recorded"* and flagged as the one frame that could not be
triaged from the corpus. Both claims were wrong, and the fault was `wave_scan.py`'s:

- The record is **turn-scoped**, so its intent lives in `turn_plan` (`intended_line` +
  `expected_end_board`), and its `rationale` field is empty by construction. The generator read only
  `rationale`. Fixed by `wave_scan.intent_of`, which reads the intent from wherever the scope records
  it; measured after the fix, **4 of 372** corpus corrections have no recoverable intent, and none of
  them is in this wave.
- `frame_view 86090164-2` failing is not a broken frame either. **2 is the TURN number**, not a frame
  — the record's Anchor is `86090164-17`, which renders fine and shows exactly this decision. That is
  the anchor-vs-key trap ADR-0090 was built for, and `frame_view`'s own error already prints the
  resolvable frames (which is where the developer's list came from).

A blank that reads as *"the human never said"* is the worst failure available to a sheet whose whole
job is relaying what they said, so it is recorded here rather than quietly patched.

**A third instance of the same Dragapult line.** `86090164|turn|2`'s plan — attach to the active
Dreepy so it can retreat to Budew — is the same shape as `85046350|21`'s. Budew's **Itchy Pollen**
costs no Energy and stops the opponent playing Item cards next turn, and Dreepy's retreat is 1, so
the attach IS the retreat cost. Three independent rulings now describe this line; it is doctrine, not
a one-off read.

† one of the 15 the developer deferred to Issue #278 S13
([comment](https://github.com/richard-jh-mccrae/PokemonAI/issues/262#issuecomment-5153527951)); the
per-frame verdict supersedes that deferral.

## ⚠️ What the flips do NOT mean — measured 2026-08-02

Prompted by the developer's question: *"we did already agree that the Lethal Solver shall remain
intact as it is today in the turn planner. so are you talking about something in addition?"* The
answer was no, and checking it overturned a conclusion this record previously drew.

**The Lethal Solver is the Turn Planner's TOP rung**
([ADR-0037](../../docs/adr/0037-lethal-solver-is-the-turn-planners-top-rung.md)), so it decides a
lethal frame before the develop rung's leaf ranks anything. On all three `missed_win` frames the
live pilot picks **exactly** the ruled option — `82522698|62` → `[15]`, `82523164|75` → `[8]`,
`82524455|55` → `[1]`. The leaf ranking the winning line 16th, 11th and 3rd never reaches a decision.

Cross-tabulating **every** flip against `data/decider_lab/baseline.json` (valid as the current
build's live decisions, because the Decision Gate passes with 0 picks moved), honouring the recorded
option-equivalence classes:

| | count |
|---|---|
| flips where the **live pick is still the ruled option** — the leaf flip is inert | **50** |
| flips where the live pick differs from the ruling | 23 |

So **the T3 swap is decision-neutral on this corpus.** The 23 were already live disagreements before
T3 and are unchanged by it; the other 50 are frames a higher rung owns.

**This does not make the flips harmless, and it must not be read as "the leaf is fine."** The
developer has ruled 22 of 23 examined frames as REVERT: the leaf's *isolated ranking* is genuinely
worse. It does not bite today because the develop rung rarely decides these frames — but Issue #263
(T4) hands the planner exactly these families, at which point this ranking becomes the live decision.
The Discrimination Gate is a **leading indicator for T4**, not a measure of today's play. That is why
it is worth taking seriously and why it should not be silenced.

**A win terminal in `state_value` was proposed and is WITHDRAWN.** The reasoning was that a won board
prices only as a prize lead (measured: a match win at exactly `4 × KO_SCORE` losing to Harlequin at
`4400.701`), so a positional term outbids a prize. The measurement is real, but the fix is not ours:
lethality is the Lethal Solver's fact, and a second authority deriving "this wins" is the duplication
[ADR-0096](../../docs/adr/0096-one-guard-per-fact-bench-carry-forward.md) exists to prevent. Recorded
as a known, bounded blind spot of the scalar instead.

## Why the remaining 50 are NOT being ruled one at a time

Asked by the developer at batch 5: *"So many of these frames' correction answer is right in their
rationale. must we really go through all of these?"* **No**, and three measurements say so:

1. **23 ruled, 22 not-conform.** The finding is already established — the T3 leaf regressed the
   develop corpus. The remaining frames are *evidence of a defect*, not decisions awaiting
   adjudication, and a 24th REVERT does not make the defect more true.
2. **A REVERT changes nothing on disk.** It leaves the recorded label standing; the frame simply
   keeps failing the gate. Only a CONFORM moves anything, because only a CONFORM re-captures a
   baseline row. So per-frame verdicts are worth the developer's time *only* where the answer might
   be CONFORM.
3. **The corpus already holds the answers.** Every `Correction` carries `rationale`,
   `correct_label`, `category` and `turn_plan`. Nothing needs retyping — `wave3-scan-sheet.md` is
   generated from the store and the live leaf, and the ideal turn sequences below can be extended
   the same way.

So the remaining 50 are listed in **`data/leaf_lab/wave3-scan-sheet.md`** with each frame's recorded
pick, recorded rationale, category, the leaf's actual new pick and the rank it gave the ruled option.
The default verdict is REVERT; the developer names only the CONFORMs.

**What the categories already say, over all 73 flips:**

| n | category |
|---|---|
| 36 | `sequencing_error` |
| 17 | `wasted_resource` |
| 7 | `misattachment` |
| 3 | `slow_setup` |
| 3 | `wrong_supporter` |
| 2 | `missed_win` |
| 1 each | `bad_target`, `bad_retreat`, `ignored_threat`, `missed_disruption`, `other` |

`sequencing_error` is half the corpus of flips on its own. That is the corpus's own label, assigned
long before this track existed, and it names the same gap the rationales keep describing.

## Triage of the 45 — which actually need the developer, and which do not

Asked after the sheet was regenerated: *"cant you read the rationale from the 45 frames and decide if
they really need additional context?"* Yes, and the split that survives is a **textual** one, not a
strategy judgement:

> **Does the recorded rationale address the action the leaf actually chose?**

That question is worth trusting because it is checkable. My strategy judgement on these frames is
not: the wave-3 packet recommended CONFORM on 15 and the developer overturned 14, so any triage
resting on *"I think the leaf's move is fine"* has a measured 1-in-15 hit rate and should not be
spending anyone's attention. What follows claims only that a rationale is SILENT, never that a
verdict is CONFORM.

**28 of 45 need nothing.** The rationale names the action the leaf took and condemns it
(`84071010|64` *"avoid attaching energy to lunatone"* → the leaf attaches to Lunatone;
`83967841|17` *"just save the ultra ball"* → the leaf plays Ultra Ball; `83037962|48`
*"placed second energy on active doomed mega starmie"* → the leaf does exactly that), or it
prescribes a first action that is not the leaf's. Those are REVERT by the developer's own words and
the default already covers them.

**17 need a look**, because the rationale condemns something the leaf did not do — most often it
condemns a shuffle or a spend and the leaf **retreats**, which the rationale never mentions:

| frame | the rationale condemns | the leaf actually picked |
|---|---|---|
| `82866415\|0\|decision\|43` | shuffling before attaching the Cape | **attaches the Cape**, to the benched Staryu |
| `82867148\|0\|decision\|62` | retreating Cinderace into a Staryu | Buddy-Buddy Poffin |
| `85163634\|1\|decision\|17` | fetching the Starmie a turn too early | Lillie's Determination |
| `83007714\|1\|decision\|8` | playing Ultra Ball at all | Retreat |
| `83054602\|1\|decision\|32` | attach-then-Wally's Compassion | Retreat |
| `83457493\|1\|decision\|33` | recycling Cinderace with Night Stretcher | Buddy-Buddy Poffin |
| `85046350\|0\|decision\|21` | powering up the Dunsparce line | Ultra Ball |
| `82525101\|1\|decision\|69` | attaching to a body that does not need it | attaches to a **different** Mega Starmie |
| `82750161\|1\|decision\|60` | Harlequin against an 11-card hand | Buddy-Buddy Poffin |
| `82752604\|0\|decision\|16` | shuffling with two Staryu benched | Retreat |
| `83037962\|0\|decision\|49` | the shuffle gamble giving back a Starmie | Retreat |
| `83038055\|0\|decision\|51` | shuffling back a strong hand | Retreat |
| `83053965\|1\|decision\|6` | first-turn Ignition Energy on the play | Retreat |
| `83456015\|0\|decision\|38` | gusting their 1-prize pre-evolution | Buddy-Buddy Poffin |
| `83966968\|0\|decision\|45` | — hedged: *"i think harlequin would have done well"* | Retreat |
| `86089638\|0\|decision\|18` | not powering the main line | Ultra Ball (which could fetch it) |
| `86090164\|1\|turn\|2` | — **no rationale recorded at all** | attaches to Dunsparce, not Dreepy |

`82866415|0|decision|43` is the strongest CONFORM candidate in the set, and it is worth reading
beside `82866415|0|decision|48` — the same episode, five frames later, where the developer writes
*"here it should be attached to the benched Staryu with a single energy as to protect it from Jetting
Blow."* That is what the leaf did on f43. The two rulings may simply disagree about the Cape's
target.

### Two findings from the read-through that are not verdicts

1. **`83053965|1|decision|6`'s rule claim is TRUE and hard**, verified at source rather than taken:
   Ignition Energy is a Special Energy that *"discard[s] it at the end of your turn"*
   (`data/EN_Card_Data.csv`), and the player going first **cannot attack on turn 1**
   (`docs/rules.md:72`, `docs/rulebook.txt` L152). So playing it turn-1-on-the-play burns the card
   for exactly zero — not a preference, a consequence of two rules. It is a **sound-rule candidate**
   (a legality-shaped constraint no weight should be able to outbid), which is a different kind of
   object from a wave verdict and is recorded here rather than smuggled into one.
2. **`82866415|0|decision|48` reports a defect, not a preference** — *"There is a clear bug with our
   ACE-SPEC Hero's Cape."* Left unruled and unexplained here; it wants its own investigation rather
   than a CONFORM/REVERT.

## Ideal turn sequences — VERBATIM (the Issue #263 / T4 acceptance corpus)

Reproduced exactly as the developer wrote them, including typos and abbreviations. Do not tidy
these: the whole point is that T4's turn plan is checked against the human's own words rather than
against someone's reading of them. Quoted blocks are the developer quoting the Correction's own
recorded rationale.

### INDEX — added 2026-08-04 by Issue #291's closeout. **Read this before grading against the list.**

41 entries, and they are not 41 gradeable turn plans. Issue #263 needs to know which is which before
it writes an acceptance harness, because a "sequence" that reads *"same as above"* grades nothing on
its own and a suite that counted it would report coverage it does not have.

**The classification rule, stated so it can be audited rather than trusted:** an entry is a
**`sequence`** when the developer's line names **two or more ordered actions**; a **`pointer`** when
it defers to another frame's line (*"same as above"*, *"exact same as above"*); **`verdict-only`**
when it names one action, a decline, or a bare judgement. A pointer's sequence is real — it just
lives on the frame it names, so grading it means resolving the pointer first.

| | frame | kind | agent |
|---|---|---|---|
| 1 | `81785223\|0\|decision\|32` | **sequence** ⚠️ carries an open discrepancy | mega_starmie |
| 2 | `81785223\|0\|decision\|44` | pointer → `81785223\|0\|decision\|32` | mega_starmie |
| 3 | `81904064\|0\|decision\|44` | **sequence** | mega_starmie |
| 4 | `81904064\|0\|decision\|59` | **sequence** | mega_starmie |
| 5 | `81904451\|0\|decision\|24` | **sequence** | mega_starmie |
| 6 | `81904451\|0\|decision\|37` | **sequence** | mega_starmie |
| 7 | `81904451\|0\|decision\|50` | pointer → `81904451\|0\|decision\|24` | mega_starmie |
| 8 | `81904451\|0\|decision\|53` | pointer → `81904451\|0\|decision\|24` (+ a Mega Signal) | mega_starmie |
| 9 | `81905522\|0\|decision\|28` | **sequence** | mega_starmie |
| 10 | `81905522\|0\|decision\|64` | **sequence** — the richest line in the file | mega_starmie |
| 11 | `81906131\|1\|decision\|25` | **sequence** | mega_starmie |
| 12 | `81906755\|1\|decision\|93` | **sequence** | mega_starmie |
| 13 | `81906755\|1\|decision\|9` | **sequence** (Batch 8) | mega_starmie |
| 14 | `82225138\|0\|decision\|82` | **sequence** — with an explicit re-decide point | mega_starmie |
| 15 | `82225643\|1\|decision\|57` | **sequence** (quoted rationale) | mega_starmie |
| 16 | `82227388\|0\|decision\|43` | **sequence** | mega_starmie |
| 17 | `82227388\|0\|decision\|50` | **sequence** (pointer + its own ordering) | mega_starmie |
| 18 | `82228017\|0\|decision\|16` | **sequence** (quoted rationale) | mega_starmie |
| 19 | `82228017\|0\|decision\|4` | **sequence** | mega_starmie |
| 20 | `82229122\|0\|decision\|17` | **sequence** | mega_starmie |
| 21 | `82229122\|0\|decision\|33` | verdict-only | mega_starmie |
| 22 | `82522698\|1\|decision\|36` | **sequence** | mega_starmie |
| 23 | `82522698\|1\|decision\|62` | **sequence** (a lethal decider) | mega_starmie |
| 24 | `82522726\|1\|decision\|7` | verdict-only | mega_starmie |
| 25 | `82525101\|1\|decision\|69` | **sequence** | mega_starmie |
| 26 | `82750161\|1\|decision\|60` | verdict-only | mega_starmie |
| 27 | `82752604\|0\|decision\|16` | verdict-only | mega_starmie |
| 28 | `82866415\|0\|decision\|43` | verdict-only | mega_starmie |
| 29 | `82867148\|0\|decision\|62` | verdict-only | mega_starmie |
| 30 | `83007714\|1\|decision\|8` | verdict-only | mega_starmie |
| 31 | `83037962\|0\|decision\|49` | verdict-only | mega_starmie |
| 32 | `83038055\|0\|decision\|51` | verdict-only (a hold, then the attack) | mega_starmie |
| 33 | `83053965\|1\|decision\|6` | verdict-only — but a **sound-rule** candidate, see below | mega_starmie |
| 34 | `83054602\|1\|decision\|32` | verdict-only (a reasoned END) | mega_starmie |
| 35 | `83456015\|0\|decision\|38` | verdict-only | mega_starmie |
| 36 | `83457493\|1\|decision\|33` | **sequence** | mega_starmie |
| 37 | `83966968\|0\|decision\|45` | verdict-only | mega_starmie |
| 38 | `85046350\|0\|decision\|21` | **sequence** — with a redecide and an explicit *don't* | dragapult_ex |
| 39 | `85163634\|1\|decision\|17` | verdict-only (a hold, reasoned forward a turn) | mega_starmie |
| 40 | `86089638\|0\|decision\|18` | verdict-only | dragapult_ex |
| 41 | `86090164\|1\|turn\|2` | **sequence** — the only entry that is a recorded TURN PLAN | dragapult_ex |

**Totals: 22 sequences, 3 pointers, 16 verdict-only.**

**Two concentrations Issue #263 must not discover after building against this list.**

- **By agent: 38 `mega_starmie`, 3 `dragapult_ex`, 0 `mega_lucario`.** The acceptance corpus is one
  deck's turn plans plus a rounding error. A composer that grades green here has been graded on
  `mega_starmie` sequencing — not on Mega Lucario's economy-vs-lock attack choice, which is Issue
  Issue #263's own acceptance requirement 3 and has **no sequence in this file at all**.
- **By shape: 16 of 41 grade a single action.** Useful as decision cases, but they cannot falsify a
  *sequence* composer — the thing this corpus exists to grade — because any ordering that ends in the
  named action satisfies them.

### The COVERAGE GAP against Issue #263's named acceptance targets — the point of this index

Issue #263 names five maneuvers it will be graded on. **None of the five has a sequence in this file.**
Verified by grep with a positive control (the same query finds `f43` and `f48`, which are present):

| Issue #263's named target | in this file? | where its rationale actually lives |
|---|---|---|
| **f32** retreat-to-sacrificial-item-lock-wall | **no** | **the best-documented maneuver in the repo, in four places.** `docs/plans/turn-planner-retreat-to-item-lock-wall.md` is a 73-line handoff giving the five steps, the full board, and the threat arithmetic verified at source (Gabite Dragonslice 40 + Roserade's Cheer On to Glory 30 = 70 vs Dreepy's 70 HP). Anchored on `tests/fixtures/corrections/dragapult_hammer_over_develop_f32.json`, frame `85046350\|0\|decision\|32`, `claims.decision` `owner=#165`, ruled 2026-07-25. Restated in Issue #165's body and again in the `xfail(strict)` reason at `tests/strategy/test_blunder_20260710_split_fixes.py:66` |
| **f35** (paired with f32 by Issue #263; an **Endorsement Claim**) | **no** | `tests/fixtures/corrections/dp_hold_evolve_until_typed_ready_f35.json`, frame `86091435\|0\|decision\|35`, `owner=#165`, re-ruled 2026-07-26. Carries a `decision` claim, an `endorsement` claim, **and a `turn_plan.intended_line`** — the only fixture in the whole store that has one (see below). Its `why` also already contains the horizon argument (*"`_engine_leaf_value` compares END-OF-TURN boards … cannot represent 'resolve the deterministic tutor FIRST, then branch'"*) |
| **f82** Adrena-Brain KO line | **no** | `tests/fixtures/corrections/dp_evolve_energized_line_body_first_f82.json`, frame `85785609\|0\|turn\|8`, `owner=#165`, ruled 2026-07-25 — full five-step chain in Issue #165's body (ADR-0070 §C); the DECISION half is already satisfied (ADR-0071 / Issue #163 promoted it from `xfail` to a passing regression test), the LEAF half is what still holds it out |
| **`stabilize-then-KO`** corpus frames (retired into the composer) | **no** | two anchors, both outside this file: the **`e1db` / f47** episode (`tests/fixtures/.../pilot_e1db`, exercised at `tests/strategy/test_blunder_20260703.py:104` — *"Wally's Compassion, THEN attach Ignition, THEN Nebula Beam for the 3-prize KO"*, a human-acked sequence recorded on the turn-8 pre-attach state), and the synthetic **`0cbc`** shape at `tests/strategy/test_planner.py:307` |
| **`forgo-KO`** corpus frames (retired into the composer) | **no** | the SAME `e1db` episode read from the other side — `test_blunder_20260703.py:143` pins the refutation (at f47 the attach is already spent, so the heal would forfeit a certain 3-prize KO). ADR-0045 S4 is the gate's ruling |

**So the answer to the question Issue #291 was asked is: they exist, and they are NOT missing — they
are in a different store.** This file holds 41 sequences Issue #263 did not ask for; the five it did
ask for are ruled, dated and reasoned in `tests/fixtures/corrections/`, keyed by frame, under
`owner=#165`. **Issue #263 must not re-derive them.** No developer ruling is owed for their rationale.

> **The single most useful artifact for Issue #263 is not in this file, and almost nothing points at
> it.** `dp_hold_evolve_until_typed_ready_f35.json` carries a **`turn_plan.intended_line`** — a
> 666-character CONDITIONAL multi-step maneuver with an explicit branch, written as structured data
> rather than prose:
>
> > *"1) Poké Pad -> fetch Drakloak. 2) Evolve a bench Dreepy -> Drakloak (2nd Recon body). 3) Recon
> > Directive x2 (see 4, keep 2). **4a) If a {P} appears:** attach it (active -> {R}{D}{P}), evolve
> > active Drakloak -> Dragapult ex, Phantom Dive {R}{P} 200 + 6 counters spread onto the two
> > Duraludon. **4b) If no {P}:** retreat the active Drakloak (cost 1, discard the dead {D}), promote
> > Budew, Itchy Pollen (No cost) -> 10 dmg + opponent cannot play Item cards next turn. The 4b branch
> > is the retreat-to-sacrificial-item-lock-wall maneuver of
> > `docs/plans/turn-planner-retreat-to-item-lock-wall.md` — **f32 and f35 are the SAME class.**"*
>
> Three reasons this matters more than any entry in the 41:
>
> 1. **It is the ONLY `turn_plan.intended_line` in the entire fixture store** — walked recursively over
>    every fixture, one hit. Every other acceptance case is prose in a `why` field.
> 2. **It settles what f35 IS.** Issue #263 pairs *"f32 + f35 retreat-to-sacrificial-item-lock-wall"*
>    without saying why f35 — a *hold-the-evolve* frame — belongs to a retreat maneuver. This line says
>    it outright: its **4b branch** is that maneuver. Two `*_f35.json` fixtures exist in the store
>    (`dp_hold_evolve_until_typed_ready_f35` and `dp_doom_guard_archaludon_1e_f35`) and this is the
>    evidence for which one Issue #263 means.
> 3. **It is a CONDITIONAL plan**, so it grades something the other 41 cannot: a composer that must
>    branch on information revealed mid-turn. Issue #263's commutative-block rule makes reveals block
>    boundaries — this is that rule's acceptance case, already written.

**What IS owed, and it is a different and smaller thing.** Issue #263 *"Merges old Issue #165"*, and
Issue #165 is **closed** (`completed`, 2026-07-31) while **9 fixture owner fields still carry
`owner=#165`** — f32, f35 and f82 among them. Those three are exactly the frames Issue #263 will
grade itself against, so the owner they name should be the issue that owns them. That is a
repointing ruling (`#165 → #263`), not a rationale ruling, and Issue #291 has deliberately **not**
made it: this issue was authorised to repoint one named frame off one closed owner, and re-owning
eight frames it was not asked about would be conforming a ruling rather than making one. See the
closed-owner census in the closeout batch below.
- `81785223|0|decision|32` — "The hand has pretty much all of our supporters, so PokeGear is actually
  not the play. its evolve staryu->mega starmie, play Hilda to fetch energy, attach energy to active
  starmie. attack jetting blow, snipe Wellspring Mask Ogerpon ex"
  ⚠️ **the snipe target is invalid** — Wellspring Mask Ogerpon ex is a Tera Pokémon ex and takes no
  attack damage while Benched. The developer caught this themselves; the rest of the sequence stands.
- `81785223|0|decision|44` — "exact same as above."
- `81904064|0|decision|44` — "my pick, play lillies. to retreat is absurd. opponents active has no
  energy, we have three from ignition energy. Attack with Nebula Beam"
- `81904064|0|decision|59` — "My pick, play Salvatore, evolve benched Staryu, attack with jetting
  blow KOing opponent."
- `81904451|0|decision|24` — "My pick, Hilda first to fetch Starmie, evolve if able.. then attack
  with Turbo Flare, give 3 energy to Starmie"
- `81904451|0|decision|37` — "My rationale correct. Hilda to fetch starmie, evolve the staryu with 5
  energy. retreat/promote that Starmie. attack jetting blow and snipe something."
- `81904451|0|decision|50` — "same as above."
- `81904451|0|decision|53` — "same as above, but now we have a Mega Signal"
- `81905522|0|decision|28` — "evolve active staryu, play lillies, attach KOing active, snipe Riolu"
- `81905522|0|decision|64` — "This one is more interesting. first attach energy to staryu. The
  opponents Mega Lucario is out of OHKO range, but we can gust up Hariyama with no energy and 2
  retreat cost. Attack Hariyama with JETTING BLOW, to snipe Lucario. Now Lucario has 190 HP, KO range
  of Nebula Beam."
- `81906131|1|decision|25` — "My ruling stands. and vital that buddy buiddy poffin played first
  before attacking with Turbo Flare"
- `81906755|1|decision|93` — "My ruling stands, attach the energy to the active starmie prior to
  attacking. Also play Salvatore to evolve one of the benched staryus. Attack and snipe the Raging
  Bolt ex."
- `82225138|0|decision|82` — "my pick. play buddy-buddy, the pokegear, redecide on new info if its a
  good supporter like Hilda (fetch energy to attach to Staryu) or Salvatore to evolve Staryu. Then
  attack with Nebula Beam"
- `82225643|1|decision|57` — "my pick, read correction's rationale: *'item cards should be used if
  they can be helpful prior to attacking. in this case, we have no mainline attacker available to
  replace our active, thus we should utlra ball to find a staryu thus that we can evolve it next
  turn. also, hero's capre should be used to give our main line aactive attacker more health.'*"
- `82227388|0|decision|43` — "My pick. Our active is doomed, but we have healing. Use Wallys
  Compassion, attach Ignition Eneergy, attack Nebula Beam"
- `82227388|0|decision|50` — "pretty much same as above. we are doomed, so heal. then sequence before
  attaching ignition energy and attacking with nebula beam."
- `82228017|0|decision|16` — "My pick. see rationale: *'Cinderace's attack give 3 energy to benched
  pokemon, therefor we should lay down a bench and at any cost when its empty before attacking. thus
  we should have payed buddy buddy poffin first.'*"
- `82228017|0|decision|4` — "This is about wasting a card that has no value to our game at the moment
  which could otherwise perhaps be used as Ultra Ball fodder. I would play Buddy buddy, attach energy
  to Cinderace, attack Turbo Flare"
- `82752604|0|decision|16` — "Just attack, as rationale says"
- `83037962|0|decision|49` — "Just attack, as rationale says"
- `83038055|0|decision|51` — "as rationale says, we have a strong hand so dont shuffle it away.
  Attack with Nebula Beam."
- `83053965|1|decision|6` — "as rationale says. Play Mega Signal"
- `83456015|0|decision|38` — "as rationale says. attack with Nebula for KO"
- `83966968|0|decision|45` — "as correction states, play Harlequin first, before attacking."
- `86089638|0|decision|18` — "as correction states, energize dreepy with P energy"
- `86090164|1|turn|2` — the record's own TURN PLAN, which the scan sheet had failed to surface:
  "Attach energy to our active dreepy, retreat to Budew, DO NOT play Lillie's this turn, because we
  want to evolve our Dunsparce next turn." Expected end board: "Budew in active, to attack with
  Itchy Pollen"
- `82866415|0|decision|43` — "Dont attach cape to a benched preevolution when our wincon is active
  and energized."
- `82867148|0|decision|62` — "leak plays buddy buddy and doesnt retrat. good!"
- `85163634|1|decision|17` — "Dont play lillies. we want the Crushing Hammer and Ultra Ball next turn
  most likely"
- `83007714|1|decision|8` — "Just end turn."
- `83054602|1|decision|32` — "We cant hurt the crustle with Jetting Blow, nothing to snipe, and we
  are not doomed. just end turn"
- `83457493|1|decision|33` — "Here, we have all three Staryu/Starmies, so buddy buddy is worthless.
  thinning the deck by playing both is a good idea. then play harlequin."
- `85046350|0|decision|21` — "Attach energy to active Dreepy as to retreat it to budew. Then evolve
  dreepy to Drakloak. Play Recon Directive, redecide. Dont play Ultra Ball. Attack with Itchy Pollen."
- `82525101|1|decision|69` — "Absolutely attach energy to our active starmie even though its doomed
  so we can attack with jetting blow and snipe other Lucario. You attached to the other because our
  active is doomed, but sometimes its better to play more aggressive and accept that we will get
  KO'd. Then play Harlequin before atacking."
- `82750161|1|decision|60` — "Buddy Buddy doesnt do anything for us. Attack with Jetting Blow"
- `82229122|0|decision|33` — "Play Crushing Hammer against the benched Crustle is a fine move."
- `82522698|1|decision|36` — "My rationale from correction, attach energy first before shuffling away
  hand or attacking"
- `82522698|1|decision|62` — "This is a lethal decider, KO to win match available, just take it and
  dont do unnecessary actions"
- `82522726|1|decision|7` — "as correction states and what it seems you do. attach energy to active
  staryu." ⚠️ **the leaf does not do that** — it ranks the BENCH attach first and the ruled ACTIVE
  attach 3rd of 5.
- `82229122|0|decision|17` — "as correction rationale says: *'Too eager to attack. could have filled
  up bench with buddy-buddy poffin AND attached energy AND evolved Staryu to main attacker.'*"
- `81906755|1|decision|9` (Batch 8, 2026-08-03) — "do not retreat. retreating staryu to staryu solves
  nothing. Orgepon with its ability can attach 1 grass energy to itself in a single turn, which will
  do 90dmg. so our active energies do not protect us. however, if we assume our active is doomed,
  which we such assume that it is, best to attach energy to a benched staryu if we haven't used up
  our attach already"
  ⚠️ **the 90 does not reconcile with the printed text** — see Batch 8's *Open discrepancy*; the
  sequence stands at any of 90/120/150, all lethal on a 70 HP Staryu.

**`82225138|0|decision|82` is worth T4's attention specifically.** *"play buddy-buddy, the pokegear,
redecide on new info"* is not an ordering preference — it asks the planner to **re-plan mid-turn on
information the earlier action revealed**. That is [ADR-0095](../../docs/adr/0095-information-precedes-commitment.md)'s
subject by name, and a turn plan fixed at the start of the turn cannot express it.

## Card facts, verified at source

Checked against `data/EN_Card_Data.csv` and `docs/rulebook.txt` rather than recalled, because several
went into committed ledger reasons:

- **Staryu (Basic) → Mega Starmie ex (Stage 1)** is a single hop — no intermediate Starmie.
- **Jetting Blow** `{W}` / 120, *"also does 50 damage to 1 of your opponent's Benched Pokémon
  (Don't apply Weakness and Resistance for Benched Pokémon)"*. **Nebula Beam** 3 Energy / 210.
- **Turbo Flare** is Cinderace's (Stage 2) attack: 1 Energy, 50 damage, search up to 3 Basic Energy
  onto Benched Pokémon.
- **Tera Pokémon ex take NO attack damage while Benched**, from *both* players' attacks
  (`docs/rulebook.txt` Appendix 6 L356; `docs/rules.md:185`). **Wellspring Mask Ogerpon ex** is
  Tera(Water) and **Teal Mask Ogerpon ex** is Tera(Grass) — neither is a legal snipe target on the
  Bench. This corrected a rationale already committed in batch 1.
- Legal snipe targets named above: **Riolu** (Basic, 70 HP) and **Raging Bolt ex** (Basic, 240 HP,
  category *Ancient*, not Tera).
- **Hariyama** is retreat **3**, not 2 as the `81905522|64` rationale said. The discrepancy cuts in
  the line's favour, so the reasoning holds.
- **Hero's Cape** is a Pokémon Tool: *"+100 HP"*. **Ultra Ball** is an Item usable *"only if you
  discard 2 other cards from your hand"* — so a card with no present use genuinely is fodder for it,
  which is the `82228017|4` rationale exactly. **Buddy-Buddy Poffin** searches out up to 2 Basic
  Pokémon with **70 HP or less**; Staryu is 70 HP, so it is eligible.

## Open discrepancies (flagged, not resolved)

1. `81906131|1|decision|25` carries a `covered` entry reading *"degenerate record (chosen ==
   correct)"* — filed as structurally unsatisfiable. The developer's *"my ruling stands"* contradicts
   that framing. One of the two readings is wrong; the entry is non-voiding either way, so the frame
   still gates and nothing was changed.
2. `82227388|0|decision|50`'s recorded pick is Pokégear 3.0, but the rationale leads with the heal.
   Read as `REVERT` (the label stands, the heal falling later in the same turn), consistent with the
   `covered` entry's *"human wanted Pokegear as the first dev"*.

## The pattern these verdicts are making

**40 frames ruled explicitly, three CONFORM — and the wave is COMPLETE.** All 17 triaged frames now
carry a verdict, and the remaining 28 of the 45 take the stated default (silence = REVERT), so every
flip in the set has a disposition. The packet recommended CONFORM on 15 and 14 were overturned, which
is why the triage that closed the wave rested on what the rationales SAY rather than on my read of
the moves.

Two things recur:

- **Four of the six voided frames fell to one misreading.** `81904451|37`, `|53`, `81905522|64` and
  `81906755|93` all carried a refutation of the form *"forgoes a KO / a 209-damage attack —
  over-eager"*. None of the developer's lines forgoes the attack; each **sequences it later in the
  same turn**. `81904451|58` and `82525741|81` are the two survivors, and `|58` carries the identical
  reason — it has NOT been ruled and must not be assumed.
- **Every `covered` entry on the batch-3 frames dismisses the same thing as a nicety** —
  *"same-turn ordering nicety"*, *"first-dev-differs"*, *"attack-last"*. The developer's rationales
  say the opposite: the ordering **is** the decision (bench before Turbo Flare; Item before
  attacking; heal before attaching).

Both point at one gap: the leaf cannot represent **sequencing within a turn**, so it prices a
develop-then-attack line and an attack-now line as the same board and lets `survival` break the tie
toward passivity. That is a T3 finding, not the Issue #278 artifact the deferral assumed — but it is
recorded here as an observation over 23 frames, not yet a diagnosis — and now corroborated by the
corpus's own categories, where `sequencing_error` is 36 of the 73 flips.

A third recurrence, from batch 4: **the ledger's stated reason and the developer's stated reason do
not describe the same decision.** `82228017|4` is filed as *"Resolved by dont-tutor-the-held-wincon:
Mega Signal is a wincon-only tutor…"*, while the developer's ruling is about not wasting Hero's Cape
that Ultra Ball could eat. Both may be true of the same board, but a `covered` entry that answers a
different question than the one asked is not evidence the frame is handled. Recorded, not acted on.

## The 22 that are NOT sequencing — diagnosed by term, 2026-08-02

The wave closed with 65 frames still gating. Splitting them by whether the LIVE agent plays the
ruled option — the Decision Gate's own `chosen` vs `correct`, not a re-reading of the boards —
gives three buckets with three different owners:

| | frames | owner |
|---|---|---|
| plays it right, `sequencing_error` | 21 | Issue #263 (T4). A board valuation scores END STATES; "develop now, attack later this turn" and "attack now" differ in ORDER, so no term can separate them. |
| plays it right, NOT sequencing | **22** | **this layer** — the subject of this section |
| plays it **wrong** | 22 | pre-existing. The Decision Gate re-run post-rebase reports `agree 250/347 -> 250/347, 0 picks moved`, so T3 caused none of them and T4's ordering is not why they are wrong. |

`tools/train/family_diag.py` (new) attributes each of the 22 to the `state_value` family that has to
change for it to flip back, by scoring the ruled option's and the leaf's end boards with
`state_value(..., working=...)` on the boards `planner._simulate_line` actually produces. The table
is generated into `t3-term-diagnosis.md` beside this file. Four findings, none of which any ruling
had named:

1. **The six-family scalar is a TWO-family scalar on this path.** `hand` is flat at exactly 0.0000
   on both sides of all 22. `threat` moves on 1. `prize_race` moves on 2. `readiness` is the largest
   delta on 2, at margins of 0.0034 and 0.0004 prizes — noise, not judgement. Every one of the 22 is
   decided by `development` (10) or `survival` (10).

2. **`development` credits a card play that nothing charges for** — the 10-frame cluster. The leaf
   plays Ultra Ball / Buddy-Buddy Poffin / Lillie's / Harlequin, banks the deploy marginal for the
   body it lands, and pays nothing in `hand`, because `hand` prices MY hand and the sim's end
   observation is opponent-perspective so my hand is hidden. `_line_account`'s spend charge is the
   only counterweight; it fires on four of the ten and is out-scaled about 3:1 where it does (-0.06
   prizes against a +0.20 deploy credit), and on the other six nothing charges for the card at all.
   The family's `blind_to` predicted this; it is now measured, and the entry says so.

3. **`survival` rewards passivity** — the other 10. On `83116501|60`, `82717711|37` and
   `83007714|8`, `survival` is the ONLY family that moves at all, so retreat-or-pass beats attack
   purely by lowering exposure. On both `85709280` frames the ruled line BANKS A PRIZE
   (`prize_race` +1.0156) and `survival` charges 1.37-1.46 more against it, so the scalar declines
   the prize. `ko-score-band` is not violated — it binds positional terms and `survival` is
   prize-denominated — but the effect is the one that rule exists to prevent.

4. **`threat` is a ONE-BIT term.** `needs.opponent_target_value` returns the target's prize value
   essentially unscaled at the `survival_shift=0` this module passes, so `min(_THREAT_CAP, sum)`
   binds on 100% of non-empty inputs: 0.0 on 20 frames, exactly the cap on 2, never between. A
   1-prize Basic and a 3-prize Mega ex price identically. The cause is a unit slip in the port — the
   incumbent rung is `min(cap, _PLANNER_THREAT_W * magnitude)` over DAMAGE points, and T3
   re-denominated the input into prizes while carrying the cap and not the weight, so `threat`
   became the one positional family with a runaway guard and no scale anchor, against the rule the
   module header states for all four.

### Finding 4's fix was applied, MEASURED, and reverted — the measurement is the point

The anchor is `_THREAT_CAP / _MAX_PRIZE_VALUE`: derived from two constants the module already
verifies at source, leaving the positional band and `POSITIONAL_MAX` untouched, and it makes the term
grade (1 prize → 0.033, 2 → 0.067, 3 → 0.1). It looked like the one finding here that was a defect
rather than a calibration, so it was applied. Then the Discrimination Gate was re-run:

```
unruled OK -> MISS   65 -> 68        (+3: 85785606|19, 85785606|21, 82752604|88)
MISS -> OK           18 -> 16        (-2: 85058574|88, 85785609|turn|8)
```

**Five frames worse, none better.** The mechanism is exact, not a guess: each of the five was winning
by a margin SMALLER than the 0.067 prizes of threat advantage the saturation was handing it — every
one reaches a 1- or 2-prize target that the unscaled term priced at the 3-prize maximum. On
`85785606|19` the ruled option trails on `development` (-0.0473) and `readiness` (-0.0413) and was
carried entirely by a 1-prize target priced as a Mega ex.

So removing the windfall is *correct* and it *costs rulings*, and the equation does not get to write
them. Reverted, and the finding is now recorded three ways instead: `threat`'s `blind_to` carries the
measurement and the derivation, `test_state_value.py` carries it as a strict-xfail TARGET that turns
red the day the fix lands, and `sound_rules.py`'s `firing-equation-constants` entry names
`_THREAT_CAP` as the one family cap with no anchor in front of it.

This also corrects a claim made when the fix was first committed — *"finding 4 moves none of the
22"*. That was true of the 22 and was checked; the rest of the corpus was not, and that is where the
five frames are. Diagnosing on a subset and shipping against the whole corpus is the error, recorded
so the next fix measures the gate BEFORE the commit rather than after.

### What is deliberately NOT done here

**Chip damage is left as a NAMED blind spot rather than closed.** Finding 3's mirror-image cause is
that `threat` reads reachability as a STEP — nothing at all unless my Active's best reachable damage
already meets the target's remaining HP — so a body chipped from 330 to 120 prices the same as one
at full HP, and `83116501|60`'s ruling (*"We can KO it with 2 Jetting Blows and a single Nebula
Beam"*) prices 0 every turn until the last. Grading it by a clock the way `survival` grades
`turns_to_ko_me` needs a MY-side KO clock on the model. `CombatMath.turns_to_ko` is the shipped
oracle but gates affordability on a raw energy COUNT while this family's filter uses the Attach
Budget, so routing to it as-is hands the family a second and weaker opinion about affordability than
the one it already holds. Writing `ceil(hp / damage)` in `state_value` instead would BE that second
opinion. The accessor is substrate and belongs to T1's completeness contract (Issue #260); the gap
is recorded in `threat`'s `blind_to` with that owner.

**Findings 2, 3 and 4 are not retuned.** All three are calibration between terms whose shapes are
right — and finding 4 earned its place on that list by measurement rather than by category, which is
the most useful thing this pass produced. Detail below for 2 and 3 —
`development`'s credit against a spend charge that lives outside the scalar, and `survival`'s
magnitude against a `threat` that cannot yet see a multi-turn KO plan. Moving either constant to
satisfy ten ruled frames would be fitting the equation to the corpus by hand, which is what the
post-POC learning phases (Issues #146-#148) exist to do with a held-out set. The diagnosis is the
deliverable; the retune is not.

## The wave CLOSES: all 65 gating frames held out onto their measured owner (2026-08-02)

**Developer-ruled 2026-08-02.** Every remaining gating flip is held out — the verdict on each is
UNCHANGED (the recorded label stands, the leaf is wrong), and what moves is the SCOPE: which issue
owns fixing the leaf. `gates.held_out_owner` is explicit that this is reversible with no ceremony —
*"Deleting `owner` is what returns a frame to gating"* — so this is a routing decision, not an
absolution.

| owner | frames | the measured cause |
|---|---|---|
| Issue #263 (T4) | 21 | within-turn ORDERING — no board valuation can separate "develop then attack" from "attack now"; they differ in order, not end state |
| Issue #330 | 22 | `survival`, uncapped and unopposed |
| Issue #331 | 15 | `development` credits a card play nothing charges for |
| Issue #332 | 6 | `readiness` funds a doomed Active over the successor; plus the sub-floor frames |
| Issue #329 | 1 | `threat` saturated into one bit |

Each frame's owner is the family `tools/train/family_diag.py` attributes its flip to, not a
category label — the attribution is in `data/leaf_lab/t3-term-diagnosis.md` and reproducible.

> ⚠️ **The `Issue #330` row is stale as of 2026-08-03 — kept, not overwritten, per this document's
> own convention above.** Issue #330 built its buildable half (two strict-xfail TARGET tests, the
> `ko-score-band` whitelist repoint) and closed. The blocked remainder — including all 22 frames'
> `owner` fields in `tests/fixtures/corrections/*_t3holdout_*.json` — moved to **Issue #369**. Five
> of the 22 are additionally claimed by Issue #291's T3.5 closeout below; that collision is tracked
> in **Issue #370**, not resolved by this repoint. The row above is correct about the state it
> described on 2026-08-02 and is left as written.

### Why this is the PLANNED sequence rather than a workaround

Issue #278 (POC-T3.5) is **"Blocked by #262 — T3 must merge first"**, and its whole purpose is to
remediate term-sufficiency findings in the terms T3 ships. Holding these frames onto that track's
children and onto T4 is what the plan already says happens; the alternative — blocking T3 until its
own successors' work is done — inverts the dependency the ADR fixed.

Two things this ruling does NOT do, stated because a held-out ledger that quietly did either would
be worthless:

- **It re-captures no baseline.** `data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json`
  are untouched. A baseline is a ruling record and auto-recapture is how the old Decision Gate died
  (ADR-0094 / `guarded_capture`).
- **It reverses no verdict.** Every wave-3 REVERT stands. A held-out frame still reads MISS; it is
  reported and not gated, which is the distinction the Discrimination Gate readout prints.

### What must be true when the owners land

Each of the five issues carries its frame list, and each must re-measure: a held-out frame that is
FIXED should be returned to gating (delete its `owner`) rather than left excused, or the ledger
becomes the wallpaper its own doctrine warns about. Issue #291 (T3.5 closeout) is the natural place
to check the whole set.

## Batch 8 (2026-08-03) — the T3.5 remediation track's one flip

The wave above closed on 2026-08-02. This batch is a **new** flip, from a different packet:
`docs/plans/issue-sequence-281-wave3-packet.md`, produced by the Issue #278 (POC-T3.5) run that
landed Issues #281, #280, #343, #282, #345, #346, #284, #285 and #286 on PR #340. It is recorded
here because this file — not the run-scoped packet — is where the Discrimination Gate's red frames
get a name attached to them.

| frame | packet rec | verdict | developer's line |
|---|---|---|---|
| `81906755\|1\|decision\|9` | REVERT | **REVERT** | do not retreat — retreating Staryu to Staryu solves nothing, and our Active's Energy is not what is protecting us |

**Ledger encoded 2026-08-04.** Per this file's own vocabulary a `REVERT` leaves the recorded label
standing, but the Discrimination Gate still needs an owner to keep a routed leaf gap from failing
`main` forever. `tests/fixtures/corrections/leaf_holdout_81906755_1_decision_9.json` holds the frame
out to Issue #332. Neither `data/leaf_lab/baseline.json` nor `data/decider_lab/baseline.json` was
touched.

### The ruling refutes the packet's *reasoning*, not just its ranking

The packet recommended REVERT on a **tempo** argument: that Ogerpon is three turns from being able
to attack at all, so dumping turn 1's only attach buys 30 damage of relief too far away to be worth
it. The developer's ruling rejects the premise underneath that argument — the relief is not merely
distant, it is **illusory**, because our Active's Energy is not the term that decides whether the
Staryu lives.

Verified at source, `data/EN_Card_Data.csv` Card ID 96, Teal Mask Ogerpon ex (TWM 25) — the packet
quoted the attack but **not the Ability on the same card**:

> `[Ability] Teal Dance` — "Once during your turn, you may attach a Basic {G} Energy card from your
> hand to this Pokémon. If you attached Energy to a Pokémon in this way, draw a card."

That is an attach *in addition to* the turn's normal one, so Ogerpon charges at up to **2 Energy per
turn**, not 1. The packet's clock table (30 at t=3, 60 at t=4, 90 at t=5 printed; 60 at t=3, 120 at
t=4 with the damage context) is derived from a one-attach-per-turn ceiling and is therefore **wrong
in the direction that matters** — it under-states how fast `{G}{G}{G}` comes online. Whatever
`turns_to_ko_me` returned on this frame, it was not reading Teal Dance.

This does not disturb Issue #280's fix, which is about threading the damage context and is
unaffected; it disturbs the packet's *narrative* about why the frame is close. It also sits squarely
on the epic's own ruled-omission line — **ability readiness → Issue #263** — so the gap is already
owned and is not re-litigated here.

### What the developer said the play actually is

Recorded as an ideal turn sequence, not a veto: the Active is to be treated as **doomed**, and the
turn's attach spent on a body that will still be there.

- Retreating Staryu → Staryu changes nothing about the matchup; both are the same 70 HP body.
- Ogerpon's own attach makes our Active's Energy irrelevant as protection.
- So if the attach for the turn is unspent, put it on a **Benched** Staryu.

That is a `readiness`-on-the-successor play, and it is the same shape as the `owner=Issue #332`
diagnosis already in this file — *"`readiness` funds a doomed Active over the successor"* — read from
the other side. Worth checking against that frame set when Issue #332 lands.

### Open discrepancy — flagged, NOT resolved

The developer's line says Teal Dance "will do 90dmg". I could not reconcile 90 from the printed
text and am recording that rather than quietly adopting or quietly correcting it. Myriad Leaf Shower
is `{G}{G}{G}` for 30, +30 **per Energy attached to both Active Pokémon**; paying the cost puts 3
Energy on their Active, which reads 30 + 3×30 = **120** with our Active bare, or 150 with our one
{W} still attached. 90 corresponds to `both_active_energy == 2`, which cannot pay the attack's cost.

**The ruling does not depend on the number.** 90, 120 and 150 are all lethal on a 70 HP Staryu, and
the developer's point — that our attached Energy is not what protects us — holds at every one of
them. Flagged in the same spirit as Batch 1's invalid snipe target: the sequence stands, the
arithmetic is queried.

---

# Batch 9 (2026-08-04) — Issue #291, the T3.5 CLOSEOUT

**Measured at `bb9bd69`** (`main`, Python 3.11.15, Linux x86_64, 4 vCPU Intel Xeon @ 2.80 GHz).
**Both gates PASS at that commit**, checked before any measurement was taken and again after the one
fixture edit below: Leaf gate *0 unruled, 67 ruled, 3 voided*; Decision gate *0 unruled*. **Neither
`data/leaf_lab/baseline.json` nor `data/decider_lab/baseline.json` was re-captured**, and no verdict
was sought for one. The Leaf gate's standing *"corpus has moved since baseline was captured"* warning
is left standing — it is a prompt for a deliberate ruled re-capture, not a licence, and this issue
was not the place to take it.

## The 15 deferred frames — 7 re-measured, 6 consumed, 2 confirmed

Issue #262's wave-3 packet flagged 15 flips as REVERT-worthy and the developer deferred them rather
than ruling them into the baseline, because they might have been measuring Issues #280/#281's bugs
rather than a preference. Issue #370 then ruled Issue #369 authoritative for the overlap. The routing
below was **verified against `tests/fixtures/corrections/*.json`'s own `claims.decision.owner`**, not
inferred from either issue's prose.

### 2a · Owned by Issue #369 — CONSUMED, not re-measured (6 frames)

Reported as Issue #369's results and cited to it. No fresh measurement, no fresh ruling.
**Issue #370's ruling names five; the real overlap is six** — `83966968|0|decision|45` reads
`owner=#369` in the fixture store and sits in this issue's 15. Confirmed at source; not dropped.

| frame | owner | Issue #369's disposition |
|---|---|---|
| `81904451\|0\|decision\|50` | #369 | Pilot-correct, no work |
| `82225643\|1\|decision\|57` | #369 | Pilot-correct, no work — Pokégear first accepted |
| `82227388\|0\|decision\|43` | #369 | Pilot-correct, no work — Pokégear, then Wally's Compassion |
| `83966968\|0\|decision\|45` | #369 | Pilot-correct, no work |
| `82522698\|1\|decision\|36` | #369 | **still a real miss** — ruled *attach Basic {W} to benched Mega Starmie ex*; Pilot plays Night Stretcher |
| `83053965\|1\|decision\|6` | #369 | **still a real miss** — ruled *Mega Signal*; Pilot ends turn. First player T1 cannot attack |

The two live misses stay blocked on Issue #263 per Issue #369's own dependency. Not circular: this
issue only reports them.

### 2b · Owned here — RE-MEASURED (7 frames)

`tools/train/family_diag.py --keys … --source decider` at `bb9bd69`, after Issues #280, #281, #329,
#332, #351 and #362 had all landed.

**THE ANSWER: passivity PERSISTS.** All 7 still fail, and `survival` is the decider on **7 of 7**.

| frame | decider | ruled | leaf | Δ development | Δ hand | Δ prize_race | Δ readiness | Δ survival | Δ threat |
|---|---|---|---|---|---|---|---|---|---|
| `81904064\|0\|decision\|44` | **survival** | Lillie's Determination | Retreat | +0.0000 | +0.0000 | +0.0000 | −0.0883 | **−0.9980** | +0.0000 |
| `81904064\|0\|decision\|59` | **survival** | Salvatore | End | +0.0548 | +0.0000 | +1.2500 | −0.0004 | **−1.4551** | +0.0010 |
| `82225138\|0\|decision\|82` | **survival** | Buddy-Buddy Poffin | Retreat | +0.0000 | +0.0000 | +0.0000 | −0.0004 | **−0.9961** | +0.0000 |
| `82227388\|0\|decision\|50` | **survival** | Pokégear 3.0 | Retreat | +0.0000 | +0.0000 | +0.0000 | −0.0818 | **−0.5078** | +0.0267 |
| `82752604\|0\|decision\|61` | **survival** | Basic {W} → benched Staryu | Retreat | +0.0000 | +0.0000 | +0.0000 | −0.0477 | **−0.5986** | +0.0264 |
| `82866415\|0\|decision\|48` | **survival** | Hero's Cape → benched Staryu | Retreat | +0.0000 | +0.0000 | +0.0000 | +0.0664 | **−0.5254** | +0.1000 |
| `83664991\|0\|decision\|25` | **survival** | Mega Starmie ex → BENCH0 Staryu | Turbo Flare | +0.0548 | +0.0000 | +1.0156 | +0.0209 | **−2.0000** | +0.0010 |

**Both outcomes were written down in advance, and this is the first one.** Passivity survives on a
level field — correct combat math (Issues #280/#281), an anchored `threat` (Issue #329), a fixed
`readiness` (Issues #332/#351). It is therefore a **real signal and not an artifact of the fixed
bugs**. The audit's warning that a damping constant fitted before F1/F2 landed would be fitted to a
measurement artifact is discharged: they have landed, and `survival` still wins.

**And phase damping is still the wrong knob** — for a reason the count alone would have hidden.
Every one of the 7 is categorised `sequencing_error`, and the shape is *order of operations*, not
*passive versus aggressive*: the ruled line and the leaf's line reach the **same end board** and
differ only in the order they reach it. No damping constant can express that. Issue #263's composer
can, which is why all 7 carry `owner=#263` and keep it.

**The single-deck concentration, reported because a count would hide it.** All 7 are
**`mega_starmie`** — 0 `dragapult_ex`, 0 `mega_lucario` — while the CONFORM camp spans all three.
They survived AND stayed single-deck, so per this issue's own advance criterion the cause is
somewhere other than the combat-math blockers. It is: within-turn ordering, which no term of a board
valuation can price.

**Positive control** (required before writing *"nothing moved"*): the instrument is not silent. It
returns non-zero deltas across five families on these same frames, up to 2.0 prizes, and reports
`hand` as inert on 7/7 — which is `hand.blind_to` entry 3 firing exactly as ruled, on the simulated
end board, while `value_lab` measures the same family contributing a mean of **+0.3261** across the
371-frame corpus on real boards. A dead instrument could not produce both readings.

### 2c · The 2 `hand`-blind frames — CONFIRMED unchanged, and one LABEL corrected

| frame | prior owner | now | result |
|---|---|---|---|
| `82522698\|1\|decision\|62` | #263 | #263 | unchanged — no decider; every delta ≥ 0 (total **+0.1826**) |
| `82749168\|1\|decision\|88` | **#332 (CLOSED)** | **#263** | unchanged — no decider; total **+0.0684**. Repointed |

Both were predicted unchanged and both are, which is the correct outcome rather than a failure. On
each, **the ruled option is weakly better on every single family and still loses** — no family
opposes it — so neither frame is attributable to a `state_value` term at all. That is Issue #263's,
whose composer decides an ordering the leaf's argmax cannot express.

`82749168|1|decision|88` is repointed off closed Issue #332 **on a re-measurement, not on the closure
alone**: `readiness` — its recorded cause — now moves it by exactly **0.0000**. The recorded cause is
discharged; the frame still fails. The original Issue #332 rationale is preserved verbatim in the
fixture rather than overwritten.

> ### ⚠️ Open discrepancy — the `hand`-blind LABEL is wrong on both frames
>
> Issue #291 §2c describes these two as sitting on a ruled `blind_to` entry where *"`hand` prices 0
> on a simulated end board."* **Measured, `hand` is not 0 on either.**
>
> | frame | `hand` on the ruled board | on the leaf's board | Δ |
> |---|---|---|---|
> | `82522698\|1\|decision\|62` | 0.3275 | 0.2158 | **+0.1117** |
> | `82749168\|1\|decision\|88` | 0.3502 | 0.3075 | **+0.0427** |
>
> Recorded, not resolved, and recorded on both sides per this file's standing convention. Three
> things make it worth carrying rather than correcting away:
>
> 1. **It is a known anomaly, not a new one.** Issue #332's own body flagged `82749168|1|decision|88`
>    as *"the only frame in either set where `hand` is non-zero — worth understanding why a hand
>    reached the model here when it does not elsewhere"*, and asked for ten minutes with
>    `frame_view.py`. That question was never answered and Issue #332 closed.
> 2. **It is LIVE — the number has moved.** Issue #332 measured Δ `hand` = +0.0944; it is **+0.0427**
>    at `bb9bd69`. The leaf's own pick moved too (Issue #332 recorded Harlequin; it is Boss's Orders
>    now). Something changed it and nothing recorded what.
> 3. **`hand.blind_to` entry 3 asserts "22 for 22" inert** across the frames the T3 layer owns. These
>    two are decider-corpus frames outside that 22, so the entry is **not refuted** — but it is also
>    no longer the whole story, and a reader taking "the whole family prices 0 there" as universal
>    would be wrong on exactly these boards.
>
> **What this does NOT change:** the disposition. Both frames are unchanged and unattributable either
> way; Issue #263 § *Parity + retirement* retires the develop rollout's sim path and makes them moot.

### Closed-owner census — REPORTED, deliberately not acted on

Issue #291 §2c gives the goal *"so the fixture store has no closed owners"* and authorises exactly
one repoint. Walking every `claims.*.owner` in `tests/fixtures/corrections/` shows the goal is not
met by that one edit: **24 owner fields still name a closed issue.** Every state below was read from
the GitHub issue, not inferred from the number's age.

⚠️ **Count `owner` RECURSIVELY or you will undercount.** A first pass over `claims.*` alone reported
23 and was wrong: `owner` also appears on **`turn_plan`**, and the one fixture that has a `turn_plan`
is `dp_hold_evolve_until_typed_ready_f35` — i.e. exactly one of Issue #263's named acceptance targets.
The numbers below are from a recursive walk of every fixture with `obs` excluded.

| owner | owner fields | state |
|---|---:|---|
| `#332` | 9 (was 10) | CLOSED `completed` 2026-08-03 |
| `#165` | **9** (8 × `claims.decision` + 1 × `turn_plan`) | CLOSED `completed` 2026-07-31 — **merged into Issue #263**, and includes f32 / f35 / f82 |
| `#262` | 3 | CLOSED 2026-08-02 |
| `#145` | 1 | CLOSED `completed` 2026-07-31 |
| `#161` | 1 | CLOSED `completed` 2026-07-29 |
| `#143` | 1 | CLOSED **`not_planned`** 2026-07-27 — the worst case in the table: the work was abandoned, so this frame's owner will never act on it |
| `#272` | 1 | **OPEN** (`status:1-grilling`) — *not* a closed owner; listed so the next reader does not re-derive it as one |
| `#263` 38 · `#369` 22 · `#329` 3 · `#351` 1 | 64 | all **OPEN** — the healthy majority, listed for completeness |

**Not repointed here, and that is the ruling-not-conforming discipline rather than an omission.**
Every owner is a developer verdict about *why* a frame fails; re-owning 24 of them off a closure date
would be adjusting the record to make a goal come out. The one frame this issue was authorised to
move was moved, and only after a measurement showed its recorded cause discharged. The remaining 24
are an owed repointing ruling, in this priority order:

1. **The 9 `#165` owner fields** (8 claims + the `turn_plan`) — Issue #263 merges Issue #165 and will grade itself against f32, f35 and
   f82 specifically. Highest urgency, and the target is unambiguous (`#165 → #263`).
2. **The 1 `#143` claim** (`ms_deny_wasted_on_doomed_active_f41`, frame `85163634|1|decision|41`) —
   closed `not_planned`, so unlike the others there is no successor issue implied by the closure. It
   needs a fresh owner, not a redirect.
3. The 9 `#332` and 3 `#262` claims, whose successors (Issue #369 / Issue #263) are at least
   identifiable.

## The Issue #263 hand-off package — three artifacts

### 3a · The budget — DERIVED per-decision P95, and it is a LOWER BOUND

Issue #263 sizes its beam, expectation-branch cap and commutative-block depth against this. **No new
timing tool was built**: `tools/train/value_lab.py` already times the leaf and names Issue #263 as its
consumer, so it was run, and the two legs it did not have were added to it.

**Leaf unit cost** (`state_value` + `_leaf_state_model`, 371 frames, 371 scored, 0 failed):

| | P50 | P95 | **max** |
|---|---|---|---|
| committed artifact run | **3.63 ms** | **6.57 ms** | **53.85 ms** |
| observed across 10 runs | 3.44 – 3.94 ms | **6.37 – 7.20 ms** | **46.8 – 59.9 ms** |

⚠️ **Quote the RANGE, not the point.** This is wall-clock on a shared 4-vCPU container and it moves
about 10% run to run. A beam sized against `6.57` as though it were exact would be sized against
noise. The **width** half of the derivation below has no such problem — it is a property of the
boards, and came out at exactly 12 on every run.

> ### ⚠️ The `max` is 8× the P95, and it is ONE named board — read this before sizing anything
>
> **`81904064|0|decision|17` (`mega_starmie`) costs ~52 ms in a corpus whose P95 is ~6.6.** The
> second-worst leaf in the whole corpus is `85058574|1|decision|109` at ~15 ms, so this frame is a
> **3.5× outlier over the next-worst and ~8× the P95.**
>
> **It is not a warm-up artifact**, which was the first hypothesis and was tested rather than assumed:
> it sits at index 141 of 371, well inside the `mega_starmie` block, and `mega_starmie`'s own first
> scored frame (`81785223|0|decision|12`) costs 5.49 ms. It is not noise either — it is the max on
> **every** run measured, at 51.8 / 52.2 / 53.2 / 53.9 / 59.9 ms.
>
> **Why Issue #263 needs this and cannot recover it from the P95.** The derived per-decision figure
> below multiplies two P95s, so it describes a typical-worst decision. A decision whose menu contains
> *this* board costs ~52 ms for that candidate alone — comparable to the entire derived per-decision
> budget — and no percentile-based number can warn you about it. This is exactly why Issue #291 §3a
> asks for P50 **and P95 and max** rather than a tail alone.
>
> **What it is not:** diagnosed. Nothing here explains WHY that board is slow, and this issue did not
> chase it. It is named so Issue #263 can profile one frame instead of a corpus.

**Post-OEC menu width** — the multiplier from unit cost to per-decision cost, over 372 frames.
Reported as a distribution because the tail is the whole point:

| raw P50 | raw P95 | post-OEC P50 | post-OEC P95 | post-OEC max |
|---|---|---|---|---|
| 6 | 16 | **6** | **12** | **23** |

293 options collapse under ADR-0091. Fate split across 2726 options: **1690 modelled, 510 terminal,
526 refused, 0 engine-resolved, 0 unclassified.** Two of those zeros are load-bearing rather than
filler: `engine-resolved` is 0 because `fate()` refuses the engine route with no `_search_api` wired,
which is the correct reading of a decision taken outside a search; and `unclassified` is 0, so every
option in the corpus got a real seam verdict and none of the counts above is padded by an instrument
failure.

**Derived per-decision P95 = post-OEC P95 × leaf P95 = 12 × 6.57 = `78.8 ms`**, and across the runs
**`76.5 – 86.4 ms`**. Round it to *"of order 80 ms per decision, leaf-only"* — the precision the
measurement actually supports. **Then read the `max` box above before sizing against it**: a single
menu containing `81904064|0|decision|17` spends ~52 ms on that one candidate, which this figure
cannot see.

**The worst frames, by name** (post-OEC of raw):

`85058574|1|decision|71` 23 of 23 · `84890060|1|decision|48` 22 of 22 · `86090164|1|turn|6` 19 of 27 ·
`83966336|0|decision|9` 17 of 17 · `81904451|0|decision|50` 17 of 20 · `83967841|1|decision|14` 16 of 16 ·
`81904451|0|decision|58` 16 of 19 · `82225643|1|decision|57` 16 of 16 · `81904451|0|decision|53` 15 of 18 ·
`85045840|0|decision|14` 14 of 14

> **⚠️ THIS IS A LOWER BOUND, AND THE MISSING TERM IS UNMEASURABLE BEFORE ISSUE #263 ITSELF.**
> Issue #291 §3a asks for *"the apply-seam transition cost, which `value_lab.py` does not time."*
> **It cannot be timed at this commit.** `apply_option` is POC-T0's frozen contract and raises
> `NotImplementedError` for every MODELLED fate — measured, **1690 of 1690** MODELLED options over
> the committed corpus, zero successes. **Positive control:** `fate()` itself resolves those same
> 1690 options to MODELLED without error, so the probe is sound and the seam is genuinely absent
> rather than mis-invoked. Issue #263 builds that transition, so the seam its own budget depends on
> does not exist to be measured before it. `84.8 ms` counts **leaf evaluations only**.
>
> Carried in the artifact as `menu.per_decision_p95_ms_is_lower_bound: true` and
> `menu.apply_option_ms: null`, not only in this prose — a consumer reading the JSON meets the
> omission there.

**This is a DEV-MACHINE number**, stated plainly as Issue #291 requires: Python 3.11.15, Linux
x86_64, 4 vCPU Intel Xeon @ 2.80 GHz. The Kaggle grader is **2 vCPUs × ~10 min/match** — quoted from
Issue #263 § *The composer* and Issue #273, **and not independently confirmed against the competition
page here**, so treat it as cited rather than verified. Issue #273 (POC-B3) does the deeper read on
the grader's own hardware after Issue #263 lands.

Re-derive with: `python tools/train/value_lab.py --menu --out reports/value.json`

### 3b · The consolidated blind-spot checklist

Issue #263's ceiling #2 says to consume Issue #262's registry list as the blind-spot checklist. **It
has moved under this track and nobody had re-read it whole.** Below is every entry of `blind_to`
across `REGISTRY` + `TERMINAL_REGISTRY` at `bb9bd69` — **35 entries, 7 families** — each mapped to the
Issue #263 family the blindness would silently zero. Under uniform 1-ply differencing a 0 delta is
**never explored**, not merely undervalued, so this is the list of plays the composer will
structurally refuse to consider.

| # | family | blindness (abbrev. — the module carries the full text) | still blind? | which Issue #263 family it silently zeroes |
|---|---|---|---|---|
| 1 | `prize_race` | deck_count / deck-out proximity | **blind** | fetch/search, draw supporters — a mill or heavy-draw line |
| 2 | `prize_race` | turn number / who went first | **blind** | the whole beam: a line trading a turn for position prices the trade at 0 |
| 3 | `survival` | the MARGIN below the case-1 win-condition test | **blind, OWNED** (Issue #283 POC ruling — binary on purpose) | terminal-action valuation: crossing that margin |
| 4 | `survival` | special_conditions | **blind** — snapshot zone OWED (T1 / Issue #260) | heal / status-cure plays price 0 |
| 5 | `survival` | attached_tools (defensive) | **blind** — same owner | **Tools** (the 5-rung equip band retires here) |
| 6 | `survival` | sub-turn healing (below one turn of incoming) | **blind, accepted at POC bar** | **Heal** — the family that motivated differencing |
| 7 | `threat` | SPREAD riders as a bench route | **blind, fail-closed under-read** | counter-placement + `EV(attack)`'s spread rider |
| 8 | `threat` | a multi-target snipe's COUNT | **blind, and now an OVER-read** | `EV(attack)` — Kyurem/Greninja multi-target |
| 9 | `threat` | the bench leg's reach beyond the snipe rider | **narrowed** (Issue #284 + #329) | gust whether-to-play; counter-placement |
| 10 | `threat` | the denial credit's SIZE | **narrowed** (Issue #329: 0 → 296 calls) | gust / snipe target choice |
| 11 | `threat` | the PRIZE a denied line would have yielded | **blind, and ⚠️ UNOWNED** — answers in damage, doctrine asks in prizes; Issue #329 discharged its only stated prerequisite and the entry names no owner | gust whether-to-play — *"trade 1 prize for a denied 3"* |
| 12 | `threat` | THEIR DECKLIST on the denial credit | **blind, deliberate over-read** | any line whose value is denial |
| 13 | `threat` | BACKWARD topology on the denial credit | **blind** — no opponent hand exists | denial lines against an unevolvable body |
| 14 | `threat` | the SCALING half of a denied payoff | **blind** — reads printed `maxDamage` | denial against scaling attackers (Alakazam) |
| 15 | `threat` | the non-Tera BENCH-IMMUNITY set | **blind** — no `CardStat` field (ADR-0020) | `EV(attack)`'s snipe rider — over-credits immune bodies |
| 16 | `threat` | an {ex}-restricted bench rider | **blind, fail-closed** | `EV(attack)` on `slowking`'s Zeraora line |
| 17 | `threat` | CONVERTING exposure into a prize | **by design** — `attack_ev`'s | none: this is the `score = state_value + EV(terminal)` split working |
| 18 | `threat` | their Energy denial / resource strip | **blind** — `deny_relevance` still dark (T2) | energy-denial plays (Crushing Hammer) price 0 |
| 19 | `threat` | their hand and deck AS A RESOURCE | **narrowed, not closed** (Issue #280 took the clock half) | **hand disruption** — Judge / Stamp / Harlequin |
| 20 | `threat` | CHIP DAMAGE — progress toward a KO I cannot yet complete | **blind** — reachability is a STEP | multi-turn KO plans; `dragapult_ex`'s whole engine |
| 21 | `threat` | the SURVIVAL half of `opponent_target_value` | **blind** — passed as 0; T1 owns the accessor | gust: a removal that buys turns without yielding prizes |
| 22 | `readiness` | the VALUE of the Active slot | **narrowed** (Issue #351 took the legality half) | retreat/promote sequencing |
| 23 | `readiness` | a board condition that is not a bench-partner condition | **blind ×12 attacks; exposure 0 across shipped decks** | `EV(attack)` — a deck change makes it live |
| 24 | `readiness` | **Ability readiness** | **blind** — no model supplies an Ability payoff | evolve-to-switch-an-engine-on. Named by the module as *"the largest single regression risk in this swap"* |
| 25 | `readiness` | an Energy that EVAPORATES on the now-leg | **VERDICT, not a gap** (Issue #351; bounded at 21 frames) | `EV(attack)` — partly-spent Ignition |
| 26 | `readiness` | what a DOOMED body could still do THIS turn | **blind** — `attack_payoff` names ONE attack | `EV(attack)` — the lesser swing off a doomed body |
| 27 | `hand` | hand SIZE as such | **by design** — measured, not missing | none |
| 28 | `hand` | information already revealed | **structural, whitelisted** | the commutative-block boundary rule already handles it |
| 29 | `hand` | **MY HAND on a simulated end board** | **blind on the SIM path; fully live on real boards** | the develop rollout — which Issue #263 RETIRES, closing it. ⚠️ see the §2c discrepancy above: measured non-zero on 2 decider frames |
| 30 | `hand` | DECK THINNING as a reason to spend a card | **blind** — no term reads deck composition | fetch/search + draw supporters — playing a card that covers nothing |
| 31 | `development` | the STADIUM | **blind** — supplier, no reader | **Stadium** (the deck-rung retires here) |
| 32 | `development` | their board topology | **blind, accepted POC asymmetry** | any line answering their development |
| 33 | `attack_ev` | the opponent's REPLY | **by design** — 1-ply (Issue #150 owns depth-2) | the beam's terminal valuation |
| 34 | `attack_ev` | opponent-choice riders | **blind** — no opponent model; apply-seam refuses the same class | `EV(attack)` riders |
| 35 | `attack_ev` | opponent ACTION-ECONOMY locks | **blind, declared** (Issue #290) | `EV(attack)` — Budew's Itchy Pollen, the 1-of that set `preferred_start="second"` |

**36 — the entry that is NOT in the registry, and must be.** Issue #376's developer ruling
(2026-08-04) accepts that `state_value` must not carry the prize value of cashing an attack boost —
that belongs to `attack_ev` under `score(sequence) = state_value(end board) + EV(terminal action)` —
and states the cost outright: **enabling cards such as Boss's Orders and Premium Power Pro may be
underplayed until Issue #263 lands.** A ruled, accepted, temporary blindness owned by **Issue #263**, with
no `blind_to` entry because the term that would carry it is the one Issue #263 wires. Listed here so
composer meets it before it writes a beam.

**Reading guide for Issue #263.** Six entries are *by design* (3, 17, 27, 28, 33, and half of 29) and
need no work — they are the double-counting rule and the 1-ply bound doing their jobs. Four are
**closed by this track's own scope**: 29 dies with the develop rollout, and 9/10/22/25 were narrowed
by Issues #284/#329/#351. The **live list is the rest**, and its centre of gravity is `threat` — 15
of 35 entries, of which entries 11, 20 and 21 are the three that would each silently zero a family
Issue #263 explicitly retires a rung into (gust, counter-placement, denial).

### 3c · The acceptance corpus

Delivered as an **INDEX** at the head of § *Ideal turn sequences* above, with the classification rule
stated so it can be audited. Headline results:

- **41 entries = 22 sequences + 3 pointers + 16 verdict-only.** Not 41 gradeable turn plans.
- **38 `mega_starmie`, 3 `dragapult_ex`, 0 `mega_lucario`.**
- **Issue #263's five named acceptance targets — f32, f35, f82, `stabilize-then-KO`, `forgo-KO` —
  appear in this file ZERO times.** They are **not missing**: all five are ruled, dated and reasoned
  in `tests/fixtures/corrections/` and in named tests, located by frame key in the index's coverage
  table. **Issue #263 must not re-derive them, and no rationale ruling is owed.**
- What IS owed is a **repointing ruling** for the 9 owner fields still carrying closed `owner=#165` (8 claims + f35's `turn_plan`) — f32,
  f35 and f82 among them — since Issue #263 merges Issue #165 and will grade itself against exactly
  those frames.

No sequence in this file was rewritten, reordered or tidied, and the file's open-discrepancy
convention is carried forward: §2c above records a developer-line-versus-measurement disagreement on
both sides rather than adopting or correcting either.
