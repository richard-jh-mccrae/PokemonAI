# Handoff: grill the three deferred-by-design features

**Date:** 2026-07-02 · **Branch:** `claude/zen-goodall-c36dc9` at `75936a4` (clean; wiring-pass
commits `73a9610` + `75936a4`, PR to main pending) · **Suite:** 1035 green (`python -m pytest
tests/ -q`) · **Corpus:** 103/103 corrections satisfied at authored seeds (`python
tools/train/tune.py --agent mega_starmie --no-report`)

## Purpose

Three features were deliberately parked ("deferred-by-design — do NOT build without a grilling
session") by the wiring-pass handoff and stayed untouched through it. This doc preps the grilling
session(s) for them. **The deliverable of each grill is a decided design captured in the owning
ADR (updated inline) — building only starts after the human signs off.** Each is a genuine design
fork, not wiring: the seams exist, the code names its own gap, and the cheap half already shipped.

The wiring pass that preceded this is DONE and ON by default (lethal engine-verify, planner
engine ranking + key-threat rung + dev term, `search-the-confirmed-hit`); its record lives in the
ADR-0029/0030/0031/0033 amendments and the two commits above — don't re-derive it. The other two
deferred items are NOT in scope here: planner multi-turn has its own captured corpus
(`docs/todo/deferred-multi-turn-criticals.md`) and the pooled general-tuned layer's trigger (a
2nd corrected deck, ADR-0035) hasn't fired.

## Item 1 — Shuffle-Refresh pull-EV (Layer B)

**What exists (Layer A, ADR-0024):** `refresh-a-dead-hand` (+8,
[doctrine_shuffle_refresh.py:126-144](../src/common/strategy/doctrines/doctrine_shuffle_refresh.py))
plays a `shuffle_hand` Supporter when the hand is PROVABLY dead — `board.hand_is_dead` (a
full-scan: every held card scores ≤0 by the keep-value comparator) AND `board.deck_holds_a_need`.
Its rationale ends: *"Layer A; the stochastic pull-EV refinement is deferred"* (line 140-141).
Deterministic-or-silent by design: a hand with ANY live card never refreshes.

**The gap:** between "provably dead" and "clearly alive" sits the common case — a *mediocre* hand
where shuffling 5 dregs into a 20-card deck holding 4 great cards is plainly right, but Layer A
is silent. Pull-EV = value the refresh by the expected quality of the N cards drawn back vs the
keep-value of what's shed.

**Design forks the grill must resolve:**
- **EV model:** exact expectation over the tracked deck (the sound `deck_known_counts` /
  probabilistic `deck_contains_odds` per ADR-0029 already exist — hypergeometric machinery in
  `common/deck_odds.py` is reusable) vs a coarse density heuristic (needs-in-deck ÷ deck size).
  Sound-vs-probabilistic separation doctrine applies (ADR-0029).
- **The comparator:** EV(draw-back) − keep-value(hand) — but keep-value is a per-card ordering
  today, not a hand-level scalar. Does Layer B need a hand-value primitive? (This is the same
  scalar-vs-ordering question the Base Value Model, ADR-0007, eventually owns — how much to
  build now vs leave to the model?)
- **Draw-count facts:** shuffle Supporters draw different N (Lillie's vs Harlequin — Harlequin
  is symmetric and also refills the OPPONENT; the ADR-0024 boundary with `hold-wincon-dont-shuffle`
  and the anti-shuffle Tool floor, ADR-0028, must stay intact). Verify each card's N at source.
- **Threshold + weight:** where does "mediocre" start; does Layer B subsume Layer A's +8 or ride
  above it; kill mechanism (rule weight → overlay-zeroable, like `search-the-confirmed-hit`).
- **Known trap (memory):** the contradictory human pair — 83116081-17 wants Lillie's over
  Harlequin, 83117367-34 the reverse — was ruled a Base-Value-Model call, NOT a weight gap. The
  grill must define where pull-EV stops and the value model begins.

