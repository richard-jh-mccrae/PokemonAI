# ADR-0126 - A follow-up frame is off-policy only when its predecessor actually CHANGES it; the same-turn rule was over-broad by more than 2×

**Status:** **Built and shipped** (Issue #412, 2026-08-06). Extracts Issue #412's detector out of
`tools/train/grab_sweep.py` into `tools/train/blunder/off_policy.py`, replaces its same-turn test
with a **dependency test**, censuses every non-MAIN select context, rules all 34 flagged frames, and
wires a **report-only** readout into both main-watchdog gates. **Amends ADR-0122 Decision 0**, whose
detector this supersedes — the finding there stands, its instrument does not. **Does not amend
ADR-0049**, whose across-turn `retest_span` doctrine is the precedent this applies within a turn.

## Context

ADR-0122 Decision 0 established the doctrine, and it is right: **a follow-up select is only
gradeable if the decision that opened it was correct.** A `_TO_HAND` menu exists because the agent
played a search; if playing that search was itself the blunder, the board is one the agent should
never have reached, and a Correction filed on the grab is not evidence about the grab. Applying it
inverted Issue #406's conclusion — the incumbent rung ladder went from *"misses 5 of 30"* to
*"misses 1 of 15 gradeable"*.

Issue #412 generalised the exposure and filed it as a corpus-wide problem: **93 of 372 correction
frames are non-MAIN**, every one a follow-up whose validity depends on an unchecked predecessor, and
only ctx 7 had ever been measured. The issue proposed extracting the working detector, censusing the
rest, and deciding what the gates should do.

The issue is **self-filed** (`CLAUDE.md`: treat its claims as needing independent verification).
Verifying them is what changed the build.

## The finding: the detector is not "sound but incomplete" — it is incomplete AND over-broad

Issue #412's own words are *"the detector is sound but incomplete"*: it fires only where somebody
happened to file on the predecessor, so any count is a floor. That half is true and is preserved
here.

The other half is not. The detector flags *any ruled Correction on an earlier frame of the same
episode and turn*, and that relation is far weaker than the doctrine it implements.
`mega_starmie 81785223-39` is the clean refutation:

| | |
|---|---|
| predecessor f38, ruled | *"Should play Pokégear 3.0 to dig for supporter earlier in turn"* |
| follow-up f39, ruled | *"Should snipe highest threat Pokemon, in this case the only benched pokemon with energy"* |

Pokégear 3.0 is `Look at the top 7 cards of your deck. You may reveal a Supporter card you find
there and put it into your hand` (`data/EN_Card_Data.csv` id 1122). It **cannot touch the opponent's
Bench**, which is the only fact the snipe ruling names. The attack still fires, on the same board.
The frame is fully gradeable and the detector kills it.

Four more ctx-15 frames have that exact shape. Measured over the whole corpus: the same-turn scan
flags **34** frames; **15** survive the dependency test. Shipping the rule as filed would have
deleted **19 perfectly good frames** — the same wrong-denominator error Issue #412 exists to stop,
pointed the other way. A gate does not become sound by getting quieter.

Two further defects were pure bugs, not judgement calls — the detector claiming a relation the
corpus does not record:

* **Endorsement records were read as blunders.** 15 committed Corrections carry `chosen == correct`
  — the human *agreeing* with the play, filed as a note or a regression guard. `85058574-109` says
  so in its own rationale (*"This is a match planer note"*). Reading one as *"an earlier decision
  was ruled wrong"* inverts its meaning. Clearing them removed one flag outright and thinned two.
* **`episode_id is None` collided across sources.** The three ctx-17 records come from committed
  engine-parity captures (`v2_ms_mirror_5000` / `_5001`), not games. Keyed `(agent, None)` they all
  landed in one bucket, so f82 of one trace scanned as a predecessor of f100 of **another**.

## Decision 1 — the test is a DEPENDENCY test, and the scan cannot compute it

A follow-up is ungradeable only when the ruled-**correct** predecessor play would have:

* **(a) prevented this select from opening at all** — the Ultra Ball whose search this is, ruled
  *"should have saved the ultra ball"*; or an alternative line ending in an attack with no
  bench-damage rider, so no `DAMAGE` select is posed (Nebula Beam `{C}{C}{C}/210` carries none while
  Jetting Blow `{W}/120` does, both Mega Starmie ex, id 1031); or
* **(b) changed a board fact the follow-up ruling NAMES** — Boss's Orders (id 1182,
  `Switch in 1 of your opponent's Benched Pokémon to the Active Spot`) moving the very Riolu the
  follow-up rules to snipe **off the Bench**.

Anything else is **orthogonal** and stays gradeable.

