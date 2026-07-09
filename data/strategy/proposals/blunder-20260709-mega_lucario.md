<!-- Strategy Proposal queue — blunder-buster round 2026-07-09 (mega_lucario).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Routing evidence: real-Pilot retests (tune._build_pilot('mega_lucario').decide) + threat/board probes, this
session. All 14 open mega_lucario corrections routed to terminal ANALYSIS outcomes:
  - covered: 84071010-30 (attack-last + dig-before-commit; reviewed.json).
  - proposal-routed: the 4 clusters below + the cross-agent planner-code merge into
    blunder-20260709-mega_starmie.md#lethal-recover-the-energy-that-wins (ml frames 84889011-24 /
    84890060-26 / 84890060-48).
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
- status: open
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
- status: open
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
- status: open
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
- provenance: correction 84071010:f15 | fixture tests/fixtures/corrections/ml_dead_hand_full_refresh_f15.json
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
Turn 3. Hand is "rather dead" (human) with **6 prizes remaining → Lillie's Determination draws 8**. The
agent played **Team Rocket's Petrel** [0] (a Trainer tutor, `dig-before-commit` +20) over **Lillie's**
[1] (`dig-before-commit` +20 **−60** `attach-before-hand-shuffle` = −40). The 2026-07-03 retirement of
`refresh-when-hand-is-dead` + its `_hand_is_dead` full-menu scan assumed the +20 `dig-before-commit`
alone carries a dead-hand refresh "when nothing else is endorsed" — but here **something else IS
endorsed** (Petrel, another +20 dig) AND `attach-before-hand-shuffle` (−60, a reusable {F} with a
placeable home) sinks the refresh below it. So the refresh loses to a marginal one-card tutor and a
stranded attach. Revive a dead-hand detector: when the full real-menu play-scan finds **no useful line
to build this turn** (the hand is genuinely dead) AND the shuffle draws a large fresh hand, the full
`shuffle_hand` refresh should out-rank a marginal alternative dig and OVERRIDE `attach-before-hand-
shuffle` (8 fresh cards beats attaching one {F} and tutoring one Trainer). Keep it narrow (a real
dead-hand scan, not a blanket refresh preference) so it never fights `hold-wincon-dont-shuffle` /
`hold-line-piece-dont-shuffle` / `dont-refresh-into-a-probable-miss` on a live hand. `update-strategy`
verifies decide() flips [0]→[1] on the fixture and that the shuffle-refresh suite (the hold/miss cases)
is unregressed. (Sibling 84071010-30 — the same episode's 1-card-hand case — is already COVERED by
attack-last + dig-before-commit; this is the harder case where a competing dig defeats the bare +20.)