**Read first:** ADR-0024 (its Layer A/B split + dig-before-commit boundary), ADR-0029,
`docs/adr/0028*` (anti-shuffle floor), memory `shuffle-refresh-doctrine`, the Fetch keep-value
comparator (`_grab_value_of` / discard rungs in doctrine_fetch.py).

## Item 2 — Fetch full cost-netting

**What exists:** `fetch-when-it-fills-a-need` (+8,
[doctrine_fetch.py:443-458](../src/common/strategy/doctrines/doctrine_fetch.py)) endorses playing
a discard-cost fetch when a needed grab is reachable; its rationale says the LOW weight "stands in
for the deferred cost-netting" and names the remainder outright: *"The full cost-netting (subtract
the shed cards) and Plan-scaled bar remain"* (line 455-456). One special case of netting already
shipped separately: `hold-costly-fetch-when-line-assembled` (line 474+) suppresses Ultra Ball when
the line is assembled. `dig-before-commit` deliberately stands down for `cost_discard` cards.

**The gap:** net_value(search) = best-grab value − keep-value(the 2 cards actually shed). Today
the cost is priced as a flat pessimism constant (+8 instead of +20-ish), so a fetch with junk to
shed is under-played and a fetch that must shed a live Supporter is over-played.

**Design forks:**
- **Which cards get shed?** The discard pick happens at a LATER select (the `_DISCARD` context,
  where the keep-value ordering already chooses well). Cost-netting at PLAY time must PREDICT that
  pick — reuse the same keep-value ordering on the current hand minus the fetch card (shared-oracle
  invariant, ADR-0023: play-reason, grab, and discard must agree by construction).
- **Replace or refine?** Does netting replace `fetch-when-it-fills-a-need`'s +8 with a computed
  net (a scored VALUE, breaking the flat-weight Hypothesis idiom — precedent question!), or gate/
  scale the existing rung (e.g. suppress when net ≤0, boost when shed cards are provably dead)?
  The Hypothesis system is weights-that-fire, not computed scores — a computed net is an idiom
  change worth explicit ADR treatment.
- **Interaction audit:** `hold-costly-fetch-when-line-assembled` becomes a special case — fold it?
  The ep82228640-fr7 shape (discard-dig must not outrank powering the attacker) must stay a test.
- **"Plan-scaled bar":** the rationale also defers a Plan-dependent threshold (dig harder in
  SETUP than in RACE?) — decide whether that's in or out.

**Read first:** ADR-0023 (the shared comparator doctrine — this change touches its core
economics), the discard/keep-value rungs (`_KEEP_ENGINE_TAGS`, discard-side HYPOTHESES),
`docs/weights.md` bands, memory `sound-deck-emptiness-oracle`.

## Item 3 — Posture lever A, favored→race half

**What exists:** the UNFAVORED half shipped: `disrupt-when-unfavored` (+18,
[baseline_disruption.py:47-63](../src/common/strategy/baseline/baseline_disruption.py)) — when the
Read's compiled matchup favorability ≤ 0.45 with coverage ≥ 0.25, up-weight already-useful free
disruption. Line 57 names this item's gap: *"The favored→race half is deferred (no clean
'aggressive option' tag yet)."* The signals exist on Board: `favorability`, `matchup_coverage`,
`posture_confidence` (γ) — ADR-0026.

**The gap:** when FAVORED (say ≥ 0.55-0.6), the symmetric move is "stop durdling, race" — but
unlike disruption (a clean Function-Tag family), "race harder" has no single option class to
up-weight. That's WHY it's parked: the design question is what "race" concretely means in
option-vocabulary.

