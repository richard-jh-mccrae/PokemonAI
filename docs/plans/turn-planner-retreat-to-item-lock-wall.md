# Turn-planner scenario — the retreat-to-item-lock-wall maneuver (handoff, 2026-07-15)

Surfaced during the evolve-valuation grill (`evolve-valuation-grill-spec.md`, Phase-2 swap). This is
**line evaluation, not single-action pricing** — it belongs to the Turn Planner (ADR-0037), not the
`evolve_value` equation, which is why it is split out here. The `evolve_value` swap made a single evolve
out-score the maneuver's step-1 retreat; the fix is NOT to nerf the equation (the standalone evolve is a
fine one-move play) but to have the planner OWN and value the whole maneuver.

## The scenario

dragapult_ex, a fragile developing Active under a lethal threat, with a benched item-lock disruptor
(Budew) and a benched draw engine. The sound play is a **five-step maneuver in a single turn**, whose
value is the END-STATE, not any one step:

1. **Retreat** the Active Dreepy → promote **Budew** (pay the retreat with Dreepy's {R}).
2. **Evolve** the now-benched Dreepy → **Drakloak**.
3. Play **Drakloak's Recon Directive** (dig 1).
4. **Reconsider** the plan on the drawn card (the maneuver is not fully pre-committed).
5. **End the turn attacking with Budew's Itchy Pollen** — a 0-cost attack that **item-locks** the
   opponent next turn.

Terminal position: the wincon line (Dreepy→Drakloak) is safe on the Bench behind a 30-HP sacrificial
Budew wall, the opponent is item-locked, and a Recon dig is banked — for the price of one cheap Budew
prize. No single-action score can express this; it is a planned sequence valued at its outcome.

## The board (anchor: `tests/fixtures/corrections/dragapult_hammer_over_develop_f32.json`, 82... f32)

- Turn 4, my Main. I go SECOND. Stadium: my Risky Ruins.
- **ME** — Active **Dreepy 70/70 {R}**; Bench **Budew 30/30** (item_lock), **Dunsparce 70/70 {D}**;
  Hand: **Dragapult ex, Ultra Ball, Drakloak, Crushing Hammer**; Discard: Poffin, Crispin, Dreepy.
- **OPP** — Active **Cynthia's Gabite 100/100 {F}**; Bench Munkidori, Cynthia's Gabite, **Cynthia's
  Roserade 130/130**, Cynthia's Gible 50/70.
- **The threat (verified at source):** Gabite **Dragonslice {F} = 40**, +30 from benched **Roserade
  (Cheer On to Glory: Cynthia's attacks do +30 to my Active)** = **70 → my Dreepy (70 HP) is KO'd next
  turn.** (Evolving to Drakloak 90 would SURVIVE 70 — which is why a "threatened-Active penalty" on the
  evolve is the WRONG instinct; evolving is itself a defensive out. The maneuver is simply better.)
- Recorded: chosen `Play Crushing Hammer`; **correct `Retreat Dreepy → promote Budew`** (step 1 of the
  maneuver). Reframed 2026-07-10 (`/update-strategy` grill) as "NOT evolve-vs-strip — a Turn-Planner
  MANEUVER"; re-affirmed by the user 2026-07-15.

## The precedence problem (why the evolve swap regressed it)

Today the maneuver is expressed as a RUNG (`retreat-to-wall-the-line`, +30, backed by
`Pilot._can_wall_line_with_disruptor`) that must out-SCORE the alternatives, with `_finish_turn_last`
riding the retreat step tier-0. Before the `evolve_value` swap: retreat (30) > the evolve rungs (20) →
maneuver wins. After the swap: `evolve_value` prices the standalone evolve at **32** (deploy 15 +
energized 5 + Recon income 12) > retreat (30) → the maneuver loses. So the single-action evolve equation
and a maneuver-step rung are competing on the same score axis, and the equation (correctly) wins on the
one action while the multi-step plan (correctly) should win the turn.

## What to grill / build (another session)

The Turn Planner should **own** this maneuver — recognize the premise (fragile wincon-line Active,
benched item-lock disruptor, real incoming threat) and commit the retreat as step 1 of a valued line,
so it is not competing on the per-option score axis with `evolve_value` at all. Open questions:

- **Recognition + commit.** `_can_wall_line_with_disruptor` already encodes the premise. Should the
  planner promote it from a rung to a committed line (like the lethal LOCK / the disruptor-lock
  maneuver, ADR-0037), so `_finish_turn_last` and the equation never override a committed maneuver step?
- **End-state valuation.** Value the terminal position (line safe on bench + item-lock up + Recon
  banked − one Budew prize) so the maneuver is chosen for the RIGHT reason, not a hand-tuned +30.
- **The "reconsider" step.** Step 4 means the maneuver is not fully pre-committed — the planner must
  re-plan after the Recon draw. How does a committed line accommodate a mid-line reconsider?
- **Sibling maneuvers.** This shares machinery with the OFFENSIVE disruptor-lock
  (`_can_lock_line_with_disruptor`, dragapult f20) and the promote-retreat grill
  (`promote-retreat-grill-spec.md`) — ideally one session owns the maneuver-ownership question across
  all three.
- **Cross-layer guard for the evolve swap:** until the planner owns it, the swap must keep the
  retreat-to-wall value dominant over any single-action score so
  `test_blunder_20260710_split_fixes::test_f32_...` does not regress.

Do NOT blind-build: verify the maneuver premise and the threat math at source per frame (the
"isolated hand-built probes manufacture phantom misplays" trap). f32 is the concrete anchor.
