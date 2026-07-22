# Snipe discard-fuel — grill handoff for a SEPARATE session (2026-07-22)

Anchor **ep83667237 f107** (mega_starmie vs mega_lucario). Surfaced + partially grilled walking the
gust-adjacent corpus (`valuation-systems-coverage-review.md`; companion
`turn-planner-snipe-and-gust-scenarios.md` §A, the discard-fuel row). The user ruled the two
**trigger signals** in-session; the **trigger threshold** is the one open question, deferred here for
a fresh session to grill and build. Do NOT blind-build — the root cause sits in shared threat-rank +
prize-guard machinery the 16 currently-correct snipe frames also ride (planner-scenarios §A).

## The frame — verified at source 2026-07-22

- **My Active:** Mega Starmie ex (1031), 1 {W} — this is the **DAMAGE select for Jetting Blow's 50
  snipe rider** (Jetting Blow {W}: 120 + 50 to 1 benched).
- **Opp Active:** Mega Lucario ex (678), 200 HP, 1 {F} — *Aura Jab* {F}, 130: **"attach up to 3 Basic
  {F} Energy from your discard to your Bench"** (the discard-source accel).
- **Opp bench:** `[0]` Lunatone 110/0⚡ · `[1]` Mega Lucario ex 340/2⚡ · `[2]` **Hariyama 150/1⚡** ·
  `[3]` **Makuhita 80/0⚡** · `[4]` Solrock 110/0⚡.
- **Opp discard: 5× Basic {F} Energy** (id 6).
- **My hand holds 1× Boss's Orders** (the drag is live now).
- Card facts (data/EN_Card_Data.csv): Hariyama (674) *Wild Press* {F}{F}{F} 210, evolves from
  **Makuhita (673)**. Mega Lucario ex (678) *Aura Jab* pulls {F} from discard to bench.

Equation picks `[0]` **Lunatone** on `snipe-on-the-path:12`. Human `correct = [3]` **Makuhita**.

## Why the equation stands down on Makuhita (measured — it is deliberate, not a miss)

`snipe-the-evolving-threat` (+45, `baseline_snipe.py:89`) is the rung built for exactly Makuhita →
Hariyama (pre-evo whose forward form is a wincon-class Wild-Press attacker). It is gated by
`not target_forward_form_in_play` (`pilot.py:4988`): because a **Hariyama is already in play**
(bench[2]), the ADR-0044 discriminator fires — *"chip the ready form directly, not the redundant
pre-evo."* The rung's own docstring cites **test_107 (this frame)** as the case a naive restore
regressed. So Makuhita scores 0 and Lunatone wins on the path rung. (The `target_prize_redundant`
guard, ADR-0044, is the secondary suppressor — see planner-scenarios §A.)

## The user's in-session ruling (2026-07-22)

The `target_forward_form_in_play` stand-down is **wrong here** because the pre-evo is **not**
redundant with the Hariyama already down — the line is **multiply-live under discard fuel**:

1. **Discard-fuel read (opponent side).** 5 {F} in the opp discard + Mega Lucario's **Aura Jab**
   (discard-source accel) means a *second* Wild-Press body is re-fuelable. The "one wincon, already
   present" premise behind `target_forward_form_in_play` is false. **Both discard-fuel AND prize-path
   are the trigger** (user's words), not either alone.
2. **Prize-path.** With Boss's Orders in hand we KO the Active Mega Lucario (2 prizes) and drag what
   we need later, so the snipe is spent on **denial**, not reach: chip Makuhita (80 → 30; damage
   carries through evolution) as the cheap future KO on our path. Lunatone/Solrock (support, Lunar
   Cycle) and the 2nd Mega Lucario (redundant) are correctly NOT the target.

## The build cost — why this is a separate session, not a small fix

The discard-fuel primitive we have (`_discard_fuel_types`, `pilot.py:2270`) reads **OUR OWN** deck's
Aura Jab, not the opponent's. Reading the **opponent's** discard fuel does not exist — it is the
coverage doc's **"Opponent read — their DISCARD ❌ not read at all,"** ranked **item #2**
(prerequisite for the snipe grill, item #3). So the deliverable is: **build the opponent-discard read,
then let it override the `target_forward_form_in_play` stand-down** (and relax the
`target_prize_redundant` guard for an imminent fueled line — the two shared pieces planner-scenarios
§A names).

## THE OPEN QUESTION for the fresh session (grill this first)

Trigger threshold for the override:
- **Strict** — opp discard holds ≥ the {F} to power a fresh Wild Press ({F}{F}{F} = 3) **AND** an
  Aura-Jab body (Mega Lucario) is in play to move it. (This frame's 5 {F} + Mega Lucario satisfies
  it.) Fires only when the second line is genuinely one-turn-live.
- **Broad** — opp runs any discard-source accel **AND** discard holds any matching {F}. Fires more
  often; risks the frames the ADR-0044 discriminator was added to protect.

## Definition of done (deferred-disposition contract)

1. New **opponent-side discard-fuel signal** (mirror of `_discard_fuel_types`, pointed across the
   table): opp's in-play discard-source accel × their visible discard {F} count.
2. Override `target_forward_form_in_play` (and the imminent-fueled-line relax of
   `target_prize_redundant`) on that signal, per the ruled threshold.
3. Bench = the **23 DAMAGE snipe frames** (`snipe_sweep` probe, the `needs_sweep` pattern):
   **fix ep83667237 f107 (Lunatone → Makuhita); HOLD the other ~16 currently-correct**, and keep the
   ADR-0044 test still avoiding the redundant 2nd Mega Lucario where its form is genuinely singular.
4. Sibling failures from planner-scenarios §A (`82749168-38` already-evolved printed damage;
   `81905522-75` positional tie) are DIFFERENT gaps — do not conflate.

## Ledger

`data/corrections/reviewed.json` `83667237-107` moved `fixed` → `deferred` (this doc is its DoD). The
2026-07-04 ADR-0044 fix still holds for the *2nd-Mega* sub-issue; the *discard-fuel Makuhita* residual
is the new, deferred work.
