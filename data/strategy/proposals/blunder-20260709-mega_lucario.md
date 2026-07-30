<!-- Strategy Proposal queue — blunder-buster round 2026-07-09 (mega_lucario).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Routing evidence: real-Pilot retests (tune._build_pilot('mega_lucario').decide) + threat/board probes, this
session. All 14 open mega_lucario corrections routed to terminal ANALYSIS outcomes:
  - covered: 84071010-30 (attack-last + dig-before-commit; reviewed.json).
  - proposal-routed: the 3 clusters below (switch / general fetch / solrock-lunatone) + the planner-code
    `lethal-retreat-enabler` below + the cross-agent planner-code merge into
    blunder-20260709-mega_starmie.md#lethal-recover-the-energy-that-wins (ml frames 84889011-24 /
    84890060-26 / 84890060-48).
  - refuted→reframed: 84071010-15 `revive-the-dead-hand-full-refresh` — re-examined (2026-07-09, per
    data/handoffs/ownside.md §3): f15 is NOT a dead hand but a missed **turn-3 lethal**, so the dead-hand
    detector is refuted for its only fixture and the real gap is reframed into the `lethal-retreat-enabler`
    planner-code record below.
CRITICAL cohort (9, all mega_lucario): 84890060-1, 84889539-87, 84889011-12, 84889539-26 (deck cluster
below), 84071010-53 (general cluster below), 84889539-30 (switch cluster below), 84889011-24 / 84890060-26
(planner-code, merged into the ms lethal-recover proposal), and 84071010-30 (covered). None refuted/gap. -->

## dont-play-switch-for-no-gain
- id: dont-play-switch-for-no-gain
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: Board/Context — a `switch`/self-promote whose incoming body is no better than the
  outgoing (no Energy freed for reuse, no ready attacker promoted, no wall interposed for a doomed Active,
  no retreat-lock escape). Needs a "switch yields no board benefit" predicate (infra-to-build on Board).
- verification_contract: verifier
- provenance: correction 84889539:f30 | fixture tests/fixtures/corrections/ml_dont_switch_for_no_gain_f30.json
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
CRITICAL. Turn 2, SETUP. The agent played **Switch** to trade an **unpowered Riolu for an unpowered
Riolu** — no Energy moved, no attacker promoted, no wall change — "a waste" (human). Both `Play Switch`
[1] and `End turn` [2] score **0**, so the option-index tie-break picks Switch. A self-initiated
Switch (or a discretionary promote) that swaps one body for a board-equivalent one — the incoming body
is not a readier attacker, frees no reusable Energy off the outgoing, interposes no wall for a doomed
Active, and escapes no retreat-lock — is pure tempo waste and should be declined (`End`/other develop
preferred). Add a small NEGATIVE on a no-benefit discretionary Switch so `End` (0) wins the tie. Guard it
so it never suppresses a Switch that DOES gain (promote-a-ready-attacker, free a locked attacker,
interpose a wall, unstick a retreat-lock) — those are the sanctioned switch/retreat motives already in
the retreat cluster. `update-strategy` verifies on the fixture that decide() flips [1]→[2] (End) and that
the beneficial-switch fixtures in the retreat suite are unregressed.

---

## dont-fetch-an-unplayable-evolution-payoff
- id: dont-fetch-an-unplayable-evolution-payoff
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: sound deck oracle (`common/deck_tracker.py` OwnCardModel / Board `own_prizes`) +
  `evolvesFrom`/CardStat evolution chain — "this Stage-N payoff has NO pre-evolution in play AND none
  reachable in the deck, so it cannot be put into play." A fetch/ToHand suppressor keyed on that.
- verification_contract: verifier
- provenance: correction 84071010:f53 | fixture tests/fixtures/corrections/ml_dont_fetch_unplayable_mega_no_riolu_f53.json
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
CRITICAL. Turn 7 Ultra Ball reveal (`ToHand` select). The agent grabbed **Mega Lucario ex** [0] over
**Solrock** [1] — but **every Riolu is already gone from the deck/play**, so a fetched Mega Lucario ex is
a **dead card** (nothing to evolve it from; a Mega ex only enters play by evolving its Basic). All ToHand
options score **0** → index tie-break takes the Mega. General rule (all decks have evolution lines): at a
fetch/ToHand payoff select, **suppress grabbing an evolution-only Pokémon (Stage ≥ 1) whose pre-evolution
is neither in play nor available in the deck** — it cannot be deployed this game. Reuse the same
sound-oracle machinery `dont-tutor-the-held-wincon` / `dont-search-an-empty-deck` already ride
(deck-content certainty from the prize-exact `OwnCardModel`; fall back to `deck_odds` probability when
the tracker is absent, as in a single-frame retest). This is the mirror of the existing
`hold-wincon-dont-shuffle` stand-down on `wincon_in_hand_undeployable` (Mega with no Riolu) — but on the
FETCH side: don't tutor UP an undeployable payoff in the first place. `update-strategy` verifies decide()
flips [0]→[1] on the fixture (note: the single-frame retest lacks the match-scoped tracker, so the deck
oracle runs in probabilistic fallback — the spec must land on a signal that fires under BOTH the
prize-exact tracker and the `deck_odds` fallback).

