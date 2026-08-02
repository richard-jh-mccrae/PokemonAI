# Keep-value v2 — session handoff (2026-07-20)

**For a fresh session picking up the ADR-0065 / keep-value-v2 line.** This session ran the full
deck-odds/card-worth review and built the Needs successor end-to-end (WP-N1 → N5d). Everything
below is committed on `claude/deck-odds-card-worth-review-jb2ik8` and suite-green (3057 + the
pre-existing `tests/meta_tracker` plotly-missing environment failures, not ours).

Authority docs (read in this order):
1. `docs/plans/keep-value-needs-assignment-grill-spec.md` — the grill, rulings, and the WP build
   log (N1–N5d, each with its measured verdict).
2. `docs/adr/0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md` §Build status
   — the full chronological build log.
3. `docs/adr/0065-glossary.md` — the five terms (Worth · Odds · Gates · Closure · Needs). Use them.

## What is LIVE (PROFILE, `src/common/runtime.py`)

| flag | state | meaning |
|---|---|---|
| ~~`needs_keep_value`~~ | **DELETED** (Issue #319) | keep-value v2 (`_needs_v2` → `needs.cheapest_removal`) decides the forced discard UNFLAGGED. The flag was read nowhere once Issue #261 item 2h made the call site unconditional, and it was the one decider lever with nothing to revert TO. Acceptance at the swap was agree_v2 **12/12**. |
| `discard_keep_value` | ON | v1 equation — now the FALLBACK decider + the **gamble** keep-value spine. (The REFRESH half left it 2026-08-01, ADR-0101: `_refresh_shed_keepcost` is `set_keep_v2`.) |
| `leaf_hand_value` | **OFF** | the readiness-leaf hand fold (N5b→N5d). Measured to a WASH (see §Closed). Do NOT arm without new leaf terms (below). |

⚠️ **The precedence chain below is GONE** — recorded as it stood 2026-07-20. Item 2h deleted
`discard_keep_value` and the `_DISCARD` ladder; Issue #319 deleted `needs_keep_value`. There is one
discard decider and no fallback under it.

~~Precedence at a forced discard: `needs_keep_value` > `discard_keep_value` > the `_DISCARD` ladder.
Each is a kill-switch; OFF falls through.~~

## The architecture in one paragraph

`common/needs.py` (pure) owns the slot vocabulary + the exact bitmask-DP assignment
(`assignment_value` / `keep_v2` / `set_keep_v2` / `cheapest_removal` with the residual-worth
tiebreak) + the two soundness nets (coverage lint `SUPPLIES`, `DISSOLUTION_LEDGER`).
**⚠️ Superseded in one place (2026-08-01, ADR-0101):** `_refresh_shed_shadow` is GONE — the refresh
SHED swapped to `needs.set_keep_v2`, so `_resolve_needs` now has two DECIDING consumers rather than one
decider and one shadow. Thread 1's swap bar ("flips ≈ 0", never met) was retired by ADR-0092, not
cleared; read ADR-0101 before acting on anything below that assumes the shadow exists.

`pilot._resolve_needs` is the ONE board→slots resolver (line+succession, deploy-now, fund-attack,
draw-engine band, supply-wincon, answer-doom, fuel, general-worth — the last excluded for the leaf
via `include_general=False`). Consumers: `_needs_v2` (discard decider + shadow columns
`keep_v2`/`eq2_pick`/`agree_v2`), `_refresh_shed_shadow` (magnitude shadow on
`Decision.refresh_shadow`), `_hand_readiness` (the parked leaf term, N5d deployability
counterfactual via the sim's `heldCtx` snapshot in `planner._simulate_line`).

## Benches (all offline, all runnable in-container)

- **Suite:** `python -m pytest tests/ -q --ignore=tests/meta_tracker` (~5 min; 3057).
- **Corpus sweeps:** `python tools/train/probes/needs_sweep.py` (NEW this session — the discard
  agree_v2 and refresh under/over-pricing reports; the WP acceptance numbers came from it).
- **Leaf lab:** `python tools/train/leaf_lab.py` → headline `SOLE-top 39/267 (15%), shared 190,
  avg-tie 3.0` at baseline. Force `pilot.leaf_hand_value=True` via a wrapper around
  `_cgpy_pilot_builder()` to measure the parked term. The decisive metric this session added:
  **E[correct picks] = Σ 1/tie-size over at-top rows** (the argmax rung breaks ties by option
  order) — compute it from `leaf_lab_report(...)["rows"]`.
- **Gate 0:** `python tools/train/probes/gate0_ab.py [--all]` (bound `gate0_ab.CAP=2500` for
  in-session runs; full `--all` at CAP=12000 exceeds a 10-min window — run backgrounded).

## Open threads, priority order

1. ~~**The refresh resupply discount**~~ **DONE 2026-07-20 (WP-N6)** — `_refresh_slot_resupply`
   (per-slot closure re-supply over the refresh window, `fetch_closure.class_reaccess_outs`) is
   LIVE in the refresh shadow. Measured: sign-flips 13→8, mean |v2−v1| 9.7→6.7, bias centered;
   discard held 12/12. `general` slots keep r=0.0 (their 0.45 W already carries the discount —
   stacking flipped the sweep unsafe; joint W+r re-measure only). **The swap bar (flips ≈ 0) is
   NOT met**: the 8 residual flips are v2 SCOPE gaps shared with the discard decider — the flat
   `answer_doom` TAG-tier slot value (over-prices a worth-0 switch at 20: 83661652-40;
   under-prices the doomed successor vs v1's full-worth closing spike: 83037962-49) and the
   saturating engine band vs v1's per-supporter sum (82522698-36). Re-pricing those is the NEW
   next piece — it feeds the discard bench too, so it needs its own adjudication (the 12/12 must
   hold through it).
2. ~~**Opponent DENY slots**~~ **DONE 2026-07-20 (WP-N7, grill spec #10)** — wired into
   `_resolve_needs`, valued by the shipped ADR-0062 oracle, graded by `_opp_turns_to_ready`
   (visible read, fail-closed). `SUPPLIES` gained `energy_denial` (the Hammers). Discard 12/12
   byte-identical; deadline-0 deny = resupply 0.0 (closing edge). NOTE the oracle is
   DAMAGE-denominated (~140 vs the ~8–30 worth tiers) — folded into the currency piece below.
3. ~~**Leaf-native who's-Active + tool terms**~~ **DONE 2026-07-20 (board-state grill §Build
   log)** — the promotion-ease lift SHIPPED (leaf-lab 40/190/2.99/84.7, zero regressed frames,
   Gate-0 up); the mobility micro-credit is HAND-ARMED behind `leaf_hand_value`. The N5d
   hand-fold re-measure with the new terms: 52/164 — STILL not cleared, stays parked. Hard cap
   found: 77/151 residual leaf ties are pure transpositions no board term can split.
4. ~~**THE slot-currency adjudication**~~ **DONE 2026-07-20 (WP-N8, grill spec #11)** — grilled
   with the user frame-by-frame, all three rulings built inside the assignment (no new
   gates/rungs/flags; one deletion): (1) answer-doom = the doomed body's preserved worth + the
   URGENT full-tier deadline-0 succession slot for the successor (not flat 20); (2) a duplicate
   saturating-need Supporter = 0 (no general slot for an engine-eligible cid); (3) the deny slot =
   `TAG_TIER["gust"]` disruption band graded by turns-to-ready, NOT the ADR-0062 damage swing
   (oracle → gate only; scoped so the leaf is untouched). Discard 12/12 byte-identical; leaf-lab
   40/190 unmoved; refresh flips 13→11. Four frames pinned (`test_needs_currency_rulings.py`).
   **The refresh-SHED swap and hedge retirement are UNBLOCKED of the currency question** — but
   still gated on their own benches (the swap bar = refresh flips ≈ 0, currently 11; hedge
   retirement still needs the sweep to show v2 never prices below the decider without the floor).
5. **Fold the shadowed `_DISCARD` rungs** out of `doctrine_fetch` once the in-ladder A/B clears
   (seam-D follow-up). **Assessed 2026-07-20: NOT satisfiable offline** — the A/B is a LIVE
   Kaggle-ladder measure (the `develop_rollout` precedent), `needs_keep_value` has zero ladder
   games behind it (armed 2026-07-20, dev window = no submissions ~a week), and folding deletes
   the kill-switch fallback. Stays gated until ladder evidence accrues post-window.
   ⚠️ **CLOSED by events, not by this item.** Issue #261 item 2h folded the `_DISCARD` rungs out of
   `doctrine_fetch` outright and Issue #319 deleted the kill-switch, so the thing this item was
   waiting to be safe enough to do has already happened and the fallback it worried about is gone.
6. **Hedge retirement** (WP-N4's note): `eq2_pick` floors at v1's post-gate keep. Resupply (1)
   and deny (2) have now LANDED, but the WP-N7 measurement says deny retires ZERO of the 13/68
   floor firings (the residual firers are engine supporters / burst rows / far-out denies — all
   legitimate fail-closures), so retirement rides its own sweep — measure whether v2 ever prices
   below the decider once the floor is removed.
7. **PLANNER-domain threads (surfaced in the WP-N8 grill, NOT keep-value — line evaluation, not
   pricing; each needs its own bench + build):**
   a. **Threshold-race snipe targeting** — pick the snipe that gets an opponent body under my
      finisher's damage threshold before my successor comes online ("Mega under Nebula's 210 in
      one more snipe from 230; but from 330 snipe the KO-able Staryu instead" — 83037962-49;
      Riolu-vs-Makuhita off their discard fuel gauge). All numbers visible.
   b. **Gust-line tempo evaluation** — a gust+KO on a bare bench body that returns their
      full-health fueled attacker to the Active is a bad trade (83457493-31: don't Boss here).

## Closed this session — do not reopen without new evidence

- **The leaf hand fold (N5b→N5c→N5d+ε)**: three shapes measured. Final: E[correct picks]
  83.5 → 84.5 of 267 — a WASH. Root cause proven: residual ties differ by who's-Active/tools (the
  leaf's other blindnesses); a hand term cannot read positional discriminators, so its tie-splits
  there are noise. The best shape (N5d deployability counterfactual + ε sizing) is committed and
  parked behind `leaf_hand_value`. **Re-measured 2026-07-20 after thread 3 landed: 52 SOLE / 164
  shared — shared-top still down, STILL PARKED.** The transposition cap (77/151 ties unsplittable
  by any board term) bounds what any further leaf/hand term can recover; next evidence would have
  to come from outside the leaf (search shape, not valuation).
- **86091435-68** is refuted-as-labeled (user re-review): the Hammer should be KEPT; the surviving
  substance is `test_deploy_now_drakloak_is_not_pitched`.

## Gotchas (this repo bites)

- **CRLF everywhere** (deck.csv, reviewed.json…): grep CRLF-tolerant; preserve terminators +
  indent style on JSON edits (`reviewed.json` = CRLF, indent 2 — raw-string insert, never
  `json.dump`).
- **Fresh Pilot per corpus replay** — pilots are stateful across `explain()` calls.
- **Native engine in tight reseed loops → `std::bad_alloc`**; the offline benches inject cgpy
  (`pilot._search_api = cgpy.compat.api`, the `leaf_lab._cgpy_pilot_builder` seam). cgpy is
  parity-limited: trust rankings, not absolute values.
- **`tune.py` clobbers `tuned.json`** — keep it out of build commits. `src/cg/` is off-limits.
- **Verify rules/cards at source** (CLAUDE.md): `docs/rules.md` → `docs/rulebook.txt`,
  `data/EN_Card_Data.csv`. Never from memory — the citation trap is real (a §2/§6 slip happened
  this session and was caught only by re-checking).
- **Adding a Pilot ctor flag** requires the PROFILE entry AND `tests/agents/test_runtime.py`'s
  `EXPECTED_SHIPPED` mirror (the wiring test enforces both directions).
- **Engine-RNG knife-edge flakiness (diagnosed 2026-07-20, the PR #121 CI failure):** the native
  engine's coins/shuffles are UNSEEDED and process-global — `search_begin` has no seed param — so
  a handful of engine-driven tests sit on RNG knife edges and can flake run-to-run in the FULL
  suite while passing standalone (ml f24 / `test_lethal_engine`'s own retry loop admits this).
  Two fixes landed from the f24 dissection and **both named the wrong channel** — corrected by #178
  (2026-07-27), read that first: f24 carries no COIN log at all, so the coin gate was a no-op there
  and the frame went on failing ~2 of 3 full-suite runs. The randomness is the **shuffle**, not the
  coin — and specifically a shuffle the policy triggers DURING the line (Professor's-Research class).
  `search_begin`'s OWN seeding shuffle is reproducible (determinism.md §4, re-measured 2026-07-27);
  the in-line one is not, and f24 draws all 11 of its cards after it. The rule still counts EVERY
  draw, not only post-shuffle ones, because the seeded deck order is our prediction either way —
  reproducing a guess does not make it knowledge. Both consumers now read a general `stream` bit
  (coin, draw, top-N peek, mill, face-down prize; a full-deck *search* is order-independent and does
  not count), and the develop rollout defers **all-or-nothing** when any candidate rode it. ⚠️ Do not
  reach for "re-run before diagnosing" on an engine-driven frame: a frame whose answer depends on the
  process's RNG position is a defect in what decides it (ADR-0072 amendment C), and re-running is
  the p-hacking that ADR deleted the `delta >= 0` clause for. (`test_lethal_engine`'s retry loop is
  NOT this class and stays: it re-rolls fresh unseeded battles to reach a board of the right SHAPE,
  and then asserts one fixed thing about it — not the same board answering differently.)
- The user's **dev window** (declared 2026-07-19): no Kaggle submission for ~a week; the corpus is
  the bench, ladder penalty-free, forward-leaning arming acceptable — but every arm still cleared
  its bench this session; keep that bar.

## Session ledger (branch `claude/deck-odds-card-worth-review-jb2ik8`)

Review passes (docs/refactor, then behavioral) → findings 1–4 fixed (duplicate-copy `_hand_keep`
reconciliation + fetcher gate; pre-anchor prize-split on the cost side; predicate hardening;
docstring honesty) → gate library completed (pressure, quota) → discard shadow → seam-D swap
(`discard_keep_value`, 9/9) → Drakloak line-member worth → keep-value v2 grill (6 rounds, ruled)
→ WP-N1 needs module + nets → WP-N2 exact assignment → WP-N3 resolver + shadow columns
(12/12 after 4 adjudications: succession slot, Pokémon-only lines, engine band, worth tiebreak)
→ WP-N4 discard decider swap (armed ON) → WP-N4b refresh magnitude shadow (verdict: not cleared)
→ WP-N5 general-worth slot (under-pricing 46→19) → WP-N5b/c/d+ε leaf fold (measured to its
ceiling, parked). Six stale plan docs retired; glossary at five terms.
