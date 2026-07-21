# Turn-planner scenarios — snipe targeting & gust-line tempo (handoff, 2026-07-20)

Two scenarios surfaced during the WP-N8 keep-value currency grill (keep-value-needs-assignment-
grill-spec.md #11). Both are **line evaluation, not card pricing** — they belong to the turn/match
planner, not the keep-value assignment, which is why they were split out. This doc records the
scenarios, the user's rulings, and — importantly — the **corpus investigation done at handoff time**,
which found the discussed anchors do NOT map cleanly onto currently-failing corpus frames. Read the
investigation before building: a blind build risks the "isolated hand-built probes manufacture
phantom misplays" trap (board-state-valuation-grill.md builder gotchas).

## Scenario A — threshold-race snipe targeting

**The idea (user, on ep83037962 f49, the mirror Mega Starmie match):** choose the bench-snipe
target by a *race computation*, not just "biggest threat":
> "when we attack with Jetting Blow, snipe the benched Starmie, putting them to 230 — if they don't
> draw Ignition we get one more turn to snipe it again, under Nebula Beam's 210 threshold. But IF
> their benched Starmie started this turn at 330 HP, snipe their Staryu instead, because that we'd
> have a chance to KO in 2 turns while the Starmie would still require a two-turn attack."
> "snipe the Riolu if they have no energy in their discard, or [Makuhita/Hariyama] if they have 2+
> energy in discard."

Two distinct sub-signals:
1. **Threshold race** — prefer the snipe that gets a body *under my next-attacker's OHKO damage
   threshold* within the window before my successor comes online. All numbers are visible (their
   body HP, damage already on it, my snipe rider, my finisher's damage, their attach clock).
2. **Discard-fuel gauge** — read the OPPONENT's discard as a "which line is live" signal: a
   discard-fueled attacker line (Hariyama's Wild Press = {F}{F}{F}, 210 — verified
   data/EN_Card_Data.csv id 674) is a real evolving threat when their discard holds the {F} to
   re-power it; snipe its pre-evo (Makuhita, id 673) to preempt.

**Where it would live:** `src/common/strategy/baseline/baseline_snipe.py` (the snipe Hypotheses:
`snipe-for-the-ko` > `snipe-the-top-threat` > `snipe-the-threat` > `snipe-on-the-path` >
`snipe-the-forced-promotion`), fed by new `Context` signals off `pilot._target_*`
(`_target_forward_damage`, `_target_hp`, `_target_energy` at src/common/pilot.py ~4061-4110) and the
`board.strongest_threat_rank` / `target_is_top_threat` machinery in planner.py.

### Investigation (2026-07-20) — the corpus bench does NOT match the discussed anchor
The discussed anchor (ep83037962 f49) is a PLAY/attack frame (`correct=[2]` = attack), NOT a
snipe-target select — the snipe target it describes is a follow-up frame never captured as a
correction. So it cannot be benched directly.

The corpus HAS 23 real snipe-target (`SelectContext DAMAGE`=15) frames. The shipped bot matches the
human on **16/19** replayable ones. The **3 failures are three DIFFERENT gaps**, and only one is the
user's discard-fuel rule:

| frame | bot → human | the gap |
|---|---|---|
| `83667237-107` | Lunatone → **Makuhita** | **discard-fuel** — their discard holds 5 {F}; the Hariyama line is live; snipe its Makuhita. The bot scores Makuhita **0** (no rung fires) and takes Lunatone on `snipe-on-the-path` (+12). |
| `82749168-38` | Hoothoot → **Dragapult ex** | **already-evolved printed damage** — the human snipes the 320-HP evolved wincon; the bot pokes a small evolving Hoothoot (`fwd_max=60`). The forward-damage signal is 0 for a final-form body, so the top-threat rank undervalues it. |
| `81905522-75` | Riolu[1] → **Riolu[3]** | **positional tie** — two identical Riolu (both HP 80, `fwd_max=270`). No board signal splits them; likely unfixable by any value term (transposition). |

**Why this is a GRILL, not a blind build (root cause, measured):** on `83667237-107` the fueled
Makuhita scores 0 for TWO compounding reasons, both structural:
- `board.strongest_threat_rank == 0.0` for the whole board — the threat-rank machinery rates the
  Hariyama forward line at ZERO because its 210 (`{F}{F}{F}`) needs energy the Makuhita doesn't yet
  carry. The human counts it precisely BECAUSE their discard holds 5 {F} to re-fuel — the discard
  read the rank computation lacks. So `target_is_top_threat` / `target_is_threat` are both False.
- `ctx.target_prize_redundant == True` — the ADR-0044 prize-path guard says "don't chip a body I
  don't need", suppressing the snipe even if a threat signal fired.
Fixing it means lifting the threat rank for a discard-fueled line AND relaxing the prize-redundant
guard for an imminent fueled threat — touching two pieces of shared machinery that the 16 currently-
correct frames also ride. A blind poke risks them. The sound path is a **snipe-targeting grill**
(frame-by-frame user rulings, like the WP-N8 currency grill) over these 3 + the described threshold-
race case, THEN a corpus-benched build. Bench = the 23 DAMAGE frames (a `snipe_sweep` probe over the
corrections corpus, the `needs_sweep` pattern); acceptance = fix the ruled failures, hold the rest.

## Scenario B — gust-line tempo evaluation

**The idea (user, on ep83457493 f31):**
> "bossing up any of their bench, we'd KO that Pokémon with a Jetting Blow, and then the Lucario is
> right back in our face with full health. so we do not Boss here."

A gust+KO on a low-value bench body is a **bad trade** when the opponent simply promotes their
full-health, fully-fueled attacker back into the Active spot — the tempo lost (my whole turn spent
KOing a cheap body) exceeds the prize gained. A line evaluation: value = the KO'd body's prize/threat
MINUS what promotes back at full health and hits me next turn.

**Where it would live:** `src/common/strategy/doctrines/doctrine_gust.py`
`_gust_target_tactical` (~line 68) — the KO_SCORE-class gust-target valuation.

### Investigation (2026-07-20) — the discussed anchor is ALREADY handled, for a different reason
On ep83457493 f31 my Active is Mega Starmie ex with **0 energy** and NO energy in hand, so it cannot
pay Jetting Blow ({W}) after the gust. `_gust_target_tactical` already returns 0 via the
`can_pay_cheapest` gate — and its code comment literally cites this frame: *"the KO premise is
unpayable this turn (f31)"*. So the bot already declines the Boss here, just because it **can't
attack**, not because of the trade logic.

The REAL Scenario-B case — *can* KO the gusted body but *shouldn't* because the return trade is bad —
has **no corpus anchor** yet. Building a tempo-veto without one risks regressing the many gust+KOs
that ARE correct despite something promoting back (the normal case). **Needs a fresh corpus frame**
(or a grilled synthetic ruled by the user) that isolates "can-KO-but-bad-trade" before a build is
sound. Until then, the `can_pay_cheapest` gate covers the discussed frame.

## Recommended next step
Run a **snipe-targeting grill** for Scenario A (the 3 corpus failures + the threshold-race case),
producing ruled acceptance frames, then build against a new `snipe_sweep` bench. Scenario B waits on
a corpus anchor that exercises the can-KO-but-bad-trade trade; flag it for capture during play.
Neither should be blind-built — the shipped snipe system is at 16/19 and the failures are tangled.
