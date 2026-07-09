# ADR-0047: Opponent awareness is one facade over knowledge subsystems, not scattered fields

**Status.** Accepted (grilled 2026-07-09, `/grill-with-docs`) + **Foundation built 2026-07-09**
(`/tdd`). Introduces the **Opponent Model** facade and the **Resources** subsystem; folds the
existing **Read** (ADR-0003/0026/0027) and **Dispositions** (opponent_properties) behind it. New
glossary terms *Opponent Model*, *Resources*, *Dispositions* in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md). Unblocks the five deferred opponent-side proposals
in [data/strategy/proposals/](../../data/strategy/proposals/). The plan the handoff
[pokemonai-handoff-opponent-modeling-cluster.md](../../data/handoffs/pokemonai-handoff-opponent-modeling-cluster.md)
called for.

**Build (2026-07-09, `/tdd`, behavior-neutral).** Four seams, test-first, full suite green
(**1406 passed / 1 skipped**), new modules 94% covered:
- `src/common/opponent_resources.py` — the Resources subsystem: stateless `copies_left_odds` (the
  opponent-side `deck_odds`; the opponent's HAND joins prizes in the hidden non-deck pool) + the
  match-scoped `OpponentResourceModel` (`deck_count`, `deckout_in_turns`, `hand_size`(+`_delta`),
  `last_turn_dumped`, `took_ko_this_turn`). Gated `REQ-OPP-0001..0006`.
- `src/common/opponent_model.py` — the `OpponentModel` facade: one `observe(obs)` fan-out (Scout by DI
  + Resources), fail-open accessors, `copies_left_odds(card)` via the Read's representative-build prior,
  `disposition(key)` from the γ-gated matched Brief (fed by `note_brief`). Gated `REQ-OPP-0010..0014`.
- `pilot.py` fold: `Pilot.__init__` builds `self.opponent`; `_board` swaps the one `scout.observe` for
  `self.opponent.observe` (Posture-off `read=None` preserved) and calls `note_brief(brief)`;
  `board.opponent` rides the Board; `Board.opp_property` delegates to the facade's Dispositions (same
  matched Brief → identical values). **No `main.py` churn**; no consumer wired yet (the deferred cluster
  consumes it next, via `/update-strategy`). Tests `tests/strategy/test_opponent_resources.py`,
  `tests/strategy/test_opponent_model.py`.

**Context.** Opponent awareness is smeared across the codebase with no single home:

- **the Read** (`scouting/scout.py` → `read.py`) — deck recognition: archetype, confidence,
  `expected_cards`, `evolution_paths`, threats, targets. Match-scoped, resets on new match.
- **opponent_properties** (`scouting/opponent_properties.json`) — high-bar behavioral booleans
  (`opp_is_engine_dependent`, `opp_comeback_disruptor`), asserted by Briefs, priced ~4% on a wrong claim.
- **Briefs** (`scouting/briefs/`) — prescriptive matchup counterplay doctrine.
- **posture-scoring** (`active_doomed`, threat rank, forward-doom) — computed in the Pilot/Planner from
  our card facts + board, not from opponent history.
- **the missing piece** — no model of the opponent's *remaining resources / outs*. `deck_odds.py` and
  `deck_tracker.py` are **own-deck only**. The handoff cluster's one shared build (`opp_copies_left`,
  `opp_deckout_in_turns`, `opp_hand_size_delta`, `opp_last_turn_dumped`, a took-a-KO flag) has no home,
  and five deferred proposals all wait on it. Faking a weight without the signal is refused (ADR-0026).

The word **"model" is overloaded three ways** (the Read is informally "the opponent model"; the handoff
names the new resource file `opponent_model.py`; the umbrella concept is also "Opponent Model"). This
already caused a mislabel in conversation. A design without fixed vocabulary rots.

**Decision.**

1. **Opponent Model = a match-scoped facade, not a folder.** Introduce `board.opponent` as the single
   surface everything routes through: `.archetype`, `.copies_left(card)`, `.deckout_in_turns`,
   `.properties`, etc. The facade — one write seam + one read surface — is the product; a namespace-only
   grouping was rejected as cosmetic. It is a **pure knowledge layer**: it answers *what is true / probable
   about the opponent*, and never decides. The Pilot/Planner consume it.

2. **Membership — three knowledge subsystems.**
   - **Identity** = the Read/Scout (keep the established name). *Who they are.*
   - **Resources** = new `opponent_resources.py`. *What's left.* Match-scoped, like `deck_tracker.py`.
   - **Dispositions** = opponent_properties. *How they behave* (high-bar booleans).

   **Out of the facade:** **Briefs** (they are the *input* that asserts Dispositions + tactical boosts,
   not an awareness subsystem — keeping matchup-genie's prescriptive doctrine out preserves the
   knowledge/decision seam), and **posture-scoring** (Pilot/Planner *decision* over card facts, not
   opponent history — folding it in would annex half the Pilot for the largest blast radius and weakest
   seam).

