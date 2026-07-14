# ADR-0026: M2 Posture's generic core is the Read's net-new levers, not generic seek/avoid

**Status.** Accepted and BUILT — `posture` is `PROFILE=True` (default ON): levers A (favorability) and
C (accurate development) are live, γ-gated on the Read. The 2026-07-03 amendment's
`dont-gift-a-refresh-when-favored` rung cleared all three evidence legs and also ships on.

**Context.** [ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md) defined Posture as a
deck-agnostic generic core ("seek `targets`, avoid `threats`, calibrate aggression to
favourability") plus deck-specific Read-conditioned Hypotheses. Wiring it (M2) surfaced two
facts that reshape the core:

1. **The Pilot already plays opponent-aware from card facts** — `snipe-the-threat`/`-weakest`/
   `-evolving-threat`, gust value by KO-prizes/stall, prize math on ex bodies, and a row of
   `Board` opponent signals (`active_doomed`, `opp_has_hand_size_attacker`, `strongest_forward_bench`).
   So a *generic* "seek any target / avoid any threat" layer largely **duplicates shipped behavior**.
2. **The Read was unwired and incomplete** — no `artifact.json` was compiled/committed, `pilot.py`
   never referenced the Scout, and the dossier's compiled `threats`/`targets` (incl. the `engine`
   role) were **dead data**: loaded by `artifact.py` but never read by `scout.py` (which built
   `Read.threats`/`targets` from observed in-play cards only). The documented "predicted when
   confident" layer ([scouting.md](../scouting.md)) was unimplemented.

**Decision.** The M2 generic Posture core is scoped to the Read's **net-new** levers only — the
behaviors card facts cannot already produce:

- **Lever A — Favorability.** The compiled matchup win-rate calibrates aggression by scaling an
  aggression↔disruption **weight band**. It is **board-dominated** (a meta *prior* — it nudges the
  default and breaks ties, but a concrete board signal, above all a KO or a forced defensive move,
  always wins; cf. [[forgo-ko-corrections-are-refuted]]), gated by the matchup table's native
  `coverage`, and makes **no Plan change** — STABILIZE stays deferred (it needs *board*-derived
  triggers, not a statistical prior).
- **Lever C — Accurate development.** A confidence-gated **modulator, both directions**, on M0's
  opponent-agnostic forward-evo snipe ([ADR-0020](0020-forward-evolution-index-is-a-provider-primitive.md)):
  *boost* when the Read confirms the line, *suppress* when a recognized archetype does not run it,
  fall back to the generic graph when unknown.
- **Generic "seek/avoid" is NOT re-implemented** — card facts cover it.
- **Confidence gating is a continuous multiplier `γ`** on every Read-specific lever, so an unknown
  opponent drives `γ→0` and Posture contributes exactly 0 — "**no regression vs an unknown opponent**"
  is *structural*, not tested. `γ` rises with the Read's monotonic in-match convergence
  (REQ-SCOUT-0002), so Posture is near-off early and ramps mid-late game, when it both matters and is
  trustworthy. Favorability (A) uses its native `coverage` instead of `γ` (it is already
  posterior-weighted).
- **Wiring is a behavior-neutral staircase.** **M2.0** — compile+commit the artifact, instantiate the
  Scout in `main.py`, carry the Read on **`Board`** (per-decision, *not* `Context`), declare
  `my_archetype` (`"Cinderace / Mega Starmie ex"`) for favorability; Posture-off, **zero decisions
  change**. **M2.1a** — the Scout completes the predicted `threats`/`targets` layer (merge the dossier
  intel, `seen`-flagged); still unconsumed, **zero decisions change**. **M2.1b** — the levers; the
  first behavior change, measured by the M1 pre-filter ([ADR-0021](0021-prefilter-balances-seats.md)).
- **Engine-removal moves out of the generic core.** Acting on a target's `engine` role is a tempo
  *investment* (a gust + a turn for usually one prize) whose value is matchup-specific, so it belongs
  in the Matchup Brief layer ([ADR-0027](0027-matchup-brief-is-hand-authored-opponent-doctrine.md)).
  The Scout still *surfaces* engine targets in M2.1a.

**Considered options.**
- *The literal ADR-0008 framing* (generic seek/avoid + favorability) — rejected: seek/avoid duplicates
  card-fact Posture, adding redundant, hard-to-attribute weight.
