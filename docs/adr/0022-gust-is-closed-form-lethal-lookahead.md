# ADR-0022: Gust decisions are a closed-form lethal-lookahead over hypothetical defenders (board-only, Read-deferred)

**Status.** Accepted (grilled 2026-06-29); **implemented 2026-06-29** — whether-to-play
(`gust-for-the-ko` + the lethal Tactical term), the `SWITCH(3)` target-select (`_gust_target_tactical`
= KO + prizes + denial + forward-denial), and the tier-5 stall-gust, all test-first in
`tests/test_gust.py` + an end-to-end check through the real mega_starmie Pilot. **Refinements
implemented 2026-06-29** (grilled; `tests/test_attack_value.py` + `tests/test_attack_riders.py`): the
special-condition rescue guard + offensive baseline (#10), the Item-vs-Supporter split (#12), the
simultaneous-double-KO draw-guard (#2, half a), the bench-snipe attack-value bonus (#14), and
**Resistance** in the KO oracle — see the *Refinements* section below. **Still deferred:** the
draw-over-loss valuation (#2 half b), the four-mechanic split's coin-flip / Confuse branches, and
Read-conditioned gusting.

**Context.** A *gust* (force the opponent to switch a benched Pokémon to their Active Spot — Boss's
Orders, card id 1182) appears in nearly every deck, swings games, and is easily misplayed. It is the
deck-agnostic counterpart of [ADR-0020](0020-forward-evolution-index-is-a-provider-primitive.md)'s
snipe work, and belongs in the **General Strategy** ([ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md)).
A gust is **two** Pilot decisions: (A) *whether to play it* — one Supporter per turn, so it competes
with a setup tutor/draw and cannot be played turn 1 on the play ([docs/rules.md](../rules.md) §3); and
(B) *which benched Pokémon to drag up*. Engine facts established by replaying the corpus and reading
`cg/api.py` (the [CLAUDE.md](../../CLAUDE.md) verify-at-source rule):

- **The gust target-select is `SelectContext.SWITCH(3)`, not `TO_ACTIVE(4)`.** Confirmed across five
  episodes: every target-pick after a Boss's (1182) play is context 3 with **opponent-owned** options
  (`area=BENCH`, `playerIndex != yourIndex` — `1` at seat 0, `0` at seat 1). `SWITCH(3)` is *also* the
  agent's own retreat, so `playerIndex` is the disambiguator. (My-promote-after-KO is `TO_ACTIVE(4)` —
  a different context — so the existing promote Hypotheses cannot collide with the gust select.)
- **The gust decisions are unsupported today.** `prize-trade-target` is a Tactical prize-preference
  over the *current* Active (not a Hypothesis). The post-gust KO would be scored once the gusted mon is
  Active, but nothing scores the two pre-gust decisions (whether to play it; which benched mon), so the
  Pilot never reaches the gust→KO line.
- **Prizes-remaining is in the observation** (`players[i].prize` length) — lethal is detectable.
- **The `gust` Function Tag spans four mechanically different cards** (1182 Boss's = forced Supporter;
  1124 Pokémon Catcher = coin-flip Item; 1088 Prime Catcher = Item + self-switch, ACE SPEC; 1204
  Lisia's Appeal = Basic-only Supporter + Confuse) — a tag-only trigger would misfire on all four.

**Decision.**

- **Doctrine.** Hold-by-default; play a gust **only** into a KO (priority: lethal/closing ▸ prize-grab
  ▸ threat-denial ▸ pre-evo tempo) or a decisive **defensive stall-gust**. Never gust a target you
  cannot KO (it gifts the opponent a ready attacker in the Active Spot) — except the stall.
- **One closed-form oracle, two consumers.** `gust_ko(my_active_stat, defender_stat) → (can_ko,
  prizes)` generalizes the Tactical KO math to an **arbitrary defender** (not just the current Active):
  best **affordable** attack (availability-gated **+1** for the manual attach we can actually make),
  ×2 on the *defender's* weakness, **minus the defender's resistance**, vs the defender's HP. It feeds
  both a whether-to-play Board signal and the target-select Hypothesis, so the play-reason and the
  picked target agree by construction (a Verifier invariant). No Search — closed-form off `CardStat`,
  consistent with the Tier-0 Tactical contract.
- **"Best attack" = best total board value, not max printed damage.** Among affordable KO attacks,
  prefer the one whose side effect adds value (e.g. a 120-damage KO **+ 50 bench snipe** over a 210
  overkill), when a worthwhile snipe target exists; else fall back to cost-efficiency.
- **Value is additive, lethal short-circuits.** Non-lethal `value = prizes + denial + forward_denial`.
  `denial` is **board-only**: the candidate threatens to KO one of my Pokémon soon (incoming-damage of
  the candidate vs my board), scaled by the prize value of what it would KO; `forward_denial` reuses
  the Evolving-Threat primitive. **Lethal** (gust prizes ≥ my opponent's remaining prizes) dominates
  everything — **except** it must **not** count a simultaneous double-KO, which is a **draw**, not a
  win (the competition rules delta); a forced draw is still valued above a loss when otherwise doomed.
- **Net-of-baseline scale.** Lethal scores in `KO_SCORE`-class. A non-lethal gust-KO is a tunable seed
  ([ADR-0009](0009-training-methodology.md)), **damped in `SETUP` while the wincon isn't in play** so a
  setup tutor can still win the Supporter slot; the stall-gust sits below every tutor/draw.
- **Scope.** v1 is **board-only** (the Read/Scouting is not wired into the Pilot) and **gated to card
  id 1182**; the four-mechanic split and engine/replaceability-denial wait for later work.
- **Tier-5 stall-gust is in scope but mechanically weak.** Fires only when `active_doomed` ∧ no
  gustable KO ∧ no KO on the current Active ∧ an *energyless, retreat ≥ 2* bench target exists; it
  strands that target Active to buy a turn. Needs new infra (`CardStat.retreatCost`, per-bench energy
  on `Board.opp_bench`, special-condition tracking so a condition-doomed Active is never gusted free).

**Considered options.**

- **Reuse the snipe target ranking wholesale** — rejected. Snipe applies fixed damage to a mon that
  stays benched (an energized attacker is its top target); a gust *drags the mon Active*, where a
  non-KO is a blunder. The gust needs a `can_ko` **hard pre-filter** snipe must not have. Share only
  the value sub-terms (energy-threat / forward-damage / weakest-HP), never the order or the filter.
- **Strict prizes-first target ranking** — rejected for **additive denial**: grabbing a fat *inert*
  prize while a live 1-prize attacker survives to KO your wincon loses the game.
- **Gate the target-select on `TO_ACTIVE(4)`** — refuted by the replay corpus; it is `SWITCH(3)`.
- **Credit only already-attached energy** in `gust_ko` — rejected for the availability-gated **+1**: a
  finisher that under-detects its own KOs is dead, and the `_finish_turn_last` sequencing (gust →
  attach → attack) makes the +1 safe when the energy actually exists.
- **A tag-only gust trigger** — rejected: gate to 1182 for v1 (the tag spans Items and a confuse-gust
  with different economics).
- **Search-based lookahead** — rejected: a closed-form oracle matches the Tier-0 Tactical contract and
  needs no engine rollout.

**Consequences.** The Tactical Evaluator's contract widens: its KO math now evaluates **hypothetical
defenders**, not only the current Active (a future reader will see `gust_ko` and the SWITCH(3)-gated
Hypotheses and should read this ADR for why). New signals land on `Board`
(`my/opp_prizes_remaining`, `gust_best_ko_prizes`, the lethal flag) and `Context` (`gust_can_ko`,
`gust_ko_prizes` at an opponent `SWITCH(3)` option); the snipe value sub-terms are widened to that
select behind a `playerIndex != yourIndex` guard. v1 plays board-only; engine/replaceability-denial,
proactive (scouted-matchup) gusting, and the four-mechanic split arrive once the Read/Posture is wired.
The design and infra are tracked as a task list in the grilling session (oracle, Board/Context fields,
the two KO Hypotheses, the tier-5 stall set, the Tactical bench-value refinement, the mechanic split,
tests + docs).

**Refinements (grilled + implemented 2026-06-29).** A second grilling pass built the five edge items.
Two findings reshaped the original plan:

- **Resistance is a per-card PRINTED amount, uniformly −30 in this set.** It is a card fact (printed on
  the card, e.g. Slowking "Fighting −30"), **not** in our data export — `CardData.resistance` and the CSV
  are resistance-*type* only, and the amount is in no text field, so the handoff's "text-parse it like
  `hpBonus`" was a dead end. The simulator is the scalable authority ([CLAUDE.md](../../CLAUDE.md)): a
  behavioral probe (drive `cg.game` with stacked decks so the only modifier is Resistance —
  `tools/sim/probe_resistance.py`) over **47** resistant Pokémon — every basic Fighting-resist and
  Grass-resist body, ex & non-ex, HP 90–280 — returned **−30 on every one**, matching the printed cards.
  So `_RESISTANCE = 30` is a verified constant. A constant is correct *because* the printed amount is
  uniform here; if a future card prints a different number the probe would surface it (revisit then). The
  resistance *type* was already precompiled into `CardStat.resistance`. Weakness AND Resistance are now
  applied through **one** direction-agnostic helper `_wr_adjusted(attacker, defender, dmg)` (rules.md §5
  order), routed by **all four** closed-form damage sites — my attacks (`_tactical`, `_can_ko`) and
  **incoming** damage (`_incoming_active_damage`/`active_doomed`, `_gust_target_denial`) — so Resistance
  is honoured defensively too (a self-resisting Active isn't falsely flagged doomed), closing the
  red-team "factor W/R into one helper" note.
- **The "one shared parser" is really TWO things.** Recoil (#2) and bench-snipe (#14) *are* free-text
  `Attack.text` riders → one parser, two `hpBonus`-style regexes (`parse_attack_recoil` /
  `parse_attack_bench_snipe`, matching only the clean *unconditional* sentence, else 0 — under-credit is
  the safe direction). Resistance is orthogonal (the constant above). All three reds are **moot for the
  live mega_starmie deck** (Water/Fire attacks never meet Fighting/Grass resistances; no recoil
  attackers; Jetting Blow's +50 snipe is already the cheapest KO) — built for generality + the mega_lucario
  (Fighting) deck + the writeup.

New signals added: `Board.opp_prizes_remaining` / `opp_active_condition_gift` / `active_condition_ko_prizes`,
`CardStat.cardType`, and per-`attackId` `recoil` / `bench_snipe` maps. Decisions made in the grill:
the stall guard blocks on **all five** conditions (conservative floor); the offensive baseline folds a
poison/burn-doomed Active's prize into the gust net-of-baseline (Option 2) but never suppresses a
**lethal** gust; #12 gates only the gust-for-the-ko SETUP-damping to `cardType == SUPPORTER`; #2 ships
**half (a)** only (suppress the false win), draw-over-loss deferred.