3. **One facade, two honest epistemic tiers — never one confidence number.**
   - **Calibrated tier** — Resources + Read confidence. Resources is mostly **probabilistic**
     (hypergeometric over unseen copies split across hidden prizes, exactly like `deck_odds.p_contains`
     but opponent-side) with a few **sound** anchors (visible board/discard, `deckCount` exact). Note the
     asymmetry with our own side: `deck_tracker` resolves our prizes to *exact* via reveals, but the
     opponent grants far fewer sound reveals, so opponent Resources leans probabilistic and is sound only
     where a log/board makes it certain.
   - **Asserted tier** — Dispositions. High-bar booleans, asserted only on strong evidence.

   Contract spanning both: **every field self-reports its epistemic class; the facade never fabricates and
   never downgrades a certainty into a guess; it fails OPEN** (a missing read never suppresses a real
   line, exactly like `deck_odds`). The consumer picks the threshold per field. **Sound-or-silent.**

4. **Lifecycle — constructed once per match, one `observe(obs)` fan-out, composes the Scout.** The Pilot
   swaps its current `scout.observe(obs)` call for `opp.observe(obs)`; internally that fans out to
   `read.observe` + `resources.observe`. Static references (priors artifact, properties JSON) are injected
   at construction. The facade **composes** the existing Scout by dependency injection — it does not
   rewrite it. If the Pilot still called N separate updaters, only the read side would be unified, not the
   write; the single write seam is the point.

5. **Vocabulary fix.** "Opponent Model" is reserved for the umbrella. The handoff's proposed
   `opponent_model.py` is renamed **`opponent_resources.py`**. Subsystem names (Read, Resources,
   Dispositions) deliberately avoid the word "model" so exactly one thing carries it.

6. **Scope — foundation now, proposals route normally, own-side work stays out.** Build the facade +
   Resources subsystem + fold Read/Dispositions behind it. The **five deferred opponent-side proposals**
   (`kou-30deck-general` · unfair-stamp-comeback-posture; `learnthetcg-fundamentals` ·
   ko-target-maximise-opponent-whiff / risk-scales-with-prize-position AHEAD-half /
   disrupt-tailored-hand-dont-hoard-iono side-1 / deck-knowledge opponent-half) then become buildable and
   go through `/update-strategy` as usual — each default-on, kill-switched, blunder-buster telemetry,
   **ladder-gated**. The handoff's **three non-opponent items stay OUT** of the Opponent Model, tracked
   separately: own-side `turn_goal_satisfied` (a Turn-Planner predicate), own-deck guarantee-out
   sequencing (`guaranteed_out_at_risk_from_shuffle`, Planner-code), and the refuted dead-hand →
   **deeper Lethal-Solver class** (the retreat-enabler lethal: Petrel → tutor Air Balloon → free-retreat
   → promote benched Mega Lucario ex → Aura Jab win — extend `_family_win_candidates`, not the model).

**Guardrails (carried from the handoff).**
- **Ladder-validate, don't gauntlet-A/B** — the cross-deck gauntlet is invalid-for-gain
  (`gauntlet-invalid-ladder-only`). Ship each feature default-on, kill-switched, with blunder-buster
  telemetry; the Kaggle ladder + user corrections are the gate.
- **High-bar Dispositions** (`opp_is_engine_dependent`, `opp_comeback_disruptor`) price a wrong assertion
  ~4% — assert only on strong evidence.
- **Sound-or-silent** — every opponent-out estimate fails OPEN, never suppresses a real line on a guess.

**Rejected.**
- **Namespace/folder-only grouping** (move files under `src/common/opponent/`, keep scattered Board
  fields). Cheap but cosmetic — no unified surface, no shared contract; the ResourceModel gets built
  either way, so the "umbrella" would buy nothing but a tidier tree.
- **Four subsystems (Briefs inside).** Mixes prescriptive doctrine with factual awareness — the facade
  would emit both "what's true" and "what to do", blurring the knowledge/decision line and coupling
  matchup-genie's output into the awareness contract.
- **Maximal (posture-scoring inside).** The most literal reading of "all-things opponent awareness", but
  annexes Pilot/Planner decision code; posture is computed from *our* card facts + board, not opponent
  history — wrong owner, largest blast radius.
- **Keep `opponent_model.py` for the resource file.** File name == umbrella name — the exact collision
  that caused the earlier mislabel.
- **Single uniform confidence scalar on every field.** Forces high-bar Dispositions into a false
  probability and erases the calibrated-vs-asserted distinction the consumer needs to gate correctly.
- **Build the whole cluster (incl. own-side items) this session.** Violates the knowledge/decision seam
  and the handoff's phased "one shared build unblocks the cluster" intent; largest single blast radius.

**Consequences.** New `src/common/opponent_resources.py` (match-scoped tracker) and a facade module
surfacing `board.opponent`; the Pilot swaps one `scout.observe` call for `opp.observe`. The Read and
Dispositions are re-homed behind the facade with no behavior change (fold, not rewrite). The five
opponent-side proposals lose their capability-gap blocker and re-enter the `/update-strategy` queue. The
three own-side/Lethal items are recorded as separate buildables, explicitly *not* Opponent Model, in their
own handoff
[pokemonai-handoff-ownside-sequencing-and-lethal-depth.md](../../data/handoffs/pokemonai-handoff-ownside-sequencing-and-lethal-depth.md).
Snapshot
opp reads currently taken at `objectives.py:304`, `planner.py:582/1451`, `pilot.py:1666` become the
accumulation points for `opp_deckout_in_turns`. Sources of truth for Resources: `obs['logs']`, opp
`discard` / `handCount` / `deckCount` / `prize`; own-deck analogs to mirror: `deck_odds.py`,
`deck_tracker.py`.