---

## solrock-lunatone-engine-roles-and-pairing
- id: solrock-lunatone-engine-roles-and-pairing
- source: blunder-buster
- target_layer: deck-strategy
- candidate_signal: mega_lucario role vocab already present (`SOLROCK: [secondary_attacker, engine]`),
  the Cosmic-Beam-needs-Lunatone oracle (models the bench-partner requirement, `dont-cosmic-beam-without-
  lunatone` retired into it), + Board "Lunatone in play" / "Solrock in play" / prize-exact "Lunatone
  reachable" reads. Deck rules at SetupActivePokemon / Main-attach / AttachFrom(Aura Jab) / ToHand fetch.
- verification_contract: verifier
- provenance: corrections 84890060:f1, 84890060:f11, 84071010:f64, 84889539:f87, 84071010:f41,
  84889011:f12, 84889539:f26 | fixtures tests/fixtures/corrections/ml_start_solrock_over_lunatone_f1.json,
  ml_attach_solrock_not_lunatone_f11.json, ml_attach_makuhita_not_lunatone_f64.json,
  ml_aurajab_skip_partnerless_solrock_f87.json, ml_fetch_solrock_for_lone_lunatone_f41.json,
  ml_dont_fetch_redundant_solrock_f12.json, ml_dont_fetch_inert_solrock_prized_lunatone_f26.json
- status: applied
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder):**
Contains 4 CRITICAL corrections. The deck's **Solrock↔Lunatone pair is a one-of-each co-dependent
engine**, and the Pilot mis-plays every seat of it because the existing rules (`fetch-the-engine-first`,
`fire-lunar-cycle`, `dont-lunar-cycle-away-the-last-attachable-f`) don't encode the ROLES or the
one-of-each QUANTITY. Card facts (STRATEGY §0, engine dump): **Solrock** = Cosmic Beam **70 for a single
{F}** but does **NOTHING unless a Lunatone is on your Bench** (the attacker); **Lunatone** = Lunar Cycle
(with Solrock in play, discard a {F} → draw 3; it is the **benched draw engine**, rarely attacks — Power
Gem is {F}{F} 50). Author mega_lucario deck rules across the four seats where this shows up:

1. **SetupActivePokemon — start Solrock, not Lunatone (CRIT, f1).** Both score 0 → index picks Lunatone.
   Prefer the Solrock (attacker role) as the opening Active over Lunatone (engine role) whenever both are
   available; Lunatone belongs on the Bench powering draws.
2. **Main attach — power Solrock (attacker), not Lunatone (engine) (f11, f64).** f11: the agent attached
   {F} to the Active **Lunatone** ([0], `prefer-active-attach-in-setup` +8) over the benched **Solrock**
   ([1]); f64: attached to **Lunatone** over **Makuhita**. Energy goes to the attacker line (Solrock /
   the Mega line / Makuhita→Hariyama), never to Lunatone unless it is the only legal home — Lunatone is
   the draw engine, not an attacker. (Root of f11 is f1: had we started Solrock, `prefer-active-attach-
   in-setup` would already point right — but add the explicit Solrock-over-Lunatone attach preference so
   it holds regardless of which is Active.)
3. **AttachFrom (Aura Jab distribution) — skip a partnerless Solrock; feed the Mega/Riolu line (CRIT,
   f87).** All bench targets tie at `spread-attach-to-the-needy` +15 → index picks Solrock [0]; the human
   wants Riolu [3]. When **no Lunatone is in play**, a Solrock is INERT (Cosmic Beam does nothing), so
   Aura Jab's discard-energy should skip it and load the Riolu→Mega Lucario line (or a Solrock only once
   its Lunatone partner is down). "Solrock is worthless without a Lunatone in play; Lunatone is near-
   worthless without a Solrock in play — write that down" (human).
4. **ToHand fetch — grab the MISSING half, never a redundant/inert one (CRIT f12, CRIT f26, f41).**
   - f41: benched lone Lunatone, Mega safe+energized → **fetch a Solrock** to complete the draw engine
     (all options score 0 today → index misses it).
   - f12 (CRIT): a Solrock is **already in play** → do **not** `fetch-the-engine-first` a 2nd one
     (over-fires +20 on the redundant Solrock); we only ever need one of each in play.
   - f26 (CRIT): both Lunatones are **in the prize cards** (prize-exact reveal) → a fetched Solrock is
     inert until a Lunatone is retrieved, so **fetch the Makuhita** (its Hariyama is in hand) instead;
     `fetch-the-engine-first`+`fetch-a-starter` (32) currently out-scores Makuhita (12).
   Unifying rule: fetch toward **exactly one Solrock + one Lunatone in play**; treat a Solrock as
   valueless while no Lunatone is in play OR reachable (deck-oracle/prize-exact), and vice-versa.

