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
| `needs_keep_value` | **ON** | keep-value v2 (`_needs_v2` → `needs.cheapest_removal`) DECIDES the forced discard. Acceptance: agree_v2 **12/12** on the discard corpus; the duplicate-wincon pair flips without a new gate. |
| `discard_keep_value` | ON | v1 equation — now the FALLBACK decider + the gamble/refresh keep-value spine. |
| `leaf_hand_value` | **OFF** | the readiness-leaf hand fold (N5b→N5d). Measured to a WASH (see §Closed). Do NOT arm without new leaf terms (below). |

Precedence at a forced discard: `needs_keep_value` > `discard_keep_value` > the `_DISCARD` ladder.
Each is a kill-switch; OFF falls through.

## The architecture in one paragraph

`common/needs.py` (pure) owns the slot vocabulary + the exact bitmask-DP assignment
(`assignment_value` / `keep_v2` / `set_keep_v2` / `cheapest_removal` with the residual-worth
tiebreak) + the two soundness nets (coverage lint `SUPPLIES`, `DISSOLUTION_LEDGER`).
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
2. **Opponent DENY slots**: `needs.deny_slot` + `turns_to_ready` exist (WP-N1, tested) but the
   resolver never emits them — needs the visible opponent read (their bodies' energy deficit +
   forward hops) wired into `_resolve_needs`. The Hammer/gust cards currently ride the hedge.
3. **Leaf-native who's-Active + tool terms** (board-state-valuation-grill.md) — the measured
   prerequisite for ever arming `leaf_hand_value` (§Closed below). This is LEAF work, not needs
   work; it re-opens the hand fold afterward.
4. **Fold the shadowed `_DISCARD` rungs** out of `doctrine_fetch` once the in-ladder A/B clears
   (seam-D follow-up; the rungs are dead code under the swap but still shipped).
5. **Hedge retirement** (WP-N4's note): `eq2_pick` floors at v1's post-gate keep. Retire only when
   resupply (1) and deny (2) land — "v2 never prices below the shipped decider" until the resolver
   is complete.

## Closed this session — do not reopen without new evidence

- **The leaf hand fold (N5b→N5c→N5d+ε)**: three shapes measured. Final: E[correct picks]
  83.5 → 84.5 of 267 — a WASH. Root cause proven: residual ties differ by who's-Active/tools (the
  leaf's other blindnesses); a hand term cannot read positional discriminators, so its tie-splits
  there are noise. The best shape (N5d deployability counterfactual + ε sizing) is committed and
  parked behind `leaf_hand_value`. Re-measure ONLY after thread 3 lands.
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
  Two SOUND fixes landed from the f24 dissection: `_engine_leaf_value`'s win short-circuit is
  COIN-GATED (a simmed "win" that consumed coin flips ranks as an ordinary board — only the sound
  win rung claims wins), and the develop rollout EXCLUDES coin-contaminated sims from its ranking
  (override authority requires a reproducible end-board; ml f24's bench-Meowth line simmed 162 on
  one stream and a phantom outright win on another). A residual environmental flake (a test whose
  own retries lose the RNG lottery) is possible on any CI run — re-run before diagnosing; a
  standalone-passing failure in an engine test is this class.
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
