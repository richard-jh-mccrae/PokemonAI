# Turn-planner scenario — multi-turn energy routing & turns-to-energy odds (handoff, 2026-07-22)

Surfaced while triaging the last `marginal` "regression" of the energy-attach oracle Round-0 sweep
(`attach-valuation-phase2-handoff.md`). Frame `85058574-121` looked like a target-choice miss but is
**not an energy-oracle decision at all** — the correct play needs multi-turn threat/deadline reads, a
prize-paranoid opponent model, and a hypergeometric odds calculation the single-turn energy oracle
structurally cannot do. This doc records the scenario, the user's ruling, and the pieces a turn
planner would need. It is a **seed for a future planner arc**, not a build spec.

Companion: `turn-planner-snipe-and-gust-scenarios.md` (the other planner-scope, line-evaluation
scenarios). Like those, this is **line evaluation, not card pricing** — it belongs to the turn/match
planner, not the energy oracle. **Card facts verified at source** (EN_Card_Data.csv, the
mega_lucario STRATEGY.md); verify again before building.

## The corpus anchor — `85058574-121` (mega_lucario vs Dragapult ex)

Re-tagged this session (user-confirmed): `correct` `[2]` (Mega Lucario ex) → **`[3]` Hariyama**,
`scope` → `turn`. The old label was deck-naive ("build the wincon"); the oracle's `[1]` Solrock and
the label's `[2]` Mega Lucario are BOTH wrong.

**Board (turn 10):** I lead on prizes — **me 4, opponent 6**. My Active Mega Lucario ex (340/340,
1 {F}) just used **Aura Jab** ({F}=130; Dragapult ex now 190/320) whose rider routes **up to 3 Basic
{F} from my discard (5 available) onto my Bench**. This select picks ONE benched recipient. My bench:
Lunatone, Solrock (+Air Balloon), a benched Mega Lucario ex (280/340, evolved this turn), Hariyama,
Makuhita — all 0 Energy. `energyAttached` and `supporterPlayed` already spent this turn.

**The correct line → route ≥2 {F} to Hariyama (`[3]`):**
1. **Threat read:** the opponent can't KO any of my Pokémon next turn — nothing forces my hand.
2. **Deadline read:** the Active Mega Lucario ex is ALREADY a next-turn KO *off-book* — one MANUAL
   {F} next turn → **Mega Brave {F}{F}=270 > Dragapult's 190 left**. That KO needs nothing from this
   route (Aura Jab reaches only the Bench anyway).
3. **So skip Solrock** (the weaker 70 attacker) and **skip pumping the 3-prize Mega Lucario liability**
   — route to **Hariyama** (Wild Press {F}{F}{F}=210), staging the next heavy **single-prize** attacker
   behind the Active (the force-8-prizes / single-prize-core doctrine, STRATEGY.md).
4. **Prize-paranoid follow-through** (ADR-0064, assume-the-accel): assume the opponent promotes a
   fully-energized backup Dragapult and eventually KOs the Hariyama.
5. **The odds calc that justifies committing to Hariyama now:** *how many turns until I draw an Energy
   or Energy-fetch to give the BENCHED Mega Lucario its first {F}, once Hariyama trades with the
   assumed backup?* — user's read: **≈ 3 turns**. That runway is what makes staging Hariyama (rather
   than holding for the Mega) correct.

## Why this is planner-scope, NOT energy-oracle-scope

The energy oracle (`Pilot._attach_value`) prices a single attach by this-turn readiness + convex
forward build, **prize-agnostic by ruling** (attach grill Ruling 4: "prize-math is planner-scope,
NEVER in the energy oracle"). It cannot see any of the load-bearing facts above: the opponent's KO
reach, the Active's off-book next-turn lethal, the 3-prize liability, the assumed backup, or the
turns-to-energy odds. Its convex term ranks Solrock (70@1) > Mega Lucario (67.5) > Hariyama (23.3) —
the exact reverse of the correct order — because a cheap complete-in-one body wins the first-energy
step. That is **not a bug to patch in the oracle** (doing so would corrupt the shared term for every
deck and violate the currency-zone rule); it is the wrong tool for a multi-turn decision.

The `attach_sweep` probe now buckets `scope: turn`/`match` frames as **PLANNER-SCOPE** and excludes
them from the fold-ranking 2×2 (9 such frames; `marginal` is 0-regression without them).

## Pieces a turn planner would need (the build, when it happens)

- **Threat/deadline reads** — reuse the existing substrate: `active_doomed` / `incoming_active_damage`
  (ADR-0064), and a "can the opponent KO body X next turn" query. Mostly built.
- **Off-book Active lethal** — "the Active is already a next-turn KO given one MANUAL attach" so this
  effect's energy is free to invest elsewhere. Composes the lethal-attach lookahead
  (`_attach_lethal_tactical`) with the once-per-turn manual-attach quota.
- **Prize-denial routing priority** — the mega_lucario doctrine (Solrock > Hariyama > protect the
  3-prize Mega Lucario ex, force 8 prizes). This is **deck-layer** (ADR-0034), not general — a
  mega_lucario rung / matchup brief that overrides the prize-blind general order.
- **Turns-to-energy odds** — a hypergeometric on the remaining deck: P(draw ≥1 Energy or Energy-fetch
  within k turns), via `deck_odds`. The new concrete consumer of the odds machinery for a *routing*
  commitment. NOTE: needs the decklist's Energy + fetch counts (Crispin, Ultra Ball, etc.).
- **Assume-the-backup** — the prize-paranoid opponent model (ADR-0064) already the standing doctrine.

## Open questions for the build session

- Where does routing live — extend the develop-rollout rung (`turn-planner-develop-rung.md`), or a new
  routing planner? The Aura Jab "route up to 3, in any way" is a SET decision (portfolio), not N
  independent single-recipient picks — the "sets not sums" shape the grill spec flagged.
- The turns-to-energy threshold (≈3 here) — derive from the deck's Energy/fetch density, or a tuned
  bound? Anchor the calc to `85058574-121` and capture more frames before generalizing.
- Only one corpus anchor so far. Do NOT blind-build — collect more `scope: turn` routing frames first
  (the "phantom misplay" trap, board-state-valuation-grill.md).