That test needs the predecessor's card text read against the follow-up's prose. No corpus scan can
do it. So the module **splits what the old helper conflated**:

* `candidates()` — the mechanical scan, narrowed by the two bug fixes above. Its output is a
  *question*.
* `RULINGS` — the developer's verdict per frame, each carrying the reason and the card id that
  settles it. AUTHORED, never derived.

A candidate nobody has ruled is **`UNRULED`** — reported, never silently filtered. This is the same
shape both gates already use for a baseline: a ruling record, never auto-derived (`CLAUDE.md`).
`classify()` never returns `OFF_POLICY` on its own reasoning.

**`GRADEABLE` verdicts are recorded explicitly**, not left to fall out of an empty scan. A frame
with no candidates and a frame ruled orthogonal are both gradeable, but only one of them has been
looked at, and a ledger that could not tell them apart would lose the review the moment the corpus
grew.

## Decision 2 — census every non-MAIN context; the exposure is real but concentrated

`tools/train/off_policy_census.py`, over 375 committed Corrections. **96 are non-MAIN** (Issue #412
said 93 of 372; the corpus grew by 3).

| ctx | | n | candidates | ruled OFF-POLICY | gradeable |
|---|---|--:|--:|--:|--:|
| 7 | TO_HAND | 31 | 14 | 6 | 25 |
| 15 | DAMAGE | 23 | 9 | 3 | 20 |
| 8 | DISCARD | 12 | 5 | 3 | 9 |
| 21 | ATTACH_FROM | 7 | 4 | 2 | 5 |
| 3 | SWITCH | 4 | 1 | 1 | 3 |
| 34 | SKILL_ORDER | 1 | 1 | 0 | 1 |
| 4/1/2/17/22/5 | | 18 | 0 | 0 | 18 |
| | **all non-MAIN** | **96** | **34** | **15** | **81** |

Every run prints the **positive control** — does the scan still fire on the ctx-7 base it was ruled
on? — because this module's success state is *fewer flags*, which is exactly the shape where a
broken instrument reads as good news (`CLAUDE.md`).

## Decision 3 — the gates FLAG AND WARN; they never drop

`gates.off_policy_frames()` joins the ledger onto the **Frame Key** both gates speak, and
`print_off_policy_readout()` prints it from the Discrimination Gate and the Decision Gate alike.
Neither verdict function consults it — asserted structurally by a test, because the tempting edit is
one line.

Excluding the frames from both baselines was the obvious alternative and was **rejected**. A
baseline is a ruling record and both gates already refuse to auto-recapture one (ADR-0094), so
silently shrinking the gated set is the same class of act as auto-recapture: it makes a gate weaker
without anyone ruling that it should be. This is the identical argument Issue #251 settled for the
**Unstatable Decline**, and the measurement above is why it matters here — on the naive detector a
third of what would have been dropped was gradeable.

**Measured on both gates, and the two answers differ for a structural reason.** The Decision Gate
prints `OFF-POLICY (15)` and PASSES. The Discrimination Gate prints nothing — and that silence was
checked rather than assumed, because *"found nothing"* and *"my instrument is broken"* return the
same empty output (`CLAUDE.md`). Its committed baseline holds 268 scorable rows of which the corpus
resolves **267 to `SelectContext.MAIN`**: the Leaf Lab grades the develop-rung leaf and
`is_leaf_frame` admits no follow-up select, so the intersection is empty by shape. The positive
control is the same join against the Decision Gate's baseline, which returns all 15. This is the
identical asymmetry the **Unstatable Decline** already carries, reached independently. The wiring
stays on the leaf side because that population could widen, guarded by a tripwire test.

The readout is two-tier: a tally of how much of the graded population is off-policy, and a named
list of only those that **moved in the fail direction**. That subset is the actionable one — a gate
going red on an off-policy frame is reporting a change on evidence that cannot speak about the
change. A section naming every frame on every push to `main` becomes wallpaper, which is the failure
mode `print_ruling_readout` documents for itself.

## Decision 4 — all 34 candidates ruled; two needed the developer

Ruled 2026-08-06 against `off_policy_census.py --review`, every card fact read from
`data/EN_Card_Data.csv` at ruling time. **14 OFF-POLICY, 20 GRADEABLE**, plus the one scan-invisible
frame ADR-0122 already carried (`mega_lucario 84889011-7`) — 15 off-policy in total.

Two were genuinely undecidable from the record and went to the developer:

* **`mega_starmie 82752604-62`** (ctx 15) — f61's correct line is *"attach → Mega Signal → evolve
  the staryu → then attack"*, and **which attack** decides it: Jetting Blow keeps this bench-snipe
  select, Nebula Beam removes it. Developer ruling: *"Attack with Jetting Blow to KO active Budew
  and Snipe a Drakloak, either one"* → **GRADEABLE**.