**Design forks:**
- **What gets up-weighted?** Candidate framings the grill should stress: (a) a Plan-level bias
  (enter/stay in RACE mode earlier when favored — Plan is the existing SETUP/RACE mode enum); (b)
  up-weight attack-enabling development (attach-to-attacker / evolve-to-attacker rungs) over
  digging/stalling; (c) down-weight the disruption/stall families (the mirror of the shipped
  half); (d) mint the missing "aggressive option" trigger tag the code asks for — but tags are
  CARD facts (memory `function-tags-canonical-signal`), and "aggressive" is option-context, not a
  card property, so (d) may be a category error the grill should kill explicitly.
- **Symmetry + thresholds:** is 0.55/0.6 the mirror of `_POSTURE_UNFAVORED = 0.45`? Same coverage
  gate? Same board-dominated, never-overrides-a-KO discipline (the refuted forgo-KO doctrine,
  memories `forgo-ko-corrections-are-refuted` / `attack-is-turn-ender-develop-first`, binds hard).
- **Evidence problem:** lever A rides the meta-DB Read; the shipped agent plays mostly mirrors
  locally, where favorability ≈ 0.5 → the rule would ~never fire in the arena. The A/B norm
  needs a plan: seed a matchup artifact fixture? gate on unit tests + fire-counts only? The grill
  must decide what evidence clears it to ON (don't hand-wave this — the wiring pass's norm was
  A/B-before-ON).
- **Owning ADR:** ADR-0026 (levers) — amend inline; a new ADR only if the design outgrows it.
  Next free ADR number is 0037.

**Read first:** ADR-0026 + ADR-0027 (Briefs are the per-archetype counterpart — beware overlap:
brief-driven counterplay vs generic favorability lever), memory `m2-posture-plan`,
`card-fact-posture`, `matchup_favorability` in `src/common/scouting/` (how the number is compiled
and why coverage gates it).

## Norms that now apply to ALL three (post-wiring-pass world)

- Behavior change ⇒ kill mechanism + arena A/B before default ON. Params flow
  `main.py _params.get(...)` (precedent: `posture`, `lethal_verify`, `planner_engine_rank`,
  `planner_key_threat`); rule-weight changes are overlay-zeroable instead. Keep
  `tools/train/tune.py _build_pilot` defaults in sync with `main.py` when adding switches.
- Arena A/B is cheap: `python tools/sim/battle.py "mega_starmie@off.json" "mega_starmie@on.json"
  -n 1000 -j 8 --note "..."` ≈ 40-60 s per 1000 games; overlay = `{"overrides": {...},
  "params": {...}}` absolute path. battle.py devnulls stderr — fire/divergence counts need an
  in-process Decision-object loop (pattern existed as a scratch `fire_counts.py`; re-create as
  needed).
- Full-corpus retest after any live scoring change (`tune.py` above must stay 103/103, 0
  proposals) — the fetch-netting item ESPECIALLY (it reprices rungs corrections were fit
  against).
- TDD, REQ-tagged (`@pytest.mark.req`); next free: REQ-GEN-0064+, REQ-PLANNER-0035+. Windows +
  Linux both first-class; `encoding="utf-8"`; pathlib.
- Rules/card facts ALWAYS verified at `docs/rules.md` / `docs/rulebook.txt` /
  `data/EN_Card_Data.csv` — never memory (CLAUDE.md mandate). E.g. verify each shuffle
  Supporter's exact draw-count text before modeling pull-EV.

## Suggested skills

- **`grill-with-docs`** — REQUIRED, one session per item (they share no design surface; don't
  batch). The session updates the owning ADR inline as decisions land (0024 / 0023 / 0026).
- **`tdd`** — for the build after sign-off (the repo's precedent for every Pilot feature).
- **`code-review`** — before the PR (branch-review convention; the wiring pass ran it at max and
  it caught two real bugs — worth the effort level).
- Do NOT use `/blunder-buster` (no fresh corrections in play), `/deck-align` (no deck-layer
  change), or `/matchup-genie` (item 3 is the GENERIC lever; Briefs are its per-archetype
  sibling, explicitly out of scope here).
