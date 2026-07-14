<!-- Strategy Proposal queue — proposals lifted from the Learn the TCG "Fundamentals" 6-episode Digest.
Source: data/strategy/learnthetcg_fundamentals_strategy.md (handle: learnthetcg / MellowMagikarp).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## attacks-to-win-clock-oracle
- id: attacks-to-win-clock-oracle
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: Match Planner Threat Clock (turns-until-KO, ADR-0045) + prize-path/KO-race (ADR-0040)
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Ahead/behind is measured in attacks-to-win, not prize count")
- status: applied

**Spec (authoring spec — thin):**
The ahead/behind decision must be driven by **attacks-to-win** (how many attacks each player still needs),
re-evaluated every turn — not by raw prizes-taken. A board of all one-prizers can win the race down 6→4.
Almost certainly already covered by the Match Planner Threat Clock + prize-path; this record exists so
update-strategy **confirms the clock is the ahead/behind oracle** (and that it re-derives each turn), and
marks covered rather than adding a weight. If any gap exists it's ensuring the clock is what gates the
play-safe/press-risk mode below.

## risk-scales-with-prize-position
- id: risk-scales-with-prize-position
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: score_diff / prize-lead board condition; the gamble tier (ADR-0039, "safe line loses → take variance")
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Risk scales with prize position")
- status: applied
- resolution (2026-07-14, deferred-cleanup): the net-new AHEAD half shipped as `play-safe-when-ahead-on-prizes`
  (src/common/strategy/baseline/baseline_posture.py, NEW cluster), keyed on `board.opp_prizes_remaining -
  my_prizes_remaining >= 1`. Ships weight-0 / status=assumed (SEED(ladder): -8) — WIRED + trigger-tested
  (tests/strategy/test_deferred_posture_cluster.py) but contributes 0 to the argmax until ladder-validated
  (ADR-0009 by-id override), the conservative default for an opponent-position prior. The BEHIND half stays
  the existing gamble tier (ADR-0039), not re-authored.

**Spec (authoring spec — thin):**
Amount of risk taken should correlate with prize position. **Ahead:** minimise whiff — stabilise (extra
support Pokémon / backup attacker), thin dead cards, and play around the opponent's *only* comeback line
("what would I hate to draw off an Iono? cut it"). **Behind:** gate every big decision on *"do I just lose
anyway?"* — if the safe line also loses, take the low-% line, and never assume the opponent sees the
winning play. Check overlap with the gamble tier (which already models safe-line-loses → variance) and the
Match Planner mode; author only the net-new half (the *ahead* → stabilise-and-thin-and-play-around-their-
one-out posture) if the gamble tier only covers the behind side.