WHY it wins: 4 CRITICAL + 3 supporting corrections, all one coherent engine misunderstanding; the deck
already carries the role tags and the Cosmic-Beam oracle, so this is applying knowledge it has. NOTE
(deck-strategy score-neutrality, ADR-0034): these are role-and-state-gated deck rules; `update-strategy`
should confirm they stay score-neutral off their trigger states and that the general layer isn't the
better home for the generic "start-the-attacker-not-the-engine" / "don't-fetch-a-redundant-in-play-engine-
piece" halves (a role-keyed general rule may generalize — deck-align's call), while the Cosmic-Beam
co-dependency stays deck-specific.

---

## revive-the-dead-hand-full-refresh
- id: revive-the-dead-hand-full-refresh
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `_hand_is_dead` (the full real-menu play-scan, RETIRED 2026-07-03 with
  `refresh-when-hand-is-dead`, doctrine_shuffle_refresh.py:75/150) — rebuild it as the gate that lets a
  full `shuffle_hand` refresh out-rank a marginal alternative dig AND override `attach-before-hand-shuffle`
  when the hand is genuinely dead.
- verification_contract: verifier
- provenance: correction 84071010:f15 | fixture tests/fixtures/corrections/ml_petrel_balloon_retreat_lethal_f15.json
- status: refuted
- for: general

**Spec (authoring spec — thin fodder):**
**REFUTED + REFRAMED (2026-07-09, per `data/handoffs/ownside.md` §3).** The user re-examined f15's exact
state and found the hand is **NOT dead** — f15 is a **missed lethal on turn 3**. There is an
engine-verified this-turn WIN line (a retreat-tool play into a ready benched attacker — see the sibling
record **`lethal-retreat-enabler` below**), so the shuffle-for-8 tag was suboptimal and the dead-hand
detector is refuted for its **only** fixture. **Do not build the dead-hand detector.** The real gap is
the **Lethal Solver going one composition deeper** (the retreat-enabler class), routed to the
planner-code sibling below — `update-strategy` should set THIS record aside (refuted) and work that one.

_Superseded rationale (kept for provenance — the original dead-hand argument, now refuted by the missed
lethal)._ Turn 3, hand read "rather dead" (human), 6 prizes → Lillie's Determination draws 8. Agent
played **Team Rocket's Petrel** [0] (`dig-before-commit` +20) over **Lillie's** [1] (`dig-before-commit`
+20 **−60** `attach-before-hand-shuffle` = −40). The original proposal argued for reviving a dead-hand
detector (the retired `_hand_is_dead` full-menu scan) so a full `shuffle_hand` refresh could out-rank the
marginal Petrel dig and override the stranded attach. That premise is wrong: the hand was never dead — a
WIN was on the table — so no refresh heuristic is the fix; the fix is the solver composing the lethal.
(Sibling 84071010-30 — the same episode's 1-card-hand case — is already COVERED by attack-last +
dig-before-commit.)

---

## lethal-retreat-enabler
- id: lethal-retreat-enabler
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: Lethal Solver generator (`_family_win_candidates`, src/common/strategy/planner.py:294;
  surfaced via `_grab_lethal_tactical`, src/common/pilot.py:1204 — ADR-0030/0037) — a NEW enabler step:
  make the Active's retreat **affordable** via an enabling card play (attach an in-hand retreat **Tool**,
  or first play a Supporter that **tutors** one) → retreat → **promote a ready benched attacker** → attack
  → KO/win. Extends the retreat-to-a-benched-attacker step of
  blunder-20260709-mega_starmie.md#lethal-recover-the-energy-that-wins (which composes the **free/natural-
  retreat + energy-recover** case) to the **retreat-Tool-enabled / tutored-retreat** case one step deeper.
  `live_trace.lethal` was null while a WIN existed.
- verification_contract: verifier
- provenance: correction 84071010:f15 (re-examined 2026-07-09 → missed T3 lethal, per
  data/handoffs/ownside.md §3) | fixture tests/fixtures/corrections/ml_petrel_balloon_retreat_lethal_f15.json
  (state re-verify at source on build; the fixture is named for the retired dead-hand framing) |
  reframes the refuted `revive-the-dead-hand-full-refresh` above | see [[lethal-solver-plan]]
