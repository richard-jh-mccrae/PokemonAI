# Deploy decider swap — review & hand-off (Issue #197, ADR-0086)

Self-contained pickup doc for the **Deploy Marginal** build (Phase 1h of the Value System, tracker
Issue #136). Sibling of `attach-decider-swap-review.md` / `evolve-decider-swap-review.md` /
`promote-retreat-decider-swap-review.md`.

**Branch:** `claude/bench-filling-pokemon-abilities-8otrk9` · **Suite:** green (4011 passed) ·
**Decision Gate:** PASS · **Deletion:** NOT applied (deliberately — see step 2).

---

## The next session's order — do these in sequence

### 1. Fix the line deadlines in `_resolve_needs` (DO THIS FIRST)

Supply the board-derived power-up timing so a **win-condition base outranks a re-drawable secondary
line on its own**, rather than resupply deciding it alone.

`needs.line_slots` already accepts `deadline` / `succ_deadline` — ADR-0065's own note says they carry
"the line's board-derived power-up timing", and that without them a wincon one attach from live is
"priced as freely re-fetchable". `_resolve_needs` does not supply them, so on the deploy path **every
line slot sits at `dl=99` (latent)** and the only thing separating two 20-tier lines is `resupply`.

Measured on `83661652-44`:

```
slot [0] line:673  v=20.0  dl=99  resupply=0.00   <- Makuhita's line (deck holds none)
slot [1] line:677  v=20.0  dl=99  resupply=0.87   <- Riolu's line   (deck holds more)
Makuhita total=16.67   Riolu total=2.19
```

The equation reasons "Makuhita is your last one, Riolu you can re-draw" — scarcity, correctly
computed, standing in for urgency. Benching Riolu **starts the Mega Lucario evolve clock a turn
earlier** and re-drawing it later never recovers that turn. That is what the deadline encodes.

Beware the shared blast radius: `_resolve_needs` also serves the discard decider (`_needs_v2`) and the
refresh-SHED site. Changing it must not move their behaviour — check `test_needs.py`,
`test_hyperclosure_corpus.py` and the refresh tests.

### 2. Re-apply the deletion, arm `deploy_value` ON

Nine rules, all named in ADR-0086's Consequences:

* `baseline_bench.py` — `dont-bench-multiprize`, `pre-position-attacker`, `develop-a-basic-in-setup`,
  `develop-the-wincon-base-first`, `dont-bench-onto-their-path`, `develop-the-accel-recipient`
* `doctrine_fetch.py` — `bench-the-supporter-tutor`, `dont-pre-bench-the-supporter-tutor`,
  `dont-pre-bench-a-redundant-utility`

**`keep-a-bench` STAYS** — decision 7 promotes it to the post-setup sound rung
(`Pilot._empty_bench_forced`), it is not deleted. It is also absent from the sweep's `RETIRED` tuple
for the same reason.

Then flip `deploy_value` to `True` in `runtime.PROFILE` **and** in `tests/agents/test_runtime.py`'s
`EXPECTED_SHIPPED`. It is currently **armed-OFF on purpose**: the decider is wired into
`_option_trace`, so ON while the nine rungs are still live would DOUBLE-COUNT every bench play. That
armed-off state is also exactly what the sweep needs (two pilots, one each way).

### 3. Triage the 16 failures the deletion causes

Verified by running it once; the deletion was then reverted to keep the branch green.

**Delete — these test rules that no longer exist (4):**
- `test_general_strategy.py::test_dont_bench_multiprize_penalizes_a_nonwincon_ex_but_exempts_the_wincon`
- `test_general_strategy.py::test_dont_bench_multiprize_also_penalizes_evolving_into_a_nonwincon_ex`
- `test_general_strategy.py::test_pre_position_attacker_develops_the_bench_during_race`
- `test_blunder_20260713_routing.py::test_f4_declines_pre_benching_a_redundant_utility_basic`

**Re-point — built against the ctor default (features OFF), so they exercised the deleted rule rather
than the decider (2):**
- `test_empty_bench_rung.py::test_the_guard_does_NOT_fire_during_set_up`
- `test_setup_bench_decline.py::test_decline_only_drops_a_discouraged_pick_not_a_neutral_basic`

Both need `Pilot(..., deploy_value=True)`. Verified directly:
`deploy_value=False -> decide=[0]`, `deploy_value=True -> decide=[]`. The decline works; the test
construction was wrong.

**Investigate — do NOT rewrite to match behaviour (the rest):**
- `test_blunder_20260703_develop_wincon_base.py` **f44** — already HELD OUT to `#165` via a
  `claims.decision` owner on its fixture. Reports, does not gate.
- ...**f33** — now an accepted-set frame (`correct_alternatives [[1],[2]]`, ruled 2026-07-30):
  Solrock and Riolu are both correct. Should pass once its consumer honours alternatives.
- ...**f40** — **the real test of step 1.** `correct` stays `[3]` Riolu ALONE, deliberately: the error
  is playing Lillie's while Riolu is in hand, and playing Solrock would not save it. It asks whether
  the Deploy Marginal can outbid `dig-before-commit` (+20) for a win-condition base. On f44 Riolu
  priced **2.19**, so on current numbers **it cannot** — expect f40 to fail until step 1 lands, and
  treat that failure as real.
- `test_hyperclosure_corpus.py::[83661652-29]` — a second consumer that does not yet know about
  `correct_alternatives`.
- `test_telemetry_reorder_markers.py::test_real_attack_last_decision_emits_deferred_and_reordered` —
  probably incidental score movement; confirm rather than assume.

### 4. Gates, review, PR

- **Discrimination Gate BEFORE the arming decision** (ADR-0072 decision 5 is explicit about the
  ordering): `python tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json`.
- **Decision Gate** — already PASS, but re-run after step 1 since the equation changes:
  `python tools/train/probes/deploy_decider_sweep.py`.
- **Tripwire A/B** — `gauntlet_swap_ab.py --stage mid-build` (this swap DELETES what its flag would
  fall back to, so the two-build harness is the right instrument, not `gauntlet_ab.py --overlay`).
- The **Leaf Profile** field-set pin WILL move (the ability and accel legs add reads) — re-measure
  deliberately.
- Then `/code-review`, then the PR (title `Issue #197: ...`, template layout, rebase onto `main`
  first, `subscribe_pr_activity` immediately, `send_later` at a 5-minute cadence).

---

## What is already built and committed

| commit | what |
|---|---|
| `177a719` | `option_slot` resolves a hand play to `("card", id)`; `DEPLOY_LANE`; `DEPLOY_BAND` / `DEPLOY_WORTH_SCALE` in `currency.py`, guard widened not deleted |
| `43fe81c` | capacity-bounded `assignment_value` + `needs.deploy_marginal`; `supporter_tutor` into `SUPPLIES` |
| `f1bbe4c` | `common/deploy_value.py` — the four-leg equation, 11 tests |
| `b1e3310` | `_bench_path_delta` returns the magnitude, not its sign |
| `e1ec2de` `3300a18` | Pilot delegation, wired into `_option_trace`, armed OFF |
| `3ec6f6e` | post-setup empty-Bench guard as an order FILTER |
| `7edea59` | the accel-unlock leg made real |
| `99733b3` | the decider sweep + `deploy_working` telemetry |
| `dca7136` | the supplier/resupply split |
| `8c6534f` | exposure falls back to prize liability when the Path is unreadable |
| `952fe35` `72d367c` `ea85ddf` | the corpus rulings (f44, f29, f33/f40) |

## Rulings on the record (do not re-litigate)

- **f44** → held out to `#165`. Attach spent, Supporter spent, only Power Gem scores — the turn was
  already misspent before this decision. A planner defect, not a pricing one.
- **f29** → accepted set `[[0],[1],[6]]`: Riolu, Makuhita and Solrock all correct; the error is the
  Ultra Ball. *"ordering doesnt matter. just dont play ultra ball."*
- **f33** → accepted set `[[1],[2]]`: the rationale names both basics.
- **f40** → NOT a set. See step 3.
- **f51** → re-ruled to `correct: [0]` (play Lillie's) with an explicit gating `claims.decision`;
  added a scorable frame to the Discrimination Gate baseline, which was re-captured (`797f93e`).

## Corrections to the ADR made during the build

- **Amendment E** — decision 2's written form (`V(C) − V(C, X pinned)`) is ≤ 0 for every candidate and
  can never clear `_finish_turn_last`'s floor. Corrected to
  `net(X) = V(X deployed now, cap=K) − V(C \ X, cap=K)`. Gain and displacement are **not** two
  subtractable terms — at tight capacity the gain already nets the displacement.
- The Needs DP had **no capacity bound**; displacement cannot exist without one. Added as a popcount
  bound (each assigned card covers exactly one slot).
- **Deck copies are not substitutes for hand copies.** They enter as slot `resupply`, never as rival
  suppliers — the first build made every hand body redundant against its own deck twin.
- **Decision 3's derived zero is not sufficient** to decline at `_SETUP_BENCH`: take-fewer drops only
  `score < 0`. The exposure leg falls back to the body's own prize liability where the Prize Path is
  unreadable.

## RULED — Amendment F is WITHDRAWN, option (a) (2026-07-30, user)

*"option a sounds like cleanest solution reusing existing machinery"* — the narrowed rule wins, f3
goes back to DECLINE, and the frame is held out of the Decision Gate.

**The schema check that made it more than a tidiness call.** At `decision` scope `correct` is
mandatory and must index a legal option (`build_correction`, `correction.py`), so `correct: []` — the
only way to say "decline" — is rejected. All 10 corpus records carrying it are `turn` scope. f3 is
therefore not a mis-recorded fixture; it is a record shape that **cannot state the ruling**, which is
exactly what the Held-out Ledger exists for. Thirteen records repo-wide share the `chosen == correct`
shape; three are this decline shape (`83661652` f3, `86088989` f3, `85785609` f4 — the dragapult
Munkidori sibling, whose own note already reached the same conclusion independently).

**`owner` names the ground, not a borrowed issue.** The ledger's `owner` means "another issue owns
the fix", and #165 does not own this — the Turn Planner is irrelevant to a record-shape limit. The
claim reads `#197-record-shape` so the ledger stays honest about why the frame is out.

**Coverage is not lost.** `test_f3_declines_pre_benching_the_supporter_tutor` asserts the decline on
this exact board and is now the ruling of record. Holding the frame out removes a false signal from
the sweep, not a test.

**Still open, deliberately NOT taken with it:** the in-game half. Decision 7's empty-Bench filter
still forces a body unconditionally, where the narrowed rule would ask for a doomed Active. That is a
different kind of change — the filter guards a LOSS, and gating a loss-guard on a prediction trades a
bounded cost (one wasted Ability) for an unbounded one (losing the game on a bad doom read). It wants
its own sitting. Recorded on `_empty_bench_forced`.

### The original grill point, for the record



**The point, verbatim:** *"Shall only bench Meowth when bench empty IF our active is doomed OR we
need a specific supporter (which is issue #165 computation). if its early game and no KO threat, we
can wait a turn."*

Amendment F currently stands the Set-Up exposure fallback down whenever the Bench is empty and no
other Basic is held — an UNCONDITIONAL stand-down. The grill point narrows it to two triggers:

1. **the Active is doomed** — a real KO threat this coming turn, so there may be no next turn to
   bench in; or
2. **we need a specific Supporter** — the Ability leg's own question, which is #165's computation.

Absent both, waiting is strictly better, and the reason is sharper than "it's early": **you can bench
Meowth on your own first turn and still GET Last-Ditch Catch.** `docs/rules.md` §2 — the player going
first cannot attack on turn 1 and the player going second acts only after that turn — so my first
turn precedes the first legal attack either way. Benching at Set Up spends the Ability for a body I
could have had one turn later WITH the fetch. The one-body risk Amendment F prices does not
materialise until the opponent can attack, which is after that turn.

### The tension this must resolve — as stated, it REVERSES f3

f3 is `turn 0`, pregame: no KO threat exists, and the Ability cannot fire at `_SETUP_BENCH` by
derivation (decision 3), so **neither trigger is met** and the narrowed rule declines — the ruling
Amendment F was written to overturn, on the 2026-07-30 Decision Gate sitting.

Both readings cannot hold. The choice is:

- **(a) The narrowed rule wins, f3 goes back to DECLINE.** Amendment F is withdrawn and the
  `83661652|0|decision|3` sweep frame returns to a REGRESSION needing a different disposition
  (degenerate-record hold-out is the obvious candidate — `chosen == correct == [0]`, one option,
  `minCount 0`, so the record cannot index a decline; 13 records repo-wide share that shape).
  Reverts `test_f3_benches_the_tutor_because_it_is_the_only_body_held`.
- **(b) Amendment F stands for the PREGAME only, and the narrowed rule governs the in-game empty
  Bench.** Distinguishable: at Set Up the placement is free of the Ability trade-off in one
  direction only — you cannot fire it now, but you also cannot be attacked before your own turn.
  This needs a reason why the pregame differs that is not just "f3 was ruled that way".
- **(c) The narrowed rule wins everywhere AND f3 keeps its ruling on a different basis** — i.e.
  something other than the one-body argument justifies benching there.

**Not implemented pending that ruling.** What is measured today: at f3 the placement scores exactly
0.0 (stood down, never endorsed), so whichever way this goes the body is never *recommended* — only
un-penalised. Note also that trigger 2 is dead at `_SETUP_BENCH` by decision 3's derivation, so under
the narrowed rule Set Up reduces to trigger 1 alone.

## Known-open, recorded rather than fixed

- The **line-deadline gap** — step 1.
- `_PATH_BENCH_EXTRA = 1` may be stale against ADR-0071 decision 6 (ADR-0086 decision 5's observation).
- `currency.py` on `main` still says the anchor capture is "issue #199's build-shape step 1", which
  ADR-0080 superseded.
- The spec comment on Issue #197 still lists f51 under "must be re-ruled" — now satisfied.
