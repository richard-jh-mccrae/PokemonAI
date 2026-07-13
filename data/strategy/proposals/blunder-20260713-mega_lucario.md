<!-- Strategy Proposal queue — blunder-buster round 2026-07-13 (mega_lucario ONLY; user narrowed scope to
data/corrections/mega_lucario_20260713_896ad45-dirty). Contract:
.claude/skills/update-strategy/references/strategy_proposal_contract.md
Worklist this round = 5 open corrections, all from ONE game (ep 85709280, seat 1, vs Dragapult ex):
  decision f42 (CRITICAL slow_setup), decision f55 (misattachment), decision f111 (CRITICAL misattachment),
  turn t2 (CRITICAL slow_setup, key 85709280-t2s1), match m1 (CRITICAL slow_setup, key 85709280-m1).
Terminal outcomes — proposal-routed 5 across 4 clusters (below). No refuted / covered / capability-gap:
  every correction is a REAL still-open blunder (retest_one FIXED=False on every decision frame) and none
  forgoes a KO (f111's Mega Brave KO still lands same-turn via attack-last; f17's "KO" is a PHANTOM).
Routing evidence = real-Pilot retests (tools/train/retest_one.py) + card/rule facts read at source
  (data/EN_Card_Data.csv, docs/rules.md, src/common source). Card facts pinned in each spec.
CRITICAL note: 4 of the 5 are CRITICAL; all route to proposal-routed, so none triggered the human
  intervention gate (that fires only on a CRITICAL routed to refuted/capability-gap). -->

## air-balloon-belongs-on-the-active-not-a-bench-body
- id: air-balloon-belongs-on-the-active
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `CardStat.retreatReduction > 0` (the retreat-tool fact, provider.py:27, EXISTS) + the attach target's area == `_ACTIVE` (attach-target board fields already read by `equip-the-retreat-tool-on-the-active`) — plus the two EXISTING rules this repairs: `save-tool-for-the-attacker` (doctrine_tool.py:214) and `equip-the-retreat-tool-on-the-active` (:228). No new infra — the fix is a `when()`-condition change on the existing pair.
- verification_contract: verifier
- provenance: correction 85709280:f42 (CRITICAL) + 85709280:f55 (mega_lucario) | fixtures tests/fixtures/corrections/ml_air_balloon_enables_retreat_maneuver_f42.json + tests/fixtures/corrections/ml_air_balloon_on_active_not_bench_f55.json | prior art (same doctrine, must not regress): ml_air_balloon_on_the_active_f87.json (the −15 do-nothing-bench-attach case that `save-tool-for-the-attacker` DOES catch)
- status: applied
- resolution (2026-07-13, update-strategy): APPLIED. Added a retreat-tool exemption to `save-tool-for-the-attacker`'s `when()` (doctrine_tool.py): `and not (c.stat is not None and getattr(c.stat, "retreatReduction", 0) > 0)`. Air-Balloon→Active-Meowth-ex no longer eats −15, so `equip-the-retreat-tool-on-the-active` (+8) wins over the do-nothing benched-Mega attach (0). retest f42 [3]→[1] FIXED, f55 [2]→[0] FIXED; mega_lucario W-route 34/36→36/36 (both now fit-satisfiable). f87 counter-case still correct (active attach +8 > bench 0). Full suite green.
- for: general

**Spec (authoring spec — thin fodder):**
Card fact (data/EN_Card_Data.csv): **Air Balloon** — "The Retreat Cost of the Pokémon this card is attached
to is {C}{C} less." Its ONLY value is cutting the holder's retreat cost, so it is useful only on a Pokémon
you intend to **retreat** — i.e. the **Active**. On a benched body it does literally nothing (bench bodies
never pay retreat).