## ko-target-maximise-opponent-whiff
- id: ko-target-maximise-opponent-whiff
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: needs a new signal (opponent rebuild-odds — their outs to a fresh attacker) + Deck-Content-Odds applied to the opponent + KO-Race read (blunder correction #30)
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Pick the KO that maximises the opponent's whiff odds")
- status: applied
- resolution (2026-07-14, deferred-cleanup): UNBLOCKED by the ADR-0047 opponent Resources model
  (`OpponentModel.copies_left_odds` — P(opp deck still holds ≥1 copy), the rebuild-odds estimate this
  proposal called "doesn't exist yet"). Shipped as a KO/snipe-target TIEBREAK in planner.py
  `_ko_key_threat_lines` (key `(rank, -whiff_odds)`), behind the `ko_target_whiff` runtime flag DEFAULT
  OFF. Rank stays dominant → only breaks ties among equal-rank targets, preferring the body the opponent is
  least able to replace. `_whiff_odds` fails OPEN to 1.0 (no confident Read → no reorder). Tests in
  test_deferred_planner_cluster.py. Enable + ladder-validate to activate.

**Spec (authoring spec — thin):**
When behind you win by making the opponent **miss** (boss / attack / KO). Choose the KO target that leaves
them needing the most *specific* cards: weigh KO-the-engine/developer (e.g. their draw-support) vs
KO-the-attacker by how many pieces each forces and how many cards they'll see, consulting their **discard**
for rebuild potential. Likely a **capability-gap**: soundly ranking this needs an opponent *rebuild-odds*
estimate (their outs to a new attacker) that doesn't exist yet — Deck-Content-Odds is currently own-deck
only. Definition-of-done: an opponent-side out-count/odds signal, then the KO-selection tiebreak. Until
then, record as needs-a-new-signal; do not fake a weight.

## disrupt-tailored-hand-dont-hoard-iono
- id: disrupt-tailored-hand-dont-hoard-iono
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: opponent hand-size delta + last-turn action (needs a new signal); Shuffle-Refresh hand-quality gate (ADR-0024) for the "play it unless hand complete" side
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Disrupt a tailored hand; don't hoard your own Iono")
- status: applied
- resolution (2026-07-14, deferred-cleanup): UNBLOCKED by the ADR-0047 opponent Resources model
  (`hand_size_delta` + `last_turn_dumped`, flattened onto Board as `opp_hand_size_delta` / `opp_last_turn_dumped`).
  Side (1) shipped as `disrupt-the-tailored-hand` (baseline_disruption.py) — value a `hand_disruption`
  Supporter when the opponent dumped last turn AND is now down to a small hand (`opp_last_turn_dumped and
  opp_hand_size <= 3`), the MIRROR of the existing `strip-the-stacked-engine-hand` (big-hand). Weight-0 /
  assumed (SEED(ladder): 22), trigger-tested. Side (2) (don't hoard own Iono) is covered by the
  Shuffle-Refresh dead-hand gate (ADR-0024). Enable + ladder-validate to activate.

**Spec (authoring spec — thin):**
Two coupled rules. (1) **Value hand-disruption (Iono) when the opponent has tailored a big hand down to a
few key cards** — especially right after they Ultra-Ball'd away normally-kept cards (they've committed to
the few they held). (2) **Don't *hold* your own Iono hoping they brick** unless (a) near-unwinnable matchup
whose only line is their brick, or (b) your hand already fully sets up and plans next turn. Side (2) maps to
the Shuffle-Refresh dead-hand gate and is likely mostly covered; side (1) needs an opponent **hand-size
delta + last-turn-discard** signal that may not exist → route the missing signal honestly.

## prize-value-board-shaping
- id: prize-value-board-shaping
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: prize CardStat (prize value) + board composition; interpose-cheap-attacker-promote, promote-after-ko-priority
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Shape the board around prize values, two ways")
- status: applied

**Spec (authoring spec — thin):**
Shape the board by prize *value*: (a) **odd-prizing / seven-prize game** — keep a single-prize attacker in
play so the opponent must knock out seven prizes' worth (an extra turn) and is forced to a single prize
(half an Iono; a one-card hand can't Ultra Ball); (b) **single-prize endgame board** — when the opponent is
at two prizes, clear your multi-prize liabilities so they can't take their last two. Both are prize-economy
board-shaping the Interpose/promote systems already touch — update-strategy should check whether the
Match-Planner prize-path already values presenting single-prize bodies, and extend it rather than add a
weight.

## deny-prizes-via-fewer-kos
- id: deny-prizes-via-fewer-kos
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: Match Planner forgo-KO seam (ADR-0045, default ON) gated by score_diff
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Deny prizes/draw by taking fewer KOs")
- status: applied

**Spec (authoring spec — thin):**
Flexible-damage / spread decks can win the race by taking **fewer** KOs: a single-prize turn (so the
opponent's prize count doesn't turn on their Counter Catcher) or **no** KO (so they don't draw off their own
Fezandipiti). This is exactly the Match-Planner **forgo-KO seam** (already default ON). update-strategy
should confirm the seam covers the "deny Counter-Catcher / deny Fez-draw" motives and needs no new authoring.
**HARD GUARD:** a positional forgo must never override a lethal or a losing KO-race — see
forgo-ko-corrections-are-refuted / attack-is-turn-ender-develop-first. Verify that guard still holds.

## discard-triage-keep-floors-and-rank
- id: discard-triage-keep-floors-and-rank
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: discard_eot keep-floors rule (partly built, general-gaps-authored-2026-07-04); add "rank remaining, cut lowest" tiebreak
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Discard triage = three buckets + rank-the-rest")
- status: applied

**Spec (authoring spec — thin):**
Discard selection = three buckets then rank-the-rest. (a) **Easy** — cards wanted in discard, off-matchup
tech, diminishing-returns (Poffin mid/late). (b) **Never** — *last* gusting effect (Boss/Counter Catcher),
*last* recovery (Super Rod/Night Stretcher), live matchup tech. (c) **Need this turn** — found by playing
the turn out mentally first. Rank the leftovers least→most important, cut from the bottom. The keep-floors
half is partly built (`discard_eot`); the net-new piece is the **rank-remaining-and-cut-lowest** tiebreak
so discard choice never falls to option-index. Confirm the last-copy floors cover Boss/Counter-Catcher/
recovery, then add the ranking tiebreak.

## thin-by-playing-not-discarding
- id: thin-by-playing-not-discarding
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: deck-thinning value term on discard-cost cards (order discards dead-in-hand > playable-from-hand); sibling to dont-waste-discard-energy
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Thin by playing dead cards, not discarding live ones")
- status: applied

**Spec (authoring spec — thin):**
When a card must be discarded (Ultra Ball etc.), prefer to **play** the useful ones from hand (Poffin, Nest
Ball) and spend the discard on genuinely dead cards — don't reflexively discard Ultra Ball with Ultra Ball.
Objective: burn the most cards out of the deck **without** discarding a win-piece (thinning raises draw
odds). Author as a discard-ordering value term: dead-in-hand > playable-from-hand > useful/win-piece. Sits
next to the Ignition energy-discipline / `dont-waste-discard-energy` doctrine — check they don't conflict.

## dont-spend-unneeded-supporter
- id: dont-spend-unneeded-supporter
- source: strategy-ingest
- target_layer: general-hypothesis
- for: general
- candidate_signal: needs a new signal — "turn-goal-already-satisfied" predicate over the Turn Planner directed goal + hand completeness
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Don't spend a draw supporter you don't need")
- status: applied (consumer wired) + deferred (sound predicate derivation)
- resolution (2026-07-14, deferred-cleanup): the CONSUMER shipped — hypothesis `dont-spend-unneeded-supporter`
  (baseline_sequencing.py, weight-0 / assumed, SEED(ladder): -15) demotes a draw/gust/rush_evolve Supporter
  when `board.turn_goal_satisfied`. The new Board predicate `turn_goal_satisfied` (pilot.py) exists but is
  populated conservatively **False**: a sound "directed-goal-met" oracle is NOT derivable from current Board
  signals (the Game Plan exposes goal-kind + confidence, not per-mode completion; the "I can attack, so I'm
  done" proxy over-claims and would lose tempo). Per the fail-safe rule the predicate returns False rather
  than fake an unsound True — so the rule is inert until a sound goal-met oracle is authored (DoD:
  a Turn-Planner directed-goal-completion signal). `select` is threaded for that future derivation.

**Spec (authoring spec — thin):**
Playing a draw supporter is **not** mandatory just because it's in hand. If the hand already accomplishes the
turn's goal and there's no dig / disruption / thinning value in drawing, **hold** it — most often save the
Boss's Orders (or a new-evolution supporter) for a later decisive turn. Net-new. Needs a
"turn-goal-already-satisfied" predicate (Turn Planner directed goal met + no card still being searched) so
the payoff is a preserved scarce future resource, not tempo now. May be a small capability-gap if that
predicate isn't exposed — route honestly.

## turn-goal-best-vs-bare-minimum
- id: turn-goal-best-vs-bare-minimum
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: Turn Planner directed goal (ADR-0045 Game Plan) + Threat-Clock delta on the fallback attack; attack-is-turn-ender-develop-first
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Frame each turn as best-possible vs bare-minimum")
- status: applied

**Spec (authoring spec — thin):**
Turn planning = define the **best-possible** turn and the **bare-minimum** the prize map requires, then take
the cheapest line that meets the goal — spend extra cards only when the saved cards genuinely won't matter
later (then playing them *is* thinning). This is the anti-tunnel-vision discipline. **Subpar-attack test:**
after whiffing the intended attacker, use a fallback attack only if it *reduces attacks-to-win* or *eases a
future turn*; otherwise retreat to a one-prizer / draw / pass. Maps onto the Turn Planner's directed goal +
Threat Clock; update-strategy should check the Planner already prefers the min-cost line meeting the goal
and models the fallback-attack test, extending code rather than adding a weight.

## deck-personality-reactivity
- id: deck-personality-reactivity
- source: strategy-ingest
- target_layer: deck-strategy
- for: general
- candidate_signal: each agent's Role / deck-intent (STRATEGY.md) sets a "solitaire vs opponent-filtered" default; opponent-filtered branch consumes the believed archetype (Read)
- verification_contract: score-diff
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (our-deck → "Match your reactivity to the deck you pilot")
- status: applied

**Spec (authoring spec — thin):**
How much a deck should react to the opponent's plan depends on the deck. **Linear/aggressive** decks play
"solitaire" — prioritise own setup, don't over-play-around the opponent. **Disruptive / flexible-damage**
decks filter each decision through the opponent's next turn (single-prize to deny Counter Catcher, forgo a
KO to deny draw). Realised per agent: `mega_lucario` / `mega_starmie` default solitaire; `dragapult_ex`
defaults opponent-filtered. Author as a per-deck STRATEGY.md posture default (score-diff gated, must stay
neutral where the deck is already correct); the opponent-filtered branch reuses the Read's believed
archetype. Not a general weight — it's a deck-intent knob.

## deck-knowledge-bottom-tracking-and-opponent-resources
- id: deck-knowledge-bottom-tracking-and-opponent-resources
- source: strategy-ingest
- target_layer: planner-code
- for: general
- candidate_signal: own side — deck_tracker.py / deck_odds.py (built, sound-deck-emptiness-oracle + deck-content-odds); opponent side — needs a new signal (opponent discard/resource + prized-count model)
- verification_contract: seed-ladder
- provenance: data/strategy/learnthetcg_fundamentals_strategy.md (general → "Exploit known deck contents on both sides")
- status: applied
- resolution (2026-07-14, deferred-cleanup): the OPPONENT side (called "doesn't exist" here) is UNBLOCKED by
  the ADR-0047 opponent Resources model. Shipped `opp_deckout_in_turns` (flattened onto Board from the SOUND
  deck-count trajectory) consumed by a planner deck-out grind nudge (`_deckout_grind_bonus`, sub-prize
  `_PLANNER_DECKOUT_W=5`) on both KO rungs, behind the `opp_resource_reads` runtime flag DEFAULT OFF. The
  finer prized-last-copy read stays probabilistic (opp hand hidden) and is deliberately NOT used — documented
  in-comment. The OWN side (bottom-tracking / no-shuffle-to-guarantee) is already built (deck_tracker /
  deck_odds). Enable + ladder-validate the grind nudge to activate.

**Spec (authoring spec — thin):**
Exploit known contents both ways. **Own deck:** track cards sent to the *bottom* with Iono and the thinned
late-game deck (you can know your bottom ~10); sequence shuffle vs no-shuffle to *guarantee* an out (e.g.
draw down to a two-card deck so the last Counter Catcher is certain; a "thin" that could shuffle away your
guaranteed out is not a thin). This side is largely built (`deck_tracker.py`/`deck_odds.py`) — confirm the
Planner uses no-shuffle-to-guarantee sequencing and mark covered. **Opponent deck:** track their discard /
resource counts / prized copies for exact endgame deck-out and play-around-the-last-copy lines — this needs
an opponent resource model that doesn't exist → needs-a-new-signal / capability-gap.
