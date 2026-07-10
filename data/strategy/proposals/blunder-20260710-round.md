<!-- Strategy Proposal queue — blunder-buster round 2026-07-10 (ALL agents).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md

SCOPE. `tune.py` (no --agent) over the whole log. Open set at run start:
  mega_lucario  — 14 NEW corrections (store mega_lucario_20260709_e2f0a07-dirty), 8 CRITICAL.
  mega_starmie  — 4 UNSATISFIED (no open proposals).
  dragapult_ex  — 1 open + 4 UNSATISFIED, ALL already proposal-routed by
                  blunder-20260709-dragapult_ex.md (f6/f10/f14/f18/f21/f31/f32/f79/f81/f85). No new work.

METHOD. Every correction was re-measured through the REAL Pilot `decide()` — never the W-route
"satisfied" count ([[wroute-satisfied-not-fixed]]). tune.py reported 26/34 W-satisfied for mega_lucario
and SKIPPED f88 as "tactical"; the decide() sweep shows 13 of the 14 still blunder on the shipped agent
(only f109 is degenerate, chosen==correct). The weight deltas tune.py fitted for the "satisfied" frames
(e.g. power-up-attacker 15 -> 3.22, grab-a-draw-supporter-in-setup 10 -> 4.0) are MIS-FITS: they sand down
general rules for every deck without fixing any of these frames. update-strategy should author the roots
below and DROP those nudges.

THE ROOT (why the general layer keeps missing on this deck). Three seams the earlier two decks never
exercised:
  1. NON-ENERGY ATTACHES. mega_lucario is the first deck with a non-HP Tool (Air Balloon, retreat -2).
     `power-up-attacker` fires on ANY OptionType.ATTACH, so a Tool is scored as an Energy attach.
     The Tool Doctrine (ADR-0028) only models +HP tools; Air Balloon isn't even `tool`-tagged.
  2. NON-ATTACKING BODIES. It is the first deck whose board carries pure engine bodies (Lunatone) and a
     2-prize tutor (Meowth ex) alongside real attackers. `power-up-attacker`'s `attach_target_needs`
     is "carries fewer Energy than its cheapest attack cost" — which RANKS THE NON-ATTACKER HIGHEST
     (Meowth ex needs 3, a live Riolu needs 0). Same shape as dragapult's Dunsparce (f21).
  3. CONDITIONAL / SELF-LOCKING ATTACKS. Cosmic Beam does nothing without a benched Lunatone
     (`requiresBench`); Mega Brave and Accelerating Stab lock themselves for a turn. The Lethal Solver's
     generator family has no "bench the enabler" arm, and `active_attack_payable` is energy-math-only,
     so it can't see a transient lock.

CARD FACTS verified at source (data/EN_Card_Data.csv, docs/rules.md) — do NOT trust the tags:
  Aura Jab {F} 130 + attach up to 3 Basic {F} from discard to the Bench.  Mega Brave {F}{F} 270,
  "during your next turn this Pokémon can't use Mega Brave".  Cosmic Beam {F} 70, "if you don't have
  Lunatone on your Bench, this attack does nothing".  Lunar Cycle: needs Solrock in play, discard a Basic
  {F} from hand -> draw 3.  Accelerating Stab {F} 30, self-locks next turn.  Air Balloon: Tool, retreat
  cost -{C}{C}.  Premium Power Pro: THIS turn, {F} attacks do +30.  Poké Pad: search a non-Rule-Box
  Pokémon.  Fighting Gong: search a Basic {F} Energy OR a Basic {F} Pokémon.  Munkidori 110 HP,
  RESISTANCE {F} (rules.md L116: -30 per the printed amount; every probed card is -30) — so Aura Jab
  hits it for 100 (no KO) and Mega Brave for 240 (KO). Retreat costs Energy equal to the printed cost
  (rules.md L89), so a 0-Energy Meowth ex (retreat 1) CANNOT retreat.
-->