* **`mega_starmie 85164605-48`** (ctx 15) — f41 rules Mega Signal over Salvatore, and they are not
  interchangeable: Salvatore (id 1189) *puts the evolution onto* a body, explicitly including one
  played this turn, while Mega Signal (id 1145) only reaches the hand. Developer ruling: *"Frame
  discusses who to snipe, not Mega Signal v Salvatore … either way, if Staryu was played this turn,
  Salvatore is best, if not, Mega Signal is best because it doesnt take up the supporter play"* →
  **GRADEABLE**; the attacker exists on either route and the opponent's Bench is untouched by both.

The zero-`UNRULED` state is asserted by a test, and it is **designed to decay**: a Correction filed
on a new follow-up frame in an already-ruled turn lands as `UNRULED` and fails, which routes it to
`--review` rather than letting it grade on an unexamined premise.

## What this does NOT do

* **It does not touch the MAIN population.** 48 of 279 MAIN frames have a same-turn ruled
  predecessor. Extending the doctrine to MAIN → MAIN within one turn is a generalisation nobody has
  ruled on; `composer_lab` reports that count and deliberately never filters on it. Unchanged here.
* **It does not systematically re-audit historical ADRs.** *"N of M ruled frames agree"* claims in
  shipped ADRs were computed on the denominators available at the time, and re-deriving every past
  decision is not in scope. But the census did surface **one live instance**, and it must not be
  buried in a "not in scope" clause — see below.

## The exposure is not hypothetical: ADR-0124 has an off-policy frame in its evidence

Issue #412 predicted that *"ADRs historically justified by 'N of M ruled frames agree' — an unknown
fraction of those M may have been off-policy"*. That is not a historical worry. **ADR-0124 merged
the same day** (Issue #417, PR #419) and states, of the `ATTACH_FROM` half:

> *"…so all three ctx-21 frames are now gradeable and covered."*

One of those three, **`mega_starmie 82224509-31`**, is ruled OFF-POLICY here, and the ruling is
mechanical rather than interpretive — it is legible in the option encoding, not just the prose:

| | |
|---|---|
| f29 (MAIN, turn 4) ruled correct | option `[4]`, `type=9 EVOLVE`, `area=2 HAND idx 2`, **`inPlayArea=5 (BENCH) / inPlayIndex=1`** |
| f31 (ctx 21, turn 4) ruled correct | option `[1]`, **`area=5 (BENCH), index=1`** — *"Staryu (bench 2)"* |

The predecessor's ruled-correct play **evolves the exact bench slot** this frame's ruling says to
attach to, and the ruling's own reason is about that body's identity and energy need
(*"dont attach more energy on a pokemon than it needs … should have attached on the other benched
mon without any energy"*). Under the correct line, option `[1]` is a Mega Starmie ex rather than a
bare Staryu. Case (b), squarely.

**What survives, and what does not.** ADR-0124's central claim is untouched: its *unambiguous* pass
is `83116081-21`, which is ruled GRADEABLE here, and `83007714-22` is an endorsement record
(`chosen == correct`) which is also gradeable. So the `ATTACH_FROM` conclusion — that the half was
already built — still rests on evidence that can speak. What is now false is the count: **two ctx-21
frames, not three**, and the sentence quoted above should read *two gradeable and one off-policy*.
This ADR does not amend ADR-0124's decision, only the strength of one supporting sentence.

The reusable point is the one Issue #412 was filed for. Nothing was wrong with ADR-0124's reasoning
on the frames it could see; the frame count was simply the wrong denominator, and **no instrument
existed to say so** — which is precisely the gap `off_policy_frames()` now closes for every future
gate run.
* **It does not claim completeness.** The scan still only sees predecessors somebody filed on. The
  ledger is keyed on the frame precisely so a developer ruling can cover what the scan cannot, the
  way `84889011-7` needed one — and any count remains a **floor**.

## Consequences

* `tools/train/blunder/off_policy.py` is the one detector; `grab_sweep._off_policy` and
  `composer_lab.off_policy_reasons` both delegate, and `grab_sweep._RULED_OFF_POLICY` is now a
  derived view of the ledger.
* `tools/train/off_policy_census.py` gives the tally, the frame list, and the review packet.
* Both main-watchdog gates print the exposure on every push to `main` and neither gates on it.
* `tests/train/test_off_policy.py` covers the scan, the two bug fixes, the scan/ledger split, the
  live census and the gate wiring — each census assertion paired with its positive control.