- *Favorability drives the Plan (activates STABILIZE)* — rejected for M2: conflates "losing *this game*"
  (a board read) with "this matchup is *generally* hard" (a prior). STABILIZE deserves its own
  board-derived design; escalate later with M1 evidence if the weight-band nudge proves too weak.
- *A hard confidence gate* — rejected: continuous `γ` makes no-regression structural and matches the
  Read's monotonic convergence rather than imposing a cliff.

## Amendment (2026-07-03, grilled): lever A's favored→race half is one variance-denial rung

The shipped `disrupt-when-unfavored` (+18) left the favored half parked for want of an "aggressive
option" vocabulary. The grill resolved it by the **variance principle**: unfavored → seek variance
(the shipped half), favored → **deny the opponent outs**. The one concrete durdle that gifts outs
when ahead is playing a SYMMETRIC refresh as your dig — Judge (1213) / Harlequin (1223) refill the
*opponent's* hand too (card text verified 2026-07-03); Lacey / Lillie's don't.

- **One rung: `dont-gift-a-refresh-when-favored` −15** — favorability ≥ **`_POSTURE_FAVORED =
  0.55`** (mirror constant of 0.45, dead zone 0.45–0.55 = noise around the 0.5 prior), same
  coverage ≥ 0.25 gate, `hand_disruption` in tags, PLAY. Judge/Harlequin-as-dig nets +5 (last
  resort, below tutors); **genuinely-triggered disruption survives** (`play-harlequin-vs-hand-size`
  +25 → net +30) — favored kills the gift, not the counterplay. Structurally exclusive with the
  unfavored half.
- **Killed framings, recorded:** an "aggressive option" **Function Tag is a category error** (tags
  are CARD facts, ADR-0006; "aggressive" is option-context) — the code comment wished for the wrong
  instrument. **Plan bias** (enter RACE earlier when favored) stays rejected — this ADR already
  ruled a statistical prior must not drive the Plan. **Attack-enabling dev boost** —
  considered-rejected: diffuse (the agent already attacks whenever endorsed and attaches every
  turn; `_finish_turn_last` already sequences dev first), no correction evidence, A/B attribution
  pain. **Down-weighting all disruption** — wrong for `energy_denial` (keeping a losing opponent
  down is good when ahead too).
- **Boundary:** this claims the *favorability-conditioned* half of the `hand_disruption` axis
  ADR-0024 parks (its board-conditioned remainder — opponent hand-size scaling — stays parked
  there). No ADR-0027 overlap: the rung reads only the compiled number, no per-archetype logic.
- **Evidence gate (the local-mirror problem — favorability ≈ 0.5, the rung never fires in a
  vanilla A/B):** three legs, all green → default ON. (1) unit tests on a seeded artifact fixture
  (compiled favorability ≥ 0.55 → fires, gates asserted, REQ-tagged); (2) vanilla mirror A/B —
  expected ZERO divergence, any divergence is a bug; (3) a stress A/B with a test artifact faking a
  0.7 mirror cell so the rung force-fires in real games — win-rate must not degrade beyond noise
  (upper-bounds the cost of a WRONG prior, the actual risk class of a prior-driven rung).
  Overlay-zeroable kill; TDD.

**Built + cleared 2026-07-03 (all three legs green → default ON).** Unit fixtures
(`tests/strategy/test_posture_read.py` REQ-POSTURE-0006): fires at 0.7, silent at 0.5 AND 0.3,
triggered disruption survives. Neutral mirror A/B: 52% (CI 49–55) — the artifact's mirror cell is
0.5141, inside the dead zone, so the rung is structurally silent. Stress leg: `my_archetype:
"Alakazam"` overlay (its compiled cell vs our archetype is 0.562 ≥ 0.55) force-fires the rung in
real games against a rung-zeroed twin with the same false belief — 52% (49–55), a wrong favored
prior costs nothing measurable.

**Consequences.** M2.1b is small and each lever has a clean "this is what the Read bought us" story for
the writeup. The first two steps change no decisions, retiring all recognition/intel-synthesis risk
before any behavior moves. Engine-removal and all matchup-specific posture are deferred to ADR-0027. A
brief-driven behavior that later proves generic can be promoted into a baseline cluster
([ADR-0025](0025-baseline-rules-cluster-by-decision-context.md)) by the usual expand-vs-override step.