- status: applied
- applied_note: 2026-07-10 deferred, BUILT 2026-07-13 (`retreat_enabler_lethal`). The 2026-07-10 objection is retired: the fixture now carries own_prizes + search_begin_input so the tracker anchors and deck_definitely_has(Air Balloon)=True. `_family_win_candidates` tier 6 recognizes the win + two KO_SCORE grab/attach tacticals steer the cascade (Petrel search -> Air Balloon, attach -> Active) + `_can_retreat` credits an attached retreat Tool. Fixture re-tagged correct=[0], category missed_win. decide() LOCKS the engine-verified win; engine_confirms(f15)=True; counter-fixtures don't regress. See docs/todo/lethal-retreat-tool-enabler.md.
- for: general

**Spec (authoring spec — thin fodder):**
Turn 3, f15. An engine-verified this-turn **WIN** existed that the solver never composed, so
`live_trace.lethal` was null and the agent shuffled instead. Line (engine-verified per the correction;
**re-verify at source on build** — the simulator deltas + CardStat are ground truth, not this record):

> Team Rocket's Petrel → tutor **Air Balloon** → attach to Active **Makuhita** → free-retreat (Air Balloon
> −2 == Makuhita retreat 2) → promote benched **Mega Lucario ex** → **Aura Jab {F} 130 ≥ Riolu 80**,
> opponent bench empty → **WIN.**

The enabling first step is neither an energy recover nor a body that already free-retreats — it is
**playing a retreat Tool** (here Air Balloon, −2 retreat) that zeroes the Active's retreat cost, optionally
**tutored first** by a Supporter (Petrel), after which a ready benched attacker is promoted for the KO.
This is exactly one composition deeper than what ships today:
- `_grab_lethal_tactical` (ADR-0030) handles the **grab-enables-lethal / energy-recover** case.
- `lethal-recover-the-energy-that-wins` (applied) handles retreat-into-a-benched-attacker **when the
  retreat is already affordable** (free-retreat Lunatone / paid) plus the energy fetch.
- **This case adds the retreat-*affordability* enabler**: attach (or tutor-then-attach) a retreat Tool so
  an otherwise-unaffordable retreat becomes free, then promote the attacker.

**Home:** extend the min-bound generator `_family_win_candidates` (planner.py) with a retreat-Tool-enabler
candidate family (surface it via `_grab_lethal_tactical` at the tutor/attach select), cascade-verified like
tiers 3/4 — a refute drops the line, a None verdict keeps the sound coin-floor lock (sound-or-silent;
never lock a phantom).

**NOTE for `update-strategy` (coverage check FIRST).** Before building, confirm whether
`lethal-recover-the-energy-that-wins` (applied) — whose candidate_signal already says "extend the
ko_for_prizes retreat line into the win/KO generator" — **already** composes a Tool-enabled retreat. Its
worked cases are all free/paid-retreat, so this Tool-affordability step is almost certainly NOT yet
composed; if it turns out it is, mark this **covered** rather than building. Then verify decide() takes the
tutor/attach-enabling step and the solver locks the KO on the f15 state.

WHY it wins: an **outright thrown WIN on turn 3** — the highest-value blunder class — and the enabling
primitives (retreat-Tool cost model, promote-a-benched-attacker, the KO oracle) already exist; only the
solver's line-generator is missing the retreat-affordability compose. Single-turn boundary (ADR-0031): the
whole line is one of MY turns; nothing here needs the deferred multi-turn layer.

**update-strategy verdict (2026-07-09): DEFERRED — capability-gap.** The win line is CONFIRMED at source
(Petrel tutors a Trainer → Air Balloon −{C}{C} retreat → Makuhita retreat 2→0 → free-retreat → promote Mega
Lucario ex → Aura Jab {F} 130 ≥ Riolu 80, opp bench empty → WIN). But a SOUND, COMPLETE build is blocked on
unbuilt infra: (1) the follow-up steering (tutor→Air Balloon, play-Tool→Active) is absent and cannot be
authored grounded without probing those engine selects; (2) the f15 fixture carries no `search_begin_input`,
so `_engine_confirms_win`'s cascade is a **no-op** in the unit suite — a closed-form-only retest would prove
RECOGNITION, not real-play COMPLETION (a false-green, [[wroute-satisfied-not-fixed]]). Authoring follow-up
hooks blind into the Lethal Solver — where a phantom win LOSES the game — is the wrong risk (grill 2026-07-09).
**Definition-of-done + the required tool:**
`data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md` — a BROAD engine-backed harness that
seeds `search_begin` from a captured state and drives a whole retreat/tutor/fetch line to the engine's
verdict (+ probes the follow-up selects). It also unblocks the sibling capability-gap
`retreat-to-promote-a-disruptor`. Once the tool exists: reframe the fixture (`correct`→[0], assert `lethal`
non-null), author the generator family + the two follow-up hooks, and gate on the tool.
