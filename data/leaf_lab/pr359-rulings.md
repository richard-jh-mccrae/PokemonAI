# PR #359 ruling record — the issue-sequence batch's packet

The developer's per-frame verdicts on `docs/archive/plans/issue-sequence-329-wave3-packet.md`, the packet
raised by the nine-issue batch in **PR #359** (Issues #329, #332, #362, #351, #350, #349, #374, #375,
#372).

Recorded here for the same reason as its sibling [`wave3-rulings.md`](wave3-rulings.md): **most of
these verdicts change nothing on disk.** A `REVERT` leaves the recorded label standing, needs no
ledger entry, and shows up only as the Discrimination Gate staying red on that frame. Without this
file that red has no name attached to it, which is the one thing `CLAUDE.md` says a ruling record
exists to prevent.

This is a **record, not an instrument**. Nothing reads it. `data/leaf_lab/baseline.json` is still the
gate's reference and **was never re-captured** — not once across the batch's 14 commits
(`git diff origin/main...HEAD -- data/leaf_lab/baseline.json data/decider_lab/baseline.json` was empty
at merge).

Per `wave3-rulings.md`'s standing note, the rationales are written as **ideal turn sequences** so these
corrections can be checked against the Turn Planner (Issue #263, POC-T4) once it exists. They are
reproduced **verbatim**, typos and all — a sequence rewritten in someone else's words is a sequence T4
would be graded against having already been interpreted once.

## Verdict vocabulary

Unchanged from `wave3-rulings.md`; `VOIDING_DISPOSITIONS` is `tools/train/gates.py:484`.

| verdict | what the developer said | what it changes |
|---|---|---|
| `REVERT` | my recorded pick stands; the new leaf is wrong | **nothing** — the frame keeps failing the gate |
| `REFUTED` | my recorded pick was wrong too | `reviewed.json` gains a `refuted` entry; the frame stops grading |
| `UN-VOID` | a standing refutation is withdrawn | that `reviewed.json` entry is removed; the frame re-enters gating |
| `CONFORM` | the new leaf's pick is right; absorb it | the baseline re-captures that row |
| `TRANSPOSITION` | the ruling STANDS, but `correct` names one of an *indistinguishable* set | voids like `refuted`, without disowning the ruling (ADR-0088 decision 6) |

## Verdicts (2026-08-04)

| frame | agent | verdict | developer's line |
|---|---|---|---|
| `83661649\|0\|decision\|54` | mega_starmie | **REFUTED** | pilot makes better decision to attach to bench given our active might be doomed if opponent plays ignition energy. |
| `85785606\|0\|decision\|19` | mega_lucario | **REVERT** | we certainly wanna attach with solrock and attack. much higher value than lunatones abiltiy or any other attach |
| `85785606\|0\|decision\|21` | mega_lucario | **REVERT** | same as above |
| `81904451\|0\|decision\|9` | mega_starmie | **REVERT** | dont retreat cinderace to staru in setup phase. we need cinderace to attack as to get 3 energy to bench |
| `83457493\|1\|decision\|20` | mega_starmie | **REVERT** | We do not have energy to power Cinderace, thus we are behind in tempo. The Salvatore however nice, doesnt help our immediate turn. we need to stall our opponent here given the real risk they evolve into Mega Lucario and KO our Cinderace, putting us even further behind. Boss's Orders up their benched mon with hghest retreat cost and least amount of energy and lowest threat. That is Makuhita |
| `85046350\|0\|decision\|85` | dragapult_ex | **REVERT** | attach the energy to the benched dreepy with an existing fire energy. bench slot 2. never attach energy to meowth unless desperate. |

### One superseded verdict, recorded rather than erased

`85785606|19` and `|21` were first ruled **TRANSPOSITION** — *"benching a pokemon and attaching energy
to another are commutative"* — and revised to **REVERT** the same day once the menu was actually read.

The first verdict rested on a misreading of the instrument, not of the game. `family_diag.py` renders
the leaf's competing option as `s0 BENCH1 = Lunatone`; that is the **Ability** option *targeting the
Lunatone already on bench 1*, **not** playing Lunatone from hand. There is no bench-play option on
either menu. The rules check that followed (bench-play and attachment draw on separate per-turn
allowances, so they commute) confirmed a real rule about a move nobody was offered.

The two `review_correction.py … transposition` writes it implied were **staged and never run**, so
nothing reached disk.

## Rationale detail

### `83661649|0|decision|54` — REFUTED

Verified before recording, because a refutation disowns a ruling:

- **Ignition Energy** (card 17, `special_energy`, engine dump): *"If this card is attached to 1 of your
  Pokémon, discard it at the end of your turn… it provides {C} Energy. If this card is attached to an
  Evolution Pokémon, it provides {C}{C}{C} Energy instead."* An **accelerator** — the doom is "opponent
  bursts three Energy and swings."
- **Mirror match.** Both Actives are Mega Starmie ex, so the opponent's deck contains Ignition Energy.
  Our Active is damaged (210/330) and gives up **3 prizes**; the opponent is at 5 prizes left.
- **The Pilot's own trace already agreed**: `dont-overbuild-the-doomed-wincon` fires **−45** against
  attaching to the Active, `concentrate-energy-on-wincon` **+25** toward the bench.

**The decisive evidence is older than the verdict.** `docs/todo/incoming-affordability.md` — split out
of this exact frame's fix — records that *"the f54 correction relied on seeing the opponent's hand
(replay), which the agent cannot."* The correction was made from information outside the agent's
information set. **ADR-0045** then ruled that `active_doomed` **stays worst-case** precisely because a
mirror opponent may hold an unseen Ignition burst, and the affordability-aware read was **built and
reverted as unsound**. Feeding the bench Mega is therefore the *designed* behaviour under shipped
doctrine, not a blunder.

The superseded 2026-07-04 `covered` reason is preserved verbatim inside the new `reviewed.json` entry,
including its own note that *"Human reversed the initial refuted call 2026-07-04"* — this frame has now
been contested three times, and none of that history was discarded.

### `85785606|0|decision|19` + `|21` — REVERT

`Lunar Cycle` (card 675): *"Once during your turn, if you have Solrock in play, you may **discard a
Basic {F} Energy card from your hand** in order to use this Ability. Draw 3 cards."*

It discards the very card the attach would place. Every attach option on both menus references the same
single hand slot, and at `|21` the hand is **literally one card**. So the options are **mutually
exclusive rivals, not orderings** — ranking them is a real preference and the ruling is scoreable. The
Pilot's own trace already names the conflict: `dont-lunar-cycle-away-the-last-attachable-f` at **−30**.

**Ideal turn sequence:** attach `Basic {F}` → **Active Solrock**, then attack with **Cosmic Beam** (70;
live because Lunatone is benched; damage unaffected by Weakness/Resistance). Do not spend the last
attachable `{F}` on Lunar Cycle. On `|19`, `Boss's Orders` is not the play either — *"Gusting is not
helpful here."*

### `83457493|1|decision|20` — REVERT

Every fact the rationale names is on the board: the opponent's Active is **Riolu with 1 {F}**,
**Makuhita is on their bench (slot 3) with no Energy**, our **Cinderace has no Energy**, prizes 6–6.
`Riolu → Mega Lucario ex` is a **single hop** in this set, so the KO threat is one turn away, not two.

### `81904451|0|decision|9` — REVERT

The leaf's argmax is literally `Retreat`, the one action the rationale forbids. Δ `readiness` −0.0037,
**below the decider floor** — no family clears it, so the flip is drift rather than a term getting this
wrong.

### `85046350|0|decision|85` — REVERT

Correction labels are **1-indexed**; `frame_view` prints the bench **0-indexed**. "Bench slot 2" is the
Dreepy carrying `Basic {R}` Energy — Fire, as the ruling says; the other Dreepy is bare.

The mechanical case is stronger than the rationale states: **`Dragapult ex`'s `Phantom Dive` costs
`{R}{P}`** (200 dmg) and evolving keeps attached cards, so attaching the hand's `{P}` onto the `{R}`
Dreepy means that body arrives at Stage 2 **already able to Phantom Dive**. Three Drakloak and two
Dragapult ex remain in deck. The same attach onto the bare Dreepy or onto Meowth ex builds nothing.

**Why Meowth ex is the wrong recipient** (card 1071): `Last-Ditch Catch` is a **once, on-play-from-hand**
Supporter search, and the frame records the body as *"came into play THIS TURN"* — its value is already
cashed. What remains is a **2-prize** body (HP 170, `ex`) whose only attack is `Tuck Tail {C}{C}{C}` for
**60**.

The generalisation — *never fund a spent utility body* — is **doctrine, not a frame verdict**. It is
filed as **Issue #376** and must go through `data/strategy/proposals/` per ADR-0046; per ADR-0034's fold
policy it reads role-keyed, so the general layer is the expected home rather than
`src/agents/dragapult_ex/`.

## One unapplied ruling, landed here

`81785223|0|decision|44` was ruled **REFUTED** by the developer on **2026-08-02**
([`wave3-rulings.md`](wave3-rulings.md) line 36, *"as 32"*), and its sibling `|32` was applied that day.
`|44` was not — `reviewed.json` still carried `covered`, which is non-voiding, so the frame kept
grading.

Worse, the `covered` entry is dated **2026-08-03**, one day *after* the refutation, and closes the frame
on the grounds that *"Current Pilot exactly matches the human ruling (Play Pokégear 3.0)"* — which is
the very pick the developer had refuted the day before. It was written against the stale correction
target and silently un-did the refutation.

Applied here on the developer's instruction, with the superseded reason preserved verbatim. **This is
executing a verdict already given, not a new one.**

## Gate state after these rulings

Measured on this branch, `data/leaf_lab/baseline.json` untouched:

| | before | after |
|---|---|---|
| unruled `OK → MISS` | 7 | **6** |
| ruled | 60 | 59 |
| voided | 3 | **5** |

`GATE: FAIL` — and that is the **correct terminal state**, not an unfinished one. All six remaining
frames are ruled `REVERT`, and a `REVERT` is *defined* to keep failing. **There are zero unnamed red
frames.** The gate is red because the developer said the leaf is wrong on those six, which is exactly
what the record is for.

The gate also reports `CORPUS SHIFTED: +1 frame added, -1 removed since the capture — re-capture the
baseline.` **Not acted on** — a re-capture is a ruling record and needs its own developer verdict.

## Two corrections to the packet's own framing

Recorded because the packet is the question and this file is the answer, so a wrong question should not
survive silently:

1. **`83661649|0|decision|54` was never one of the "unruled" frames.** It already carried a standing
   `covered` ruling, so the gate counted it as **ruled**. Refuting it moved `ruled 60 → 59` and
   `voided 3 → 4`; it did not reduce the unruled count.
2. **The packet's flip list is not the gate's unruled list.** The packet records flips *this batch
   caused*; the gate reports every unruled flip, including pre-existing ones. `81785223|0|decision|44`
   was invisible to the packet for exactly that reason. **Read the gate, not the packet**, when
   enumerating what is owed a verdict.
