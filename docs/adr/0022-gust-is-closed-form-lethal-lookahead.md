# ADR-0022: Gust decisions are a closed-form lethal-lookahead over hypothetical defenders (board-only, Read-deferred)

**Status.** Accepted (grilled 2026-06-29) — **designed, build pending**.

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
