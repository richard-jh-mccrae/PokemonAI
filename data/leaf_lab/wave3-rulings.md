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

## Ideal turn sequences — VERBATIM (the Issue #263 / T4 acceptance corpus)

Reproduced exactly as the developer wrote them, including typos and abbreviations. Do not tidy
these: the whole point is that T4's turn plan is checked against the human's own words rather than
against someone's reading of them. Quoted blocks are the developer quoting the Correction's own
recorded rationale.

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

23 frames ruled, **one CONFORM**. The packet recommended CONFORM on 15 of them and 14 were
overturned, so the packet's read was wrong and should not be trusted for the remainder.

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
