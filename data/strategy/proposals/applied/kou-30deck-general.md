<!-- Strategy Proposal queue — general-bucket proposals lifted from the Kou@Pokeka 30-deck Digest.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## unfair-stamp-comeback-posture
- id: unfair-stamp-comeback-posture
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: needs a new signal (opponent property "runs Unfair Stamp") + a board condition "I took a KO this turn" + hand-redundancy
- verification_contract: seed-ladder
- provenance: data/strategy/articles/pokemon_lover_30-deck-strengths-weaknesses/pokemon_lover_30-deck-strengths-weaknesses_strategy.md (general → "Unfair Stamp is the meta's pivot")
- status: applied
- for: general
- resolution (2026-07-14, deferred-cleanup): both blocking signals now exist. (a) The "I took a KO this turn"
  Board condition = `board.opp_took_ko_this_turn`, flattened from the ADR-0047 Resources tracker
  (`took_ko_this_turn`). (b) The opponent property `opp_comeback_disruptor` was MINTED in
  opponent_properties.json and asserted `true` in briefs/dragapult_ex.json (the opponent Dragapult runs
  Unfair Stamp, ACE SPEC id 1080 — docs/matchups/dragapult_ex.md). Defensive posture shipped as
  `unfair-stamp-comeback-posture` (baseline_disruption.py, weight-0 / assumed, SEED(ladder): -18): when I
  took a KO this turn AND the recognized opponent can Unfair-Stamp AND my hand is low, demote further
  hand-emptying. DOUBLE-inert (weight-0 AND γ-gated on a Brief-asserted property). Offensive/user side was
  already COVERED. Enable + ladder-validate to activate.

**Spec (authoring spec — thin):**
Unfair Stamp (ACE SPEC Item #1080, verified in pool) is usable ONLY by a player who had one of their
Pokémon KO'd on the opponent's last turn — a comeback hand-disruptor (shuffle hands, redraw). In THIS
meta it is the *only* strong interaction left, so the field splits into Stamp-users and Stamp-targets and
"survive the one Stamp" usually wins. Actionable doctrine: **when I take a KO on the opponent this turn, I
have just ENABLED their Unfair Stamp next turn — so don't over-commit my hand (leave a recovery out /
don't empty to hand-size-0), and value holding a re-draw.** Symmetrically, as a Stamp-user, bias toward
baiting/accepting a KO so my own Stamp comes online. Why it wins: the entire event meta (all CL Fukuoka
Master Top-4 ran Unfair Stamp) turned on who navigated this correctly.

**update-strategy verdict (2026-07-09):** split into two halves after checking the live feature catalog:
- **Offensive/user side (we PLAY Unfair Stamp): COVERED.** Both `dragapult_ex` and `mega_lucario` already
  run it and sequence it as a post-KO comeback (STRATEGY.md, Shuffle-Refresh doctrine, `aceSpec` discard
  guards). No new authoring.
- **Defensive/target side (opponent plays it against us): CAPABILITY-GAP → deferred.** The posture "I just
  took a KO → opponent is now enabled to Unfair-Stamp me → don't empty my hand, hold a recovery out" needs
  two signals that don't exist: (a) a Board condition **"I took a KO on the opponent this turn"** (not
  exposed), and (b) a Scouting opponent property **"opp runs a post-KO hand-disruptor"** (not in
  `opponent_properties`: only opp_is_engine_dependent / donk_vulnerable / tempo / is_heal_wall /
  accel_dependent / pierces_active_effects / hand_size_attacker / single_prize).
  **Definition-of-done:** add the Board KO-this-turn signal + an `opp_comeback_disruptor` opponent property
  (route its per-archetype assertion to matchup-genie for the 21 opponent Briefs), THEN author the general
  posture Hypothesis (seed-ladder). Until then no deck-agnostic weight is soundly authorable.