Both frames are the same blunder — the Pilot attaches Air Balloon to a **benched Mega Lucario ex** instead
of the **Active Meowth ex** (a support-ex pivot we want to retreat out of):
- **f42 (turn 4, CRITICAL):** Active Meowth ex (0e); bench Solrock(1e), Mega Lucario ex(1e), Riolu, **Lunatone**.
  Hand has Air Balloon + **Premium Power Pro**. `retest_one` (85709280-42): chosen [3] `Attach Air Balloon →
  Mega Lucario ex (bench 2)` = **0** (no rule fires); correct [1] `Attach Air Balloon → Meowth ex (active)` =
  **−7** = `save-tool-for-the-attacker`(−15) + `equip-the-retreat-tool-on-the-active`(+8). The human's full line:
  Air Balloon → Meowth (free retreat) → promote **Solrock** → play **Premium Power Pro** → **Cosmic Beam KO**
  (Solrock's Lunatone partner IS benched here, so Cosmic Beam is live; 70 + PPP 30 = 100 > 70-HP Fan Rotom).
- **f55 (turn 6):** chosen [2] `Attach Air Balloon → Mega Lucario ex (bench 3)` = **0**; correct [0] `Attach
  Air Balloon → Meowth ex (active)` = **−7** (same two rules). Human: "Air Balloons are for retreating active
  for free, not any other reason."

Root defect (retest-confirmed, shipped weights): **`save-tool-for-the-attacker` (−15) EXEMPTS the deck's
attacker** — so Air-Balloon→benched-Mega-Lucario (the attacker) escapes the penalty and sits at **0**, while
the correct Air-Balloon→Active-Meowth-ex is *penalized* −15 ("not the attacker") and only +8 back = **−7**,
LOSING to the do-nothing bench attach. Reweighting cannot fix it (why tune.py reports both UNSATISFIED): even
at the tuned `equip`=11.26 / `save-tool`=−11.74 the active attach is −0.48 < the 0 bench attach.

**Author:** make retreat tools (`CardStat.retreatReduction > 0`) a distinct discipline from attacker-boost
tools (Hero's Cape etc.):
1. **`save-tool-for-the-attacker` must NOT fire on a retreat tool** — a retreat tool on the *attacker* (which
   you never want to retreat) is the waste, not a retreat tool on the Active. Add `and c.card.retreatReduction
   == 0` (or equivalent) to its `when()`.
2. **`equip-the-retreat-tool-on-the-active` must beat a do-nothing bench attach** — with (1) removing the −15
   drag, +8 on the Active already tops the 0 bench attach; additionally the benched retreat-tool attach should
   be neutral-or-negative (it does nothing). Predicted: f42 [1] and f55 [0] rise above the benched-Mega [3]/[2].
The regression guard is the existing **f87** fixture (Air Balloon → benched Solrock, correctly −15): a benched
retreat-tool attach must still lose. WHY it wins: a retreat tool has exactly one home — the body you plan to
retreat — and putting it anywhere else is a pure tempo waste; this is the deck-agnostic Air-Balloon doctrine
the two `equip-`/`save-` rules were meant to encode but mis-scope on the attacker exemption.

---

## dont-shuffle-away-the-bigger-hand (Judge hand-size discipline)
- id: dont-shuffle-away-the-bigger-hand
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `Board.my_hand_size` (pilot.py:312 — literally commented "the don't-gift-a-refresh comparator") + `Board.opp_hand_size` (:309) + the `shuffle_hand`+`hand_disruption` Function Tags on symmetric refreshers (Judge id 1213, Iono, Harlequin) + the per-card draw count table (doctrine_shuffle_refresh.py:28, Judge → 4). All EXIST — no new infra.
- verification_contract: verifier
- provenance: correction 85709280:f111 (CRITICAL, mega_lucario) | fixture tests/fixtures/corrections/ml_dont_judge_away_the_bigger_hand_f111.json | complements the EXISTING sibling `dont-gift-a-refresh-when-favored` (baseline_disruption.py:60) which guards a DIFFERENT axis (matchup posture) | must not regress `strip-the-stacked-engine-hand` (:74, fires only when opp_hand ≥ 6 AND > mine)
- status: applied
- resolution (2026-07-13, update-strategy): APPLIED. New general Hypothesis `dont-shuffle-away-the-bigger-hand` (baseline_disruption.py, −25, `assumed`) + constant `_REFRESH_HAND_FLOOR = 5`. Fires on a symmetric `shuffle_hand`+`hand_disruption` refresh when `my_hand_size >= 5 AND my_hand_size > opp_hand_size` (net card-negative). retest f111 [2]Judge→[6]Mega Brave KO FIXED (Judge 20→−5, below End; the KO still lands via attack-last). Structurally exclusive with `strip-the-stacked-engine-hand`/`play-harlequin-vs-hand-size` (both need opp_hand > my_hand): the covered Harlequin case ms 82226759-64 stays at +45, unchanged. Registered in test_baseline_clusters.py. Full suite green.
- for: general

**Spec (authoring spec — thin fodder):**
Card fact (data/EN_Card_Data.csv): **Judge** (id 1213) — "Each player shuffles their hand into their deck and
draws 4 cards." It is a **symmetric** refresh to a fixed count of 4 (draw table doctrine_shuffle_refresh.py:28).

**f111 (turn 12, CRITICAL):** our hand = **8 good cards**, opponent's hand = **1**. Playing Judge takes us
8 → 4 (**net −4, discarding 4 good cards**) and refills the hellbent opponent 1 → 4 (**gifting them +3**). The
human: *"such an enormous blunder. the use of judge must always first consider our hand size and our opponents
hand size. this is card specific, deck agnostic."* `retest_one` (85709280-111): chosen [2] `Play Judge` =
**+20** (`dig-before-commit` only — nothing else fires); correct [6] `Attack with Mega Brave` = **1001.5** (a
KO). The KO is NOT forgone — `_finish_turn_last` defers the attack (tier 2) and the fix simply removes Judge
from the pre-attack develop slot, so the Mega Brave KO still lands the same turn; the human's objection is to
playing Judge **at all** on this board, and the tuner's attack-last logic MASKS it (it counts the frame
"satisfied" because the attack lands — see the W-route-satisfied≠fixed trap).

Why the existing rules don't catch it: **`dont-gift-a-refresh-when-favored`** (−15, baseline_disruption.py:60)
is the right idea but is keyed on **matchup posture** — it needs `favorability >= _POSTURE_FAVORED (0.55)`.
At f111 favorability = **0.522** (roughly even), so the −15 never fires and Judge keeps its +20 dig. But the
blunder is not about matchup posture at all — it is **card-mechanical**: a symmetric refresh is card-negative
for us whenever **our hand is large and ≥ the opponent's**, independent of who is winning.

**Author:** a new general suppressor (the card-mechanical sibling of `dont-gift-a-refresh-when-favored`) firing
on a symmetric `shuffle_hand`+`hand_disruption` refresh (Judge / Iono / Harlequin) when playing it is
net-card-negative: `my_hand_size >= refresh_draw_count` (we discard net — Judge draws 4, so my_hand_size ≥ 5
is a strict loss; ≥ 4 breaks even) **AND** `my_hand_size >= opp_hand_size` (we do not net-strip the opponent;
we gift them cards). Weight negative enough to sink Judge below both `dig-before-commit` (+20) and End (0) so
it is not played (target: Judge ≤ 0 at f111). The gate must STILL let Judge fire as targeted disruption where
it is net-positive: `strip-the-stacked-engine-hand` (+22, opp draw-engine + opp_hand ≥ 6 AND > mine) and
`play-harlequin-vs-hand-size` (+25) must not regress — both require `opp_hand > my_hand`, the exact complement
of this guard, so they are structurally exclusive with it. WHY it wins: it teaches the deck-agnostic Judge
discipline the human named — never shuffle away a strong, larger hand to refuel a hellbent opponent.

---

## honor-requiresbench-in-the-attach-lethal-lookahead (no phantom Cosmic Beam KO)
- id: honor-requiresbench-in-attach-lethal
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: `AttackStat.requiresBench` (provider.py:357, EXISTS — Cosmic Beam parses to requiresBench={Lunatone}) + the attack context `atk_bench_names` (pilot.py:2017/2045) + the promote/retreat bench-set `_promote_bench_names` (pilot.py:3254). The gate that must be EXTENDED lives at damage.py:52-54. `candidate_signal: infra-to-build` — extend the existing requiresBench zeroing to the max-bound path (a targeted change to a general oracle, NOT a capability-gap).
- verification_contract: verifier
- provenance: correction 85709280:t2s1 (CRITICAL turn, mega_lucario; representative frame 17) | fixture tests/fixtures/corrections/ml_inert_solrock_phantom_ko_f17.json | routing: turn-scope with `live_trace.planned == null` throughout the span → per routing.md the real gap is a general-hypothesis, not planner-code
- status: applied
- resolution (2026-07-13, update-strategy): APPLIED — and the real defect was NARROWER than the spec guessed (the damage.py:52 requiresBench gate was already correct; the max-bound framing was wrong). Root cause: `_attach_lethal_tactical.best_affordable` (pilot.py) called `predicted_damage` with NO context, so `atk_bench_names` was absent and the gate fail-opened. Fix: compute the live bench names (the attach is to the ACTIVE, so the Bench is unchanged) and pass `context={"atk_bench_names": bench_names}` — the exact-bound gate now zeros Cosmic Beam on an empty bench. retest f17: opt[3] 1019/tac 1001 → 18/tac 0 (phantom dead), decide()=[0] develop (keep-a-bench 65). Cosmic Beam WITH a benched Lunatone still lands (partner present → not zeroed). Full suite green.
- for: general

**Spec (authoring spec — thin fodder):**
Card fact (data/EN_Card_Data.csv): **Solrock — Cosmic Beam** ({F}, 70): *"If you don't have Lunatone on your
Bench, this attack does nothing."* A hard bench-partner requirement, already modeled as `AttackStat.requiresBench`
(the deck's `dont-cosmic-beam-without-lunatone` rule was RETIRED 2026-07-02 in favour of this oracle,
strategy.py:239).

**t2 / f17 (turn 2, CRITICAL):** Active **Solrock** (0e), **bench EMPTY** (no Lunatone), opp Active Fan Rotom
(70/70). The Pilot attaches Basic {F} → Solrock and swings Cosmic Beam — which **does nothing** (no benched
Lunatone), wasting the turn. Human: *"lunatone is required for solrock to attack… otherwise it would not have
attached energy and attempt attacking in the first place."* `retest_one` (85709280-17): opt [3] `Attach {F} →
Solrock (active)` scores **1019 (tac 1001)** — a **PHANTOM KO** (it credits Cosmic Beam's 70 → KO of the 70-HP
Fan Rotom) even though the bench is empty. The sound develop opt [0] (`keep-a-bench` +60, `dig-before-commit`
+20 = 65) is buried under the phantom. Kill the phantom → the Pilot develops (bench Meowth ex / set up the
Lunatone) instead of attacking an inert Solrock.

Root defect: the requiresBench zeroing at **damage.py:52-54** only applies when **`bound != "max"`** and only
when `atk_bench_names` is present in context. The attach-unlocks-attack tactical lookahead that produces the
1001 uses the **max (optimistic) bound**, which skips the gate — so an attack that "does nothing" without its
partner is still scored as a full KO when the partner is provably absent.

**Author (infra-to-build):** extend the requiresBench zeroing so a **hard "does nothing"** requirement zeros
the damage even at the max bound **when the partner is provably unreachable** — i.e. none of `requiresBench`
sits on the current Bench AND cannot arrive via the presumed promote/retreat set (`_promote_bench_names`). This
is distinct from a mere optimistic upper bound (where max may assume a not-yet-present body): "does nothing"
is a floor of 0, not an optimistic ceiling, so a provably-absent partner must zero all bounds. Verifier gate:
on the f17 fixture, opt [3]'s tactical KO credit must drop to ~0 (no phantom) so a develop option wins; the
existing `atk_bench_names`-satisfied cases (Cosmic Beam WITH a benched Lunatone, e.g. f42's board) must keep
their real damage. WHY it wins: the Pilot stops burning setup turns attaching to and swinging an inert Solrock —
a correctness fix to the card-knowledge the deck was told the oracle already owned.

(Out of scope / noted: the human's richer turn-2 line — Meowth ex → Last-Ditch Catch fetch **Team Rocket's
Petrel** [Supporter] → Petrel fetch **Premium Power Pro** → PPP + Cosmic Beam KO — is a multi-step combo that
also needs a benched Lunatone it doesn't have at f17; it is a future multi-turn-planner opportunity, not part
of this correctness fix. The primary blunder the human flags — attaching+attacking an inert Solrock — is fully
resolved by killing the phantom.)

---

## dont-bench-a-redundant-second-solrock (reserve the bench for the Makuhita line)
- id: dont-bench-a-redundant-solrock
- source: blunder-buster
- target_layer: deck-strategy
- candidate_signal: `Board.in_play_ids` (SOLROCK 676 + LUNATONE 675 both online — the exact gate the deck's `skip-a-partnerless-solrock` / `grab-the-playable-item` rules already use, strategy.py) + a bench-duplicate read (a Solrock is already in play AND this option benches another Solrock). The rule counteracts the GENERAL `pre-position-attacker` (+25, baseline_bench.py:37) for a redundant engine duplicate. No new infra beyond an in-play-duplicate check.
- verification_contract: verifier
- provenance: correction 85709280:m1 (CRITICAL match, mega_lucario; representative frame 51) | fixture tests/fixtures/corrections/ml_dont_bench_redundant_solrock_f51.json | routing: match-scope, but `live_trace.planned == null` at f51 (the 2nd-Solrock play was scoring-driven via pre-position-attacker +25, not planner-committed) → the fix is a deck develop-priority rule, not a plan_match change
- status: applied
- resolution (2026-07-13, update-strategy): APPLIED. New deck Hypothesis `dont-bench-a-redundant-engine-piece` (src/agents/mega_lucario/strategy.py, −25, `assumed`) — the PLAY-side complement of `dont-fetch-the-redundant-piece`: fires on `_PLAY` of an engine piece (`_ENGINE_IDS`) already in play whose partner is also in play (`c.card_id in board.in_play_ids and _partner in board.in_play_ids`). retest f51: opt[2] Play Solrock 25→0, decide() [2]→[0] (keeps the bench slot open). Soft (never hard-vetoes a sole backup). match-scope correct=[] so `fixed=None` by construction; gate = chosen moved off the redundant Solrock + suite-green. Full suite green.
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder):**
Deck fact (src/agents/mega_lucario/strategy.py:60): the Solrock↔Lunatone pair is a **co-dependent one-of-each
engine** — Solrock is the Cosmic Beam attacker / Lunar Cycle enabler, Lunatone is the benched draw engine.
**One** Solrock + **one** Lunatone in play completes the engine; a second Solrock is redundant.

**m1 / f51 (turn 6, CRITICAL):** bench already = Solrock(1e), Mega Lucario ex(Air Balloon), Mega Lucario ex,
**Lunatone** (engine complete). The Pilot plays a **2nd Solrock** into the last bench slot. Human: *"We dont
need two Solrocks down. we must reserve this last bench spot for a Makuhita"* (→ Hariyama, the Heave-Ho Catcher
gust-on-evolve + 210 attacker). `retest_one` (85709280-51): chosen [2] `Play Solrock` = **+25**
(`pre-position-attacker`), beating opt [0] `Play` (dig) = +20 → the redundant Solrock wins and clogs the bench.

**Author:** a deck-strategy rule that suppresses `pre-position-attacker`'s reward (or applies a matching
negative) for benching a **Solrock when a Solrock is already in play AND the Lunatone partner is online**
(`SOLROCK in board.in_play_ids and LUNATONE in board.in_play_ids` and the option benches another Solrock) —
the engine is complete, so a duplicate is not "pre-positioning an attacker", it is bench clutter. Target: opt
[2] drops below opt [0] at f51 so the last bench slot stays open for the Makuhita→Hariyama line. Keep it
conditional — a 2nd Solrock is NOT suppressed when no Solrock is yet in play, or when the engine is offline
(a partnerless Solrock is a different, already-handled case). WHY it wins: it stops the agent over-committing
duplicate engine pieces into a scarce bench, preserving room for the deck's Stage-2 finisher line — the exact
bench-management the human called out.
