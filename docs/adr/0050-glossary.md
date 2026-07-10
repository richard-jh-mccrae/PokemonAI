# Ubiquitous Language — Lethal verification & engine seeding (ADR-0050)

Terms the grill found overloaded or conflated in the handoff. Canonical choices below; use these in
code, tests, commits, and the follow-up lethal proposals.

## Observations & the seed

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Step observation** | The per-seat agent observation the engine emits per turn (`steps[k][seat].observation`); the object `search_begin` wants "exactly as is". **Carries `search_begin_input`.** | agent obs, obs |
| **Film observation** | The `.obs` embedded in a full-information visualize frame (`steps[0][0].visualize[i].obs`); what `backfill_obs.py` copies into a Correction. **Seed-stripped.** | replay obs |
| **Seed** / **`search_begin_input`** | The ASCII blob encoding a forkable engine position. Present on the *step* obs, absent on the *film* obs; the two deep-equal on `select`+`current`, so the seed is recovered by joining them. | search input, sbi (in prose) |
| **Backfill** | Adding `search_begin_input` + `own_prizes` to a fixture by a **content-join** to the step obs + an `OwnCardModel` replay — NOT a `cg.api` re-derivation. | re-derive, replay-through |

## Seeding the hidden zones

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Prefix seeding** | The old behavior: fill `your_deck`/`your_prize` with `self.deck[:n]`, an id-sorted decklist prefix. Hides the high-id band; unsound both ways. | `deck[:n]`, `take(n)` |
| **Exact seeding** | Fill from the **exact split**: `your_deck` = `deck_known_counts` (decklist − visible − prizes), `your_prize` = `own_prizes`. The ADR-0050 fix. | true-pool seeding |
| **Pool-into-deck** (anti-pattern) | Dumping the whole deck+prize pool into the `your_deck` half. Over-counts a prized copy → **false confirm**. Never do this. | flatten-the-pool |
| **Exact split** | The partition of hidden own cards into deck vs prize, known only from **match history** (`OwnCardModel` anchors ~frame 6); `None` from a single frame. Matches the full-info film's ground truth. | prize split |

## Verdicts & verification

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Engine verify** | `_engine_confirms_win` forking the engine, stepping a line, driving my selects via `decide()` to a verdict. **Already exists** = the handoff's "line driver (B)". | the tool, line driver |
| **Confirm / Refute / None** | Engine says I win / does not before the opponent acts / undetermined. Refute drops the candidate; None keeps the sound closed-form lock. | pass/fail |
| **False confirm** | Locking a win that is not real. The **one catastrophic** Solver error (a phantom win loses the game). Over-seeding can cause it. | phantom (ambiguous) |
| **False refute** | Refuting a real win. **Safe** — misses a win, never locks a phantom. Prefix under-seeding causes it. | miss |
| **Closed-form-only** (false-green) | A lethal whose recognition fires but whose real cascade refutes — passes a seed-less unit retest, fails under the engine. What DoD #3 audits for. | false-green (be specific) |

## The two gaps (do not conflate)

| Term | Definition | Aliases to avoid |
| --- | --- | --- |
| **Seeding gap** | The engine verify can't *see* the enabling card (prefix hides it). Fixed by exact seeding (Phase 1). Independent of `decide()`. | — |
| **Steering gap** | `decide()` doesn't *drive* the follow-up selects (tutor→Tool, play-Tool→Active, retreat, promote). The `lethal-retreat-enabler` build (Phase 3), NOT the tool. | follow-up hooks (ok), the tool (no) |
| **The tool** | Phase 1 seeding fix + Phase 2 backfill/probe/helper. **Not** the lethal hooks. | the verification tool (ambiguous with (B)) |

## Relationships

- A **Correction** embeds a **film observation**; **backfill** joins it to the **step observation**
  for the **seed**, and replays for the **exact split**.
- **Exact seeding** needs the **exact split**; the split needs **match history**, so a fixture must
  store `own_prizes`, not just the seed.
- A **fetch line** (tutor tiers 3–4) is only *generated* post-anchor (gated on `deck_definitely_has`),
  so **exact seeding** matters exactly when `own_prizes` is present — the unanchored **fallback**
  (`None`) is near-moot.
- Closing the **seeding gap** does not close the **steering gap**: f15 still refutes until Phase 3
  builds the hooks; the **helper** then gates them.

## Example dialogue

> **Dev:** "The handoff says fixtures have no seed, so we must replay each one through `cg.api` to
> re-derive it?"
>
> **Domain expert:** "No — the seed is only missing from the **film observation**. The **step
> observation** in the same replay has it, and they deep-equal on `select` and `current`. **Backfill**
> is a content-join, not a re-derivation."
>
> **Dev:** "Then once I add the seed, the engine verify drives f15 to a win?"
>
> **Domain expert:** "Two different gaps. Adding the seed closes nothing on its own — with **prefix
> seeding** the engine can't even offer Air Balloon (it's high-id, outside `deck[:44]`). That's the
> **seeding gap**; **exact seeding** fixes it. But f15 still refutes, because `decide()` doesn't yet
> *pick* Air Balloon and play it and retreat — the **steering gap**, which is the deferred
> `lethal-retreat-enabler`, not this tool."
>
> **Dev:** "So why not just put both Air Balloons in the deck half so the tutor always sees one?"
>
> **Domain expert:** "That's **pool-into-deck** — one of f15's Air Balloons is **prized**. Seat it in
> the deck and, for a card that's fully prized, you'd get a **false confirm**: the catastrophic error.
> Seed the **exact split** from `own_prizes`, never the pool."

## Flagged ambiguities

- **"The tool"** in the handoff meant *both* the already-existing engine verify (B) *and* the new
  backfill/helper. Split: **engine verify** (exists) vs **the tool** (Phase 1+2, new).
- **"Verified end-to-end"** was read as "f15 wins," which needs the **steering gap** closed (Phase 3).
  The tool's own proof-of-life is `f110` confirming — no new hooks required.
- **"Capture writes the seed"** (handoff DoD #4) implied the film path; the seed lives on the **step
  observation**, so capture must join the two (and also write `own_prizes`).