## lethal-bench-the-attack-enabler
- id: lethal-bench-the-attack-enabler
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: `AttackStat.requiresBench` + `damage.py` `context["atk_bench_names"]` (both exist); `Board.search_deck_ids` / `deck_definitely_has` for tutor certainty
- verification_contract: verifier
- provenance: correction 85058051:f13 (mega_lucario, CRITICAL) | fixture tests/fixtures/corrections/ml_lethal_bench_the_attack_enabler_f13.json | [[lethal-solver-plan]]
- status: applied
- applied_note: 2026-07-10 Pilot._grab_enabler_lethal_tactical. f13 PASS (tactical >= KO_SCORE). Bound note: damageMin is 0 for a requiresBench attack (the clause IS the conditional), so the lock reads exact damage behind a new _attack_is_deterministic guard.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
A guaranteed win was on the board and `live_trace.lethal` was `null`. Board (turn 3): my Solrock is Active
with one {F} attached (Cosmic Beam {F} 70 is affordable); the opponent's ONLY Pokémon is a 70/70 Staryu
with an empty Bench. Ultra Ball was already in play and its search pool revealed Lunatone. Fetch Lunatone
-> bench it -> Cosmic Beam's `requiresBench` condition is satisfied -> 70 KOs the Staryu -> the opponent
has no Pokémon to promote -> **we win**. The Pilot grabbed a Riolu instead (`fetch-base-before-stranded-
payoff` +20 / `prefer-wincon-line-piece` +18 out-scored Lunatone's +32).

The win rung already models the bench-out win (`Planner._attack_wins`: `active_ko and not board.opp_bench`)
and the damage oracle already zeroes a `requiresBench` attack whose partner is absent. What is missing is a
generator arm: **no candidate in `_family_win_candidates` ever puts a body onto my Bench.** Every develop
tier is attach / retreat / evolve-active / gust / energy-tutor / evolution-tutor.

Add the enabler arm, in both places it can pay:
- at the MAIN menu — a `_PLAY` of a Basic from hand, or of a `tutor_pokemon` Item whose target is
  deck-certain (tracker positive certainty, never the probabilistic estimate), when benching that body
  makes my Active's `requiresBench` attack legal AND that attack's min-bound damage wins
  (`_develop_wins`);
- at the `TO_HAND` grab select — the sibling of `Pilot._grab_lethal_tactical` (which today only recognises
  a KO-enabling **Energy** grab): a grabbed **body** that, once benched, unlocks the winning attack.
  This is the seam the human tagged, and it is the gating fixture.

Soundness is the same standard as the rest of the family: benching a Basic is unconditional given a free
Bench slot, the attack is already affordable, `requiresBench` is a modeled condition, and the win test is
the existing min-bound `_develop_wins`. Only lock when the enabler is CERTAIN (in hand, or revealed in this
search's pool) — a probable fetch is never a win.

## dont-wake-the-giant-with-the-self-locking-ko
- id: dont-wake-the-giant-with-the-self-locking-ko
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: `AttackStat.nextTurnSameAttackLock` / `.nextTurnSelfLock`, `Pilot._lock_cost_applies`, `Pilot._boost_lethal_tactical`, `Planner._opp_after_forced_promote`, `Planner._threat_clock`, `strategy.params["reactivity"]`
- verification_contract: verifier
- provenance: corrections 85058574:f88 (mega_lucario, CRITICAL), 84889539:f48 (mega_lucario, `ignored_threat` — the frame tune.py has been SKIPPING as "tactical") | fixtures tests/fixtures/corrections/ml_dont_wake_the_giant_with_the_locking_ko_f88.json, ml_dont_wake_the_giant_boost_ko_f48.json | tensions with [[forgo-ko-corrections-are-refuted]] — read the argument below
- status: applied
- applied_note: 2026-07-10 Planner._lock_free_attack_line + _opp_active_pinned + _ko_wakes_an_unanswerable_body. f88 + f48 PASS with planned.goal == 'forgo_ko'. The line has its OWN gate: _forgo_ko_gate demands a BUILD-mode plan and both frames are RACE. Solitaire skip retained for the develop/END lines only, per the human's ruling.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
Turn 8. My Mega Lucario ex (2{F}) is Active. Their Active is a 110 HP Munkidori that **resists {F}**;
their Bench holds a fully-energized Dragapult ex (320 HP, Phantom Dive 200). Mega Brave (240 after
resistance) is the only KO — and it locks itself for my next turn, which is exactly the turn the KO
force-promotes the Dragapult. Aura Jab (100 after resistance) doesn't KO but loads up to 3 Basic {F} from
my discard onto the Bench (I have 3 there) and keeps Mega Brave live. The Munkidori cannot escape: 0
Energy, retreat 1 — so the prize is deferred one turn, not forgone. The Pilot took Mega Brave
(`tactical` 1000.5 vs 324.9; `_LOCK_COST` = 40 is a rounding error against `KO_SCORE`).

This is a KO-forgo correction, which the ledger says are usually refuted ([[forgo-ko-corrections-are-refuted]]:
"a positional WEIGHT must never override a KO"). It survives that test on two grounds: **(a)** it is not a
weight — a `when()` can never out-score `KO_SCORE`, so the fix must be a Planner rung, exactly as that
memory prescribes; **(b)** it does not trade the prize away, it re-sequences which attack banks it. The
cheap lock-free attack cashes the same prize next turn while the expensive one stays loaded for the body
the KO wakes.

**The same doctrine, a second time, from an earlier round: correction 84889539:f48** — "KOing the Hariyama
makes sense, however, now we awaken the opponents beast of a Mega Lucario with 440 HP … better to attack
but NOT KO, in this very particular situation." There my Aura Jab reaches the 150 HP Active only *with* a
Premium Power Pro (+30), and `_boost_lethal_tactical` scores the **Premium Power Pro play** at 1000.9 while
the bare Aura Jab sits at 74.9. The human wants the bare Aura Jab. `tune.py` has been silently filing this
frame under `skipped: tactical` every round — it is not unbuildable, it is the same rung
([[skipped-frames-need-retest-triage]]).

Three defects to author against, all in `Planner._forgo_ko_line` / `_forgo_ko_gate`:
1. **The rung can only develop or END.** It has no way to say "attack, but with the other attack". Add an
   alternative-attack line: when the KO-ing attack self-locks (`nextTurnSameAttackLock` / `nextTurnSelfLock`)
   or is only reachable through a consumable boost, a lock-free/unboosted attack is affordable, and the
   forced-promote hypothetical (`_opp_after_forced_promote`) brings up a body whose Threat Clock is strictly
   worse than the current Active's, commit that attack instead. Require the deferred KO to stay bankable —
   their Active can't retreat away (0 Energy vs its retreat cost) or is otherwise pinned — so the prize is
   deferred, never surrendered. (f88: Munkidori, 0 Energy, retreat 1. f48: Hariyama, retreat 3, 1 Energy.)
2. **The rung cannot see a KO that isn't an ATTACK option.** Its first guard is
   `any(o["type"] == _ATTACK and t.tactical >= KO_SCORE)`. At f48 the KO_SCORE-class option is a `_PLAY`
   (the damage-boost Trainer, priced by `_boost_lethal_tactical`), so the rung returns None before the gate
   is ever consulted. Widen the guard to any KO_SCORE-class option, matching how `_finish_turn_last` already
   treats boost/attach lethals.
3. **`reactivity == "solitaire"` blanket-skips the rung**, and mega_lucario declares `solitaire`. That skip
   is right for the *tempo* concession the rung offers today (spend the turn developing instead of
   attacking). It is wrong for the alternative-attack line, which costs no tempo — you still attack, you
   still develop (Aura Jab's bench-load IS the deck's energy engine). Exempt the alternative-attack line
   from the solitaire skip; keep the skip for the develop/END lines.

Related but distinct from the forced-promotion snipe read (ADR-0044): that one pre-chips the body they
will promote; this one declines to summon it early with the wrong attack.

## no-phantom-grab-lethal-check-the-retreat-and-the-necessity
- id: no-phantom-grab-lethal-check-the-retreat-and-the-necessity
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: `CardStat.retreat` + attached Energy (retreat affordability — needs a new `can_retreat` helper); `Board.reusable_energy_in_hand`; `Pilot._best_affordable_ko_value` called WITHOUT the grabbed unit (the necessity test)
- verification_contract: verifier
- provenance: correction 85059103:f39 (mega_lucario, CRITICAL) | fixture tests/fixtures/corrections/ml_phantom_grab_lethal_unretreatable_active_f39.json | [[lethal-solver-plan]]
- status: applied
- applied_note: 2026-07-10 three preconditions on the retreat branch (Pilot._can_retreat / necessity / marginality). f39 PASS with no option claiming a lethal; counter-fixtures ml f48, ml f26, ms f110 still lock. Also gated fetch-base-before-stranded-payoff on `not wincon_in_play` so the engine half wins the grab.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
`Pilot._grab_lethal_tactical` scored every Basic {F} Energy in a Fighting Gong search at
`KO_SCORE + prize` = **1001**, burying the Solrock the human wanted (`fetch-the-missing-engine-half`, 20).
The "lethal" is a phantom, and it is a soundness bug in a KO_SCORE-class tactical — the class the docstring
promises is "min-bound SOUND like the Lethal Solver's closed-form locks".

The board (turn 5): my Active is a 0-Energy **Meowth ex** (retreat cost 1); my benched Mega Lucario ex
already carries 2{F}. The tactical's fallback branch — "retreat into a benched attacker, then attach" —
fired on the Mega. Three independent reasons it cannot happen:
1. **The retreat is illegal.** Retreat costs Energy equal to the printed cost (docs/rules.md L89). A
   0-Energy Meowth ex cannot retreat this turn. The branch never checks retreat affordability.
2. **The grab is unnecessary.** Aura Jab costs one {F}; the benched Mega already has two. The KO exists
   with or without the fetched Energy. The branch tests `kos(energies + 1)` and never `kos(energies)`.
3. **The Energy is already in hand.** Two Basic {F} sit in hand (`reusable_energy_in_hand`), so the grab
   is not the source of the attach even if the line were legal.

Author all three as preconditions on the retreat-into-a-benched-attacker branch: retreat must be
affordable this turn (or a free-switch effect is in hand); the KO must NOT already be reachable at the
body's current Energy; and the grab must be the marginal Energy (no reusable Energy already in hand). Any
one of them is enough for f39, but a KO_SCORE-class claim should carry all three. The Active-attach branch
above it is unaffected (no retreat, and it is the marginal attach by construction) — do not weaken it.

## dont-fund-the-non-attacking-engine-body
- id: dont-fund-the-non-attacking-engine-body
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Context.attach_target_roles` (exists at ATTACH; **needs a new signal at `ATTACH_FROM`**), the `supporter_tutor` / `draw` Function Tags, `CardStat.maxDamage == 0`
- verification_contract: verifier
- provenance: corrections 85058574:f121 (mega_lucario, CRITICAL), 85059103:f84 (mega_lucario), 85046350:f21 (dragapult_ex, CRITICAL — cross-agent; also carried by blunder-20260709-dragapult_ex.md `energy-color-and-attach-target-discipline`, whose attach-target half this SUBSUMES) | fixtures tests/fixtures/corrections/ml_aurajab_dont_load_the_engine_f121.json, ml_dont_energize_the_supporter_tutor_f84.json, dragapult_dont_feed_draw_engine_f21.json
- status: applied
- applied_note: 2026-07-10 general `dont-fund-the-non-attacking-body` (-12) over Pilot._is_utility_body, at BOTH attach seams. ml f121 + ml f84 + dragapult f21 PASS. mega_lucario's `dont-attach-to-the-engine` RETIRED (folded). Also fixed _attach_from_concentrate_slot to consider only bodies the select offers (Aura Jab loads the Bench only).
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
Energy must never go to a body whose job is to draw or tutor, while a real attacker can take it. Three
frames, three seams, one root — and the root is that `power-up-attacker` (+15) fires on
`attach_target_needs`, i.e. *"carries fewer Energy than its cheapest attack cost"*, which **ranks the
worst body highest**: a Meowth ex needing 3 for Tuck Tail out-scores a Riolu that is already online.

- **f121 (CRITICAL)** — Aura Jab's `ATTACH_FROM` bench-load. All five bench bodies tied at
  `spread-attach-to-the-needy` +15, so the option index picked **Lunatone**, the pure draw engine. The
  deck's own `dont-attach-to-the-engine` (-12) is gated `option_type == _ATTACH` and cannot see this
  select; `aurajab-load-the-wincon-line` needs a line **pre-evo** and the Riolu had already evolved.
  Correct: the benched Mega Lucario ex.
- **f84** — a MAIN attach. `power-up-attacker` fired on **Meowth ex** (+15, needs 3) and stood silent on
  the Riolu the human wanted (already online at 1{F}, needs 0). Meowth ex deliberately carries **no
  Role** (STRATEGY.md §3), only the `supporter_tutor` tag — so the role-keyed guard misses it.
- **dragapult f21 (CRITICAL)** — the identical shape on Dunsparce/Dudunsparce.

Author one general suppressor that covers **every attach seam** (`OptionType.ATTACH` and
`SelectContext.ATTACH_FROM`, which needs the attach-target Context fields plumbed to the latter) and keys
on *"this body does not attack"* rather than on one deck's Role string: an `engine`-only Role, or the
`supporter_tutor` / `draw` tags, or `CardStat.maxDamage == 0`. Keep it below `power-up-attacker` so a lone
engine body still takes the Energy when it is the only legal home (`dont-attach-to-the-engine`'s existing
-12 calibration). Pair it with a positive ranking at `ATTACH_FROM` — accelerator payload goes to the
win-condition/attacker bodies first — so the seam stops resolving on option index.

Separately, consider whether `attach_target_needs` should be *"needs Energy AND has an attack worth
funding"*: as written it is an anti-signal on any board carrying a non-attacker.

## a-tool-attach-is-not-an-energy-attach
- id: a-tool-attach-is-not-an-energy-attach
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: the `tool` Function Tag is **MISSING on Air Balloon (card 1174)**; `CardStat.hpBonus`; **needs a new signal** `Context.attach_is_energy` (and a retreat-reduction CardStat field)
- verification_contract: verifier
- provenance: corrections 85058574:f87 (mega_lucario, CRITICAL), 85058051:f4 (mega_lucario) | fixtures tests/fixtures/corrections/ml_air_balloon_on_the_active_f87.json, ml_air_balloon_no_retreat_plan_f4.json | [[tool-deploy-doctrine-reversed]]
- status: applied
- applied_note: 2026-07-10 CardStat.retreatReduction + Context.attach_is_energy + Air Balloon tagged `tool`; every Energy hypothesis gated. PARTIAL: f4 gates as the human ruled (the Tool blunder is gone; the Pilot attaches Energy, not the tagged Ultra Ball). f87's rule is unit-gated on scores, because the new forgo-KO rung now commits Aura Jab at that exact frame.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
Air Balloon (Pokémon Tool: the holder's Retreat Cost is {C}{C} less) is scored by the **Energy** attach
hypotheses, because it arrives as an `OptionType.ATTACH` and nothing tells the Pilot it isn't Energy.
`power-up-attacker` (+15) and `attach-energy-last` (-5) both fire on it; `attach-solrock-over-line-base`
(+3) then breaks the tie toward a benched Solrock.

- **f87 (CRITICAL)** — Air Balloon attached to a **benched** Solrock. A retreat-cost tool only does work on
  the body that retreats. Correct: the Active Mega Lucario ex.
- **f4** — turn 1, Air Balloon burned on the Active Solrock with no retreat in the plan; the human wanted
  Ultra Ball played instead (fetch Lunatone, then discard an Energy to Lunar Cycle for 3 cards).

Two things to author.
1. **Infra (build at apply time, not a capability-gap):** tag Air Balloon `tool` in
   `src/common/card_functions.json` — it is absent today, so ADR-0028's Tool Doctrine never sees it, and
   `_is_hp_tool` would reject it anyway (`hpBonus == 0`). Expose an `attach_is_energy` (or
   `attach_card_is_tool`) Context field so the Energy hypotheses — `power-up-attacker`,
   `attach-energy-last`, `dont-waste-off-type-energy`, `attach-solrock-over-line-base`,
   `dont-attach-to-the-engine` — all stand down on a Tool attach. That alone removes the +15/+3 that
   chose the benched Solrock.
2. **Doctrine:** a retreat-reduction tool belongs on the body that will retreat — the Active by default
   (or the body a planned promote will make Active) — and is worth playing only when a retreat is wanted:
   a high-retreat Active we intend to swap out, or a `swap-out-the-locked-attacker` plan. Otherwise hold
   it (it is `cost_discard` fodder for Ultra Ball, the human's f4 point). ADR-0028's `_tool_deploy_slot`
   is the natural home, extended past `_is_hp_tool` to a second tool class.

f4 has a second, weaker half: Ultra Ball scored **-12** because `dont-shed-a-live-card` (-20) outweighs
`fetch-when-it-fills-a-need` (+8) on a 7-card turn-1 hand holding two spare Supporters. Fixing (1) makes
the Energy attach win the frame, not the Ultra Ball, so the correction's `correct=[1]` will still not be
reproduced by the fixture — flag it: either widen this proposal to soften `dont-shed-a-live-card` when the
fetch target is a needed engine piece and the hand is fat, or accept f87 as the gating fixture and record
f4 as partially addressed. The human's own rationale says the Energy attach "was a good move", so the
observed blunder (the Tool) is what must disappear.

## dont-buff-an-attack-you-cannot-use
- id: dont-buff-an-attack-you-cannot-use
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Board.active_attack_payable` (exists, energy-math only) must consult the ADR-0033 transient-lock tracker — `Pilot._active_best_attack_locked` / `_transients.grant_for_serial` — or, simplest, the absence of any `OptionType.ATTACK` on the menu
- verification_contract: verifier
- provenance: correction 85058574:f69 (mega_lucario, CRITICAL) | fixture tests/fixtures/corrections/ml_ppp_attack_transient_locked_f69.json
- status: applied
- applied_note: 2026-07-10 Board.active_attack_payable now consults the transient lock AND the engine's own menu (Pilot._attack_impossible_on_menu) — the ADR-0033 tracker is match-scoped and cannot survive a single-frame retest. f69 PASS.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
`dont-play-damage-boost-when-cant-attack` (-12) already exists and is exactly the right rule; its gate
`not active_attack_payable` is what fails. My Active was a Riolu holding one {F}, and its only attack —
Accelerating Stab {F} — self-locked when it was used last turn ("During your next turn, this Pokémon can't
use Accelerating Stab"). The engine offered **no ATTACK option at all** on that menu: the choices were
Premium Power Pro, Team Rocket's Petrel, End turn. `_active_attack_payable` reads energy vs
`minAttackCost`, sees 1 >= 1, returns True, and the guard stands down. Every option scored 0.0, so the
option index played the Premium Power Pro — a this-turn-only +30 that expired having buffed nothing.

Author: `active_attack_payable` must be False when the Active's affordable attacks are all
transient-locked. The lock is already tracked (`_active_best_attack_locked` reads
`_transients.grant_for_serial`, serial-gated so it expires on a swap); it currently answers only "is the
BEST attack locked", so it needs a companion "are ALL affordable attacks locked". A menu-derived fallback
("no ATTACK option present") is a sound belt-and-braces check at MAIN.

Secondary, same frame: Team Rocket's Petrel (the human's `correct`) scored 0.0 because
`demote-needless-search-supporter-in-setup` (-20) exactly cancels `dig-before-commit` (+20). With the
Premium Power Pro correctly demoted below End, the three-way 0.0 tie still resolves on option index. The
Petrel here has a real target (see `grab-what-advances-the-plan`, below) — check that the demotion's
"needless" test looks at whether the search has something worth finding.

## grab-what-advances-the-plan-not-a-redundant-supporter
- id: grab-what-advances-the-plan-not-a-redundant-supporter
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: **needs two new signals** — `Context.card_is_hand_duplicate` (an identical copy already in hand; the fetch-side mirror of the shipped `discard-the-hand-duplicate`) and `Board.supporter_played` (the turn's Supporter is spent)
- verification_contract: verifier
- provenance: corrections 85059103:f9 (mega_lucario, CRITICAL), 85058574:f71 (mega_lucario) | fixtures tests/fixtures/corrections/ml_dont_grab_a_hand_duplicate_supporter_f9.json, ml_grab_the_playable_item_f71.json | [[sound-deck-emptiness-oracle]]
- status: applied
- applied_note: 2026-07-10. General halves (pass 1): `dont-grab-a-card-already-in-hand` (-12) + `grab-what-i-can-play-this-turn` (-12) over new Board.supporter_played / Context.card_already_in_hand / card_unplayable_this_turn. Deck half (pass 2, human-authorised): mega_lucario `grab-lunar-cycle-fuel` (+8) -- Lunar Cycle's cost is a Basic {F} DISCARDED FROM HAND, which the general layer cannot model. f71 PASS. f9 PARTIAL: the tagged blunder (fetching a duplicate Lillie's) is gone, but the Pilot now takes a Judge rather than the human's Petrel -- the Petrel-over-Judge read is a tutor-chain judgment the proposal never supplied.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
`grab-a-draw-supporter-in-setup` (+10) fires on every draw Supporter in a search pool and is blind to
whether that card is *worth taking*. Two frames, two different disqualifiers:

- **f9 (CRITICAL)** — Meowth ex's Last-Ditch Catch (Supporter tutor), turn 1. Hand already holds a Lillie's
  Determination. The pool offers three more Lillie's and two Judge (each +10) and one Team Rocket's Petrel
  (0.0). The Pilot took a **duplicate Lillie's**. The human wanted Petrel, whose Trainer tutor opens the
  real chain (Petrel -> Fighting Gong -> Solrock -> Lunar Cycle draws 3). Rule: don't tutor a card an
  identical copy of which is already in hand. `dont-fetch-the-redundant-piece` covers redundancy **in
  play**; this is redundancy **in hand**, and the shipped `discard-the-hand-duplicate` proves the signal is
  wanted on the other side of the same axis.
- **f71** — Team Rocket's Petrel resolving with a dead hand (0 cards). The pool offers Lillie's (+10),
  Fighting Gong (0.0), Premium Power Pro, Ultra Ball. The Pilot took Lillie's — **a Supporter, on the turn
  its own Supporter slot was just spent by Petrel**, so it cannot be played until next turn. Fighting Gong
  is an Item: play it now, fetch a Basic {F}, discard it to Lunar Cycle, draw 3. Rule: at a search, a card
  that cannot be played this turn loses to one that can, when the playable one advances the plan.

One suppressor per disqualifier, both scoped to the grab (`SelectContext.TO_HAND`), sized to cancel the
+10 rather than to invert the whole fetch order.

## dont-play-a-search-item-with-nothing-to-find
- id: dont-play-a-search-item-with-nothing-to-find
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Board.my_bench` vs the 5-slot cap (**needs a `bench_full` signal**); the `tutor_pokemon` Function Tag is **MISSING on Poké Pad (card 1152)** — it carries only `search`
- verification_contract: verifier
- provenance: correction 85058574:f114 (mega_lucario, CRITICAL) | fixture tests/fixtures/corrections/ml_dont_play_a_needless_pokemon_tutor_f114.json | [[sound-deck-emptiness-oracle]]
- status: refuted
- applied_note: 2026-07-10 NOT AUTHORED — the spec does not survive the board. At f114 the Bench is full but Poke Pad can still fetch a Hariyama that evolves the benched Makuhita, so 'nothing to find' is false; and satisfying the tagged correct=[1] would also require suppressing a reasonable Fighting Gong. Needs a human retag (the human's real reason is 'Poke Pad is Ultra Ball fodder', a value judgment). CRITICAL — see the run report.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
Turn 10, my Bench is **full** (5 bodies) and my hand already holds a Solrock, a Meowth ex and a Mega
Lucario ex. Poké Pad searches for a non-Rule-Box Pokémon — there is nowhere to put one and nothing it
could find that I need. `dig-before-commit` (+20) fires on it anyway (it is `search`-tagged and not
`cost_discard`), so it beat every other option. The human's point: Poké Pad is the perfect **Ultra Ball
discard fodder**; spending it for a dead search throws the fodder away.

Note the `reordered = True` marker on this frame. The human's `correct` is the Energy attach onto the
Active Mega Lucario (score 98), and it lost only because `attach-energy-last` deliberately defers the
attach to the end of the turn — that reorder is by design and must NOT be "fixed". The blunder is that
Poké Pad, not End/Fighting Gong, filled the pre-attach window.

Author: `dig-before-commit` (and `fetch-when-it-fills-a-need`) must stand down on a **Pokémon tutor**
whose product has no legal home — the Bench is full and no in-hand evolution wants the fetched body — and
on any search whose pool cannot satisfy a current need. Infra to build first: tag Poké Pad `tutor_pokemon`
(Ultra Ball already carries it), and expose a `bench_full` board signal. The general `search`-tag boost is
too coarse to distinguish a draw dig from a body tutor.

## open-with-an-attacker-not-the-pure-engine
- id: open-with-an-attacker-not-the-pure-engine
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Context.roles` at `SelectContext.SETUP_ACTIVE_POKEMON`; mirrors the shipped `dont-open-multiprize-active` (-15)
- verification_contract: verifier
- provenance: correction 85059103:f1 (mega_lucario) | fixture tests/fixtures/corrections/ml_open_with_an_attacker_not_the_engine_f1.json | supersedes the deck rule `start-solrock-over-lunatone`
- status: applied
- applied_note: 2026-07-10 general `dont-open-with-the-engine` (-12) over the same Pilot._is_utility_body. f1 PASS; the deck's start-solrock-over-lunatone still orders Solrock above Riolu.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
At the pregame Set-Up Active pick the options were Lunatone (pure draw engine), Riolu (the win-condition
base) and Meowth ex. `dont-open-multiprize-active` correctly demoted Meowth ex to -15; Lunatone and Riolu
both scored 0.0, and the option index opened **Lunatone**. The deck rule that exists,
`start-solrock-over-lunatone` (+12), fires only on Solrock — which was not in hand — so nothing spoke.

This is the opener half of the same doctrine as `dont-attach-to-the-engine`, and it is role-keyed, so it
belongs in the general layer ([[fold-policy-deck-rules-general]]): at `SETUP_ACTIVE`, demote a body that has
no attacker Role (`engine`-only, or `CardStat.maxDamage == 0`, or a `supporter_tutor`/`draw` body). Order:
any attacker > pure engine. That reproduces `start-solrock-over-lunatone`'s intent without naming a card,
covers the Riolu-vs-Lunatone case the deck rule cannot see, and lets the deck rule be folded or reduced to
the Solrock-vs-Riolu tiebreak the deck actually wants (Solrock opens: Cosmic Beam 70 for one {F}).

## lunar-cycle-beats-an-inert-bench-attach
- id: lunar-cycle-beats-an-inert-bench-attach
- source: blunder-buster
- target_layer: deck-strategy
- candidate_signal: `Board.energy_placeable` is too coarse — **needs** "the pending attach lands on a body that attacks this turn" (the Active, or a KO-enabling target)
- verification_contract: verifier
- provenance: correction 85058574:f16 (mega_lucario) | fixture tests/fixtures/corrections/ml_lunar_cycle_over_inert_bench_attach_f16.json | [[mega-lucario-built]]
- status: deferred
- applied_note: 2026-07-10 BOUNCED to the producer — spec insufficient. The proposed gate ('the attach lands on a body that attacks this turn') is TRUE at f16 (the Active Riolu would attack), so it does not reproduce the correct. The human's actual claim (draw 3 beats a 30-damage self-locking chip on turn 2) is a value judgment the proposal never pinned down.
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder, not finished code):**
Turn 2. Riolu Active (0 Energy), Lunatone + Solrock benched, exactly one Basic {F} in hand.
`dont-lunar-cycle-away-the-last-attachable-f` (-30) suppressed Lunar Cycle so the {F} could be kept for
"the turn's manual attach to the wincon line" — and then `attach-solrock-over-line-base` (+3) spent it on
a **benched Solrock**, which will not attack this turn. The {F} bought nothing; Lunar Cycle would have
drawn 3, and the discarded {F} is Aura Jab fuel, not waste (`fire-lunar-cycle`'s own rationale).

The guard's premise is right but its gate is wrong: `energy_placeable` only asks "can any body take an
Energy". Tighten it to "the attach this turn would actually advance an attacker" — the Active, or a body
whose attack the Energy makes affordable — so the guard protects a real attach and stands down on an inert
one. Score-neutrality is not expected here (the guard must change behaviour on this fixture); gate on the
correction, and re-check `ml0705_starved_*` / `ml_attach_solrock_not_lunatone_f11` do not regress.

## snipe-order-a-ko-dominates-the-positional-stack
- id: snipe-order-a-ko-dominates-the-positional-stack
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Context.target_kos` (exists) — the missing piece is that `snipe-the-top-threat` / `snipe-the-forced-promotion` / `snipe-on-the-path` do not stand down on it, and their weights **sum** past `snipe-for-the-ko` (60)
- verification_contract: verifier
- provenance: corrections 82754241:f45, 82753102:f63, 81785223:f45 (all mega_starmie) | fixtures tests/fixtures/corrections/ms_snipe_ko_beats_positional_stack_f45.json, ms_snipe_ko_beats_positional_stack_f63.json, ms_snipe_the_energized_ex_f45.json | [[forgo-ko-corrections-are-refuted]], [[snipe-threat-two-signals]]
- status: applied
- applied_note: 2026-07-10 Board.snipe_ko_available gates EVERY positional snipe rung (per-option target_kos was not enough — the bonuses fire on a different body and SUM past the prize). Plus a readiness gate on the forced-promotion key and a new `dont-snipe-a-benched-tera` (card fact: Tera takes no damage while Benched). All three PASS. NOTE ms f75 was already failing on HEAD despite its proposal being `applied` — unchanged here, re-open it.
- for: general

**Spec (authoring spec — thin fodder, not finished code):**
The three mega_starmie corrections the weight fit has reported `UNSATISFIED` for several rounds are one
cluster, and the fit can never satisfy them: the positional snipe bonuses **stack**, and their sum beats
the KO.

- **82754241 f45** — Applin (40/40, KO-able) scored 60 via `snipe-for-the-ko`. Grookey (70/70, no KO)
  scored **115**: `snipe-the-top-threat` 30 + `snipe-the-forced-promotion` 40 + `snipe-the-evolving-threat`
  45. A free prize lost to three positional bonuses. "Should have sniped for the easy KO."
- **82753102 f63** — Abra (50/50, KO-able, and the base of the Alakazam that is their only attacker)
  scored 72. A Dunsparce scored **97** (forced-promotion 40 + evolving-threat 45 + path 12). Same defect.
  A second bug shows here: `snipe-the-evolving-threat` did not fire on the Abra because its
  `not target_forward_form_in_play` discriminator (ADR-0044) sees the Alakazam "in play" — while that
  Alakazam is at **0 HP**, being knocked out by this very attack. The discriminator must ignore a body
  that is already dead on this frame.
- **81785223 f45** — no KO available. Their Active (Lillie's Clefairy ex) is at 0 HP; the Bench holds a
  60/210 Latias ex with no Energy and a 70/190 Lillie's Clefairy ex carrying 1 Energy.
  `snipe-the-forced-promotion` (+40) picked the Latias as "their highest-value READY attacker
  (energy-independent)". The human picked the **energized** Clefairy ex, and neither `snipe-the-threat`
  (+20) nor `snipe-the-top-threat` (+30) fired on it at all — check whether `target_prize_redundant` /
  `target_promotion_mirage` are suppressing it. **This correction carries no rationale**, so confirm the
  read with the human before authoring its half; the KO-dominance fix below does not touch it.

Author: make `snipe-for-the-ko` strictly dominant — either promote it out of the additive score (a KO
target is a KO target: rank first, then break ties by the positional axes), or stand every positional
snipe hypothesis down on `target_kos`, exactly as `snipe-the-evolving-threat` already does. This is the
`bad_target` mirror of [[forgo-ko-corrections-are-refuted]]: a positional weight must never override a KO,
and the sum of three of them is still a positional weight.

## dragapult-matchup-plan-the-drakloaks-are-the-target
- id: dragapult-matchup-plan-the-drakloaks-are-the-target
- source: blunder-buster
- target_layer: matchup-brief
- candidate_signal: `posture.brief == "dragapult_ex"` (gamma 1.0 on this frame — the Read is CORRECT, the counterplay is missing); `opp_spreads_bench`, the Tera bench-immunity fact
- verification_contract: brief-validator
- provenance: correction 85058574:f109 (mega_lucario) | fixture tests/fixtures/corrections/ml_dragapult_matchup_plan_note_f109.json | extends the pending doctrine data/strategy/proposals/matchup-dragapult_ex.md | [[matchup-dragapult-ex-authored]]
- status: applied
- applied_note: 2026-07-10 pass 2. src/common/scouting/briefs/dragapult_ex.json: added MUNKIDORI as a threat (110 HP, RESISTS FIGHTING -30 -- the card fact that made Aura Jab whiff and Mega Brave the only KO in ml f88) and folded the f109 prize-path doctrine into the existing Drakloak fragile_preevo target. Deliberately did NOT assert opp_is_engine_dependent: it is read by _target_threat_rank OUTSIDE the brief_engine kill-switch, so it would be a live unvalidated behavior change (a wrong assertion of that key cost ~4% in an earlier stress leg). Nor a second Drakloak `engine` target -- brief_target_roles is a {card_id: role} dict and the duplicate would silently overwrite the fragile_preevo role that brief_preevo (default ON) reads. validate_brief.py: Brief OK. f109 stays degenerate (decide()==correct).
- for: opponent:dragapult_ex

**Spec (authoring spec — thin fodder, not finished code):**
Tagged `other` with `chosen == correct` — the human filed it as a **match-planner note**, not a misplay at
that option, and the real Pilot's `decide()` reproduces the tagged pick. It is doctrine, and its home is
the dragapult_ex Brief, whose Read was already firing at gamma 1.0 when the game was lost.

The note: facing a fully-energized Dragapult ex with two Drakloak on their Bench (one energized) and all
six of their prizes still up. We cannot KO the 320 HP Dragapult in one turn; the Drakloak are draw engines
(Recon Directive) and future Dragapults. Our hand held Wally's Compassion (heal the Mega to full), Boss's
Orders (gust), and an Ultra Ball into Hariyama (whose Heave-Ho Catcher gusts on evolve). The plan the human
wanted: gust the single-Energy Drakloak and KO it, placing the three discarded {F} on the benched Riolu and
Hariyama with Aura Jab; next turn gust and KO the second Drakloak; that leaves 2 prizes, and a Meowth ex in
hand fetches the decked Boss's Orders to gust the Fezandipiti ex for the last two.

Brief levers to author (they compose with the pending matchup-dragapult_ex doctrine, which already mints
"a Tera-ex wincon is threat-NOT-target — a benched Tera-ex is untouchable"): against this archetype,
(a) prize-path through the **Drakloak**, not the Dragapult — they are the engine and the successor;
(b) hold the clutch heal for the Mega rather than spending it early; (c) value gust sources (Boss's Orders,
Heave-Ho) at the Drakloak, and value the Supporter tutor as the second gust. Sibling frame f88 in the same
game is routed to `dont-wake-the-giant-with-the-self-locking-ko` (planner-code) — the two together are what
that match needed.

---

<!-- APPLY PASS 2026-07-10 (/update-strategy). Scope authorised by the human: both blunder rounds (16
proposals). 9 applied, 1 refuted, 1 bounced, 5 still open (below). Suite 1423 passed / 1 skipped, ZERO
fixture regressions (before/after sweep of all 77 correction fixtures: 14 newly PASS, 0 newly FAIL).
The mis-fit `tuned.json` weight nudges from the round's fit were dropped (reverted to HEAD) as the
header instructed.

STILL OPEN after this pass — not authored, no code written:
  - blunder-20260709-dragapult_ex.md `play-energy-denial-threat-and-ko-aware`   (f6, f32 CRITICAL)
  - blunder-20260709-dragapult_ex.md `spend-boss-orders-on-the-ko-not-setup`    (f10, f79 CRITICAL, f81)
  - blunder-20260709-dragapult_ex.md `energy-color-and-attach-target-discipline` — only its f21 ATTACH
    half shipped (merged into `dont-fund-the-non-attacking-engine-body`); the f18 energy-COLOR half
    remains
  - blunder-20260709-mega_lucario.md `lethal-retreat-enabler`                   (ml f15)
  - blunder-20260710-round.md        `dragapult-matchup-plan-the-drakloaks-are-the-target` (brief)

TWO FINDINGS THE HUMAN MUST SEE:
  1. `dont-play-a-search-item-with-nothing-to-find` is a CRITICAL correction (ml f114) that is REFUTED
     as specced — see its record. It needs a retag, not code.
  2. `ms 81785223 f75` (`ms_snipe_evolving_wincon_preevo_f75`) FAILS on the real Pilot, and failed on
     HEAD before this pass too — even though blunder-20260709-mega_starmie.md marks
     `snipe-the-real-attacker-not-a-bulky-body` as `applied` and lists f75 in its provenance. That
     proposal's claim is not true of the shipped code. Re-open it.
-->

<!-- APPLY PASS 2 · 2026-07-10 (/update-strategy). Scope: the 5 proposals remaining from the authorised
16, plus the grab-cluster status. Result: 5 applied, 1 deferred with a definition-of-done.

Cumulative over BOTH passes: 14 applied · 1 refuted · 2 deferred/bounced · 2 legacy features untouched.
Suite 1428 passed / 1 skipped. Whole-corpus fixture sweep vs HEAD: 19 newly PASS, ZERO regressions.
`tuned.json` mis-fit nudges reverted to HEAD, as this file's header instructed.

SHIPPED IN PASS 2
  - Board.opp_active_attack_threatens   (opp Active's AFFORDABLE attacks, oracle-priced, fail-open)
  - Context.card_is_wincon_attack_color (payoff's own AttackStat.energyTypes; no deck declaration)
  - general `fetch-the-attack-color` (+3, faint tie-break; silent for mono-colour decks)
  - play-energy-denial / disrupt-when-unfavored gated on threatens + `not active_can_ko`
  - _finish_turn_last: the gust demotion now keys on `active_can_ko`, not any menu KO
  - Buddy-Buddy Poffin's `bench_fill` fetch-filter carries its own 70-HP cap
  - mega_lucario `grab-lunar-cycle-fuel` (+8, human-authorised deck rule)
  - dragapult_ex Brief: +Munkidori threat, f109 prize-path folded into the Drakloak target

STILL OPEN (the two legacy features, deliberately out of scope both passes):
  - capability-gap-retreat-to-item-lock.md `retreat-to-promote-a-disruptor`  (planner-code, verifier)
  - prize-economy-fetch.md               `prize-economy-fetch`               (planner-code, seed-ladder)

CORRECTIONS THAT NEED A HUMAN RETAG, NOT CODE (proven, not punted):
  - ml 85058574 f114 (CRITICAL) — refuted, human-acknowledged. Bench full, but Poke Pad can still fetch
    a 2nd Hariyama onto the benched Makuhita; "nothing to find" is false.
  - dragapult 85046350 f32 (CRITICAL) — "we are about to KO their active" is false on the board
    (active_can_ko False: a 1-Energy Dreepy vs a 100-HP Gabite). Both options are free tier-0 plays, so
    the evolve still happens the same turn; only the Hammer's coin flip is spent.
  - dragapult 85046350 f10 — bounced: no sound gate for "the gust achieves no board value in setup".
  - ml 85058574 f16 — bounced (pass 1): the proposed gate is TRUE at f16, so it cannot reproduce correct.
  - ml 85059103 f9 (CRITICAL) — partially fixed; the residual Petrel-over-Judge read is a tutor-chain
    judgment the proposal never supplied.

KNOWN-WRONG LEDGER ENTRY (left as the human directed, recorded here so it is not lost):
  blunder-20260709-mega_starmie.md `snipe-the-real-attacker-not-a-bulky-body` is marked `applied` and
  lists ms 81785223 f75 in its provenance, but that fixture FAILS on the real Pilot — and failed on HEAD
  before either pass. Its claim is not true of the shipped code.
-->
