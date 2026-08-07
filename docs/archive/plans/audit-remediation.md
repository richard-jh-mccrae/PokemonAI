# Audit remediation — grilled plan (2026-07-14)

Post-merge audit of `main` after the strategy-update rounds: hunt for missed corrections, open
proposals, designed-but-unimplemented infrastructure, and implemented-but-inert seams. Grilled to
decisions; **nothing is built yet**. This doc is the record so the grill survives.

Status: **BUILT 2026-07-14.** All three oracles + WP1–WP7 shipped; suite 2901 green; W-route
dragapult 22/22, mega_starmie 115/115, mega_lucario 39/40 (its one gap, ep85058051 f4, pre-dates this
work). Commits: `d23b75a` (ADR-0060), `8c6c016` (ADR-0061), `e1f370f` + the pricing fix (ADR-0062),
`9cbf831` (WP1–WP6).

### What the build changed about the plan

The plan was right about the defects and wrong about two fixes. Both corrections came from measurement,
and both are worth carrying forward:

1. **ADR-0060's first cut broke the entire hand-quality guard family.** Pricing every moved card the
   same reached +76 and blew through `hold-wincon-dont-shuffle` (−25), `hold-irreplaceable-tool-dont-
   shuffle` (−30) and `dont-refresh-into-a-probable-miss` (−25) — all calibrated against
   `dig-before-commit`'s flat +20. The guards fired correctly and were outvoted. The fix was a better
   model, not a bigger constant: the four directions a refresh moves cards are **not worth the same**.
   A card I *shed* is one I chose to keep (certain, priced per card); cards I *draw* are unseen
   (speculative — a flat, bounded, guard-cancellable credit).

2. **ADR-0062's gate fix alone caused a regression against a human label**, and the obvious remedy was
   *disproved* by measurement: f29's raw denial (70) is more than double f15's (30), so no monotone
   pricing of magnitude can separate them. **Imminence, not size, is the discriminator.** The flat rung
   also could never *decline* a Hammer, because `_finish_turn_last` tiers a free Item ahead of
   everything — any positive score gets it played. Hence `_DENIAL_ITEM_COST` (the value of keeping the
   card) and a bench weight **derived** from the two labels (`< 30/70 = 0.43`), not chosen to taste.

Three test fixtures turned out to be describing **boards that cannot exist** — two claimed to disrupt a
hand-size attacker while giving the opponent zero cards in hand (Judge would *refill* them and arm the
very attacker), and one gave the opponent 2 Energy on a Pokémon whose only attack costs 1 (the strip
denies nothing). The old scorers could not represent a gift or a whiff, so nobody noticed. Boards fixed;
assertions untouched.

---

## Audit result: what was actually clean

- **Strategy proposals:** 70 applied / 2 refuted across 21 docs. **Zero `open`, zero `deferred`.**
- **Corrections:** `data/corrections/reviewed.json` = 110 covered / 22 refuted / 5 fixed. **Zero deferred.**
  Every fresh-looking frame in `tune.py --dry-run` traces to an applied proposal (85785606-1 →
  blunder-20260713 §44, 85785609-4 → §262, 85785609-t8 → §294, 85786096-t2, 85058051-4, 85164605-41).
  W-route: 23/23 (dragapult), 40/41 (mega_lucario), 120/120 (mega_starmie).
- **Suite:** 2845 passed / 2 skipped.
- The old "main.py omitted the kill-switches" bug is now **structurally impossible** — ADR-0055
  collapsed the shells into `src/common/runtime.py`, and `tests/agents/test_runtime.py:81` pins
  PROFILE ↔ `Pilot.__init__` as a bijection both ways (29 flags, zero drift).

## The meta-finding

Every Board signal the audit flagged as "unconsumed" turned out to be a **designed signal whose
consumer was never built** — not dead code. The orphan list was a *backlog of unbuilt features*.

| signal | verdict |
|---|---|
| `opp_hand_size_delta` | → the hand-swing **freshness** term (ADR-0060) |
| `my_discard_basic_energy` | → the **recover credit** re-source (ADR-0061) |
| `opp_has_energy_in_play` | → the **denial** presence gate (ADR-0062) |
| `bench_threat_present` | genuinely dead — doctrine reversed under it (see WP1) |

---

## Three closed-form oracles

### ADR-0060 — Hand-refresh value is a closed-form card-count swing

**Card facts (verified at source).** Judge and Harlequin are symmetric **refills**, not strips:

| card | my draw | opp draw |
|---|---|---|
| Judge (1213, Supporter) | 4 | 4 |
| Harlequin (1223, Supporter) | 5 \| 3 (coin) → **EV 4** | 3 \| 5 → **EV 4** |
| Unfair Stamp (1080, ACE SPEC **Item**, needs a KO on us last turn) | 5 | 2 |
| Lillie's Determination (1227, self-only) | 6, **8 at exactly 6 prizes** | 0 |
| Lacey (1199, self-only) | 4, **8 if opp ≤3 prizes** | 0 |

**The model.** One quantity governs all of them:

```
swing = (my_draw − my_hand_size) − (opp_draw − opp_hand_size)
fresh = min(max(opp_hand_size_delta, 0), opp_hand_size)   # their cards drawn last turn
score = K * swing + F * fresh          # fresh bonus only when swing > 0 (we are stripping)
```

- Judge (4/4) → `swing = opp_hand − my_hand`
- Harlequin (EV 4/4) → same EV as Judge, plus ±2 coin variance
- Unfair Stamp (5/2) → `swing = opp_hand − my_hand + 3`
- Lillie's (6 self-only) → `swing = 6 − my_hand`

**It reproduces every human hand-size correction exactly:**

| correction | swing | human's words |
|---|---|---|
| ml f111 — Judge, my 8 / opp 1 (**CRITICAL**) | −7 | "an enormous blunder" |
| ms f60 — Harlequin, my 11 / opp 2 | −9 | "a HUGE blunder, HUGE!" |
| ms f43 — opp 8 | ≈+5 | "a perfect time to play Harlequin" |
| ms f100 — opp 9 | ≈+6 | "a great time to disrupt" |
| ms f45 — opp 7, weak hand | ≈+4 | "harlequin would have done well here" |
| ms f94 — Lillie's, big hand | −1 at hand 7 | "never shuffle back hand greater than 7" (break-even is **6**) |

The code instead hardcodes `_STACKED_HAND = 6`, `_REFRESH_HAND_FLOOR = 5`, `_TAILORED_HAND = 3` —
**none of which is any card's break-even.** The card's own draw number *is* the threshold.

**Why they're grossly misplayed today.** The only rung that reliably fires on Judge/Harlequin is
`dig-before-commit` (+20 general / 23.0 dragapult / 18.24 mega_starmie), which is completely
hand-size-blind — it endorses them as "a draw card". Every hand-aware rung is broken or dark:

- `strip-the-stacked-engine-hand` (+22) also requires `opp_draw_engine_in_play` — the human never
  once mentions a draw engine. **The plain "they have 8 cards, Judge them" heuristic has no live rung.**
- `play-harlequin-vs-hand-size` (+25) gates on `opp_has_hand_size_attacker` — a tag carried by
  **exactly one card in the whole table** (Alakazam, 743). Effectively never fires.
- `dont-shuffle-away-the-bigger-hand` (−25) requires the `hand_disruption` tag, which **Lillie's
  lacks** → f94 uncovered; and hardcodes floor 5 when Judge's break-even is 4 and Lillie's is 6.
- `disrupt-the-tailored-hand` — weight **0**.

**Build.**
- Lift per-card draw counts out of the hardcoded `_DRAW_COUNTS` dict in
  `doctrine_shuffle_refresh.py` (which is **missing Unfair Stamp entirely**, so
  `dont-refresh-into-a-probable-miss` can never fire on it) into a `RefreshStat` on the Stat
  Provider (ADR-0056), with the real conditionals (Lillie's 8 at six prizes; Lacey 8 vs ≤3 prizes).
- New `_refresh_swing_tactical(obs, select, board, option)` in the `tactical` chain
  (`pilot.py:1196-1205`) — same shape as `_tactical` (KO oracle) and `_gust_tactical`. The scorer is
  `score = sum(fired hypothesis weights) + tactical` (`pilot.py:1208`), so a continuous card-fact
  term belongs in `tactical`, not in a boolean `Hypothesis`.
- **Gate `dig-before-commit` off `shuffle_hand`.** Its flat pull IS the misplay engine; the oracle
  becomes the sole owner of shuffle-refresh value. `dig-before-commit` keeps owning genuine digs
  (Ultra Ball, Poké Pad, tutors). Rationale: a negative override that must CANCEL a large flat
  general pull is fragile — see `[[hold-evolution-weight-inert]]`, inert for weeks at the wrong seed.
- **Delete** `strip-the-stacked-engine-hand` and `dont-shuffle-away-the-bigger-hand` (replaced).
- **`disrupt-the-tailored-hand`: refuted for symmetric cards.** It says `opp_hand ≤ 3` + they dumped
  → disrupt (+22 seed). But Judge *gives a 2-card opponent 4 cards* — a net **+2 for them**. It is
  only sound for a one-sided strip (Iono-class), and **no deck has one** — which is exactly why
  `strip-the-stacked-engine-hand` carries a dead `or "shuffle_hand" not in tags` branch. Keep at
  weight 0, re-annotated as an honest one-sided-strip forward contract.
- **Keep (orthogonal axes, not superseded):** `play-harlequin-vs-hand-size` and
  `disrupt-when-unfavored` (Alakazam's Powerful Hand scales damage with *its own* hand size —
  stripping denies **damage**, not cards), `dont-gift-a-refresh-when-favored` (posture), and the
  whole `hold-*-dont-shuffle` / `attach-before-hand-shuffle` guard family (card-identity quality).
- **Harlequin's coin:** score at EV 4/4 now; the ±2 variance is a follow-up for ADR-0039 gamble lines.
- **Sign convention, settled:** `opponent_resources.py:185` and `pilot.py:337` currently *contradict*
  each other. The freshness definition decides it: **positive delta = they grew their hand = fresh.**

**Test gate.** Must kill ml f111 (−7) and ms f60 (−9) **while keeping** ms f43 / f100 / f45 firing.
⚠️ f100 and f45 are already marked `covered` in `reviewed.json` — but *for the wrong reason*
("real Pilot plays Harlequin, dig-before-commit +20"). They pass today by the same blind +20 that
causes the blunders. That is the whole test.

**Bonus.** Two frames the ledger wrote off as unmodellable (`83116081-17`, `82754241-11` — "Lillie's
vs Harlequin is a Base-Value-Model call, not a weight gap") become **closed-form**: at my_hand 8
early game, Lillie's draws 8 at six prizes → swing **0**; Harlequin → swing **−3**. Prefers Lillie's.

**Retune.** Gating `dig-before-commit` perturbs two tuned decks. Re-run `tune.py --dry-run`, confirm
the W-route does not regress. Keep `tuned.json` out of the batch commit (it gets clobbered).

---

### ADR-0061 — A locking attack's value includes its forced follow-up (Horizon-2)

**The defect.** `_LOCK_COST = 40` (`pilot.py:36`) is one flat constant applied to **42 attacks** in
the pool that carry a next-turn lock — and they split into two structurally different kinds:

| lock kind | example | 2-turn damage | verdict on the flat 40 |
|---|---|---|---|
| **same-attack** ("can't use Mega Brave") | Mega Brave 270 / Aura Jab 130 | 270+130 = **400**, and 130+270 = **400** | **phantom charge** — order-invariant, the lock costs nothing |
| **full** ("can't use attacks") | Blood Moon 240, Giga Impact 250, Prism Edge 180 | 240 + **0** = **240**, losing to a lock-free 130/turn's **260** | **5× under-charge** — it costs a whole turn of offense |

`AttackStat` already carries the flags separately (`nextTurnSelfLock` vs `nextTurnSameAttackLock`,
used at `pilot.py:2013`); the scorer just collapses them.

**Mega Lucario ex (678, Stage 1 ← Riolu, 340 HP, {F}) — verified at source:**
- **Aura Jab** — `{F}`, **130** — "Attach up to 3 Basic {F} Energy cards from your discard pile to
  your Benched Pokémon in any way you like."
- **Mega Brave** — `{F}{F}`, **270** — "During your next turn, this Pokémon can't use Mega Brave."

**The model.** When an attack locks, next turn's option set is not a branching space to search — it
is **forced and known**. So evaluate the two-turn sequence closed-form:

- **full lock** → this Pokémon deals **0** next turn.
- **same-attack lock** → next turn is its best **other** attack.
- discount the second turn by **`active_doomed`** (worst-case, as designed — a doomed Active means
  there is no turn two, so the follow-up never materialises).

No search, no budget, no timeout risk, cannot regress the Tier-0/Tier-1 answer. This is the shape
that has shipped **four times** here (ADR-0039 gamble lines, ADR-0040 objectives, ADR-0044
opponent-choice reads, the Lethal Solver). The one actual *tree* — Tier-6 escalation — lost 12
points (44%, CI 41–47) and stays parked.

**The recover rider, repriced.** `_recover_units` (`pilot.py:1876`) already reads the discard
correctly (type-matched, capped at `recoverN`, zeroed on an empty bench) — via
`_damage_context["atk_discard_basic_by_type"]`. Two changes:

- **Re-source it to `board.my_discard_basic_energy`.** It is always MY recover rider, so the Board
  field is the honest single truth, and it retires a duplicate `_discard_energy_counts(me["discard"])`
  call made twice per decision. (`_damage_context` keeps its own key — that one is *attacker-relative*
  and must also serve the opponent direction for Riptide-class scalers.)
- **Replace the flat `_ENERGY_RECOVER = 75`/energy with a recipient-threshold credit.** Today
  `_recover_units` gates only on `board.my_bench` being non-empty, so three `{F}` onto a
  Lunatone/Solrock support bench scores an identical **+225** to three `{F}` onto a Riolu that becomes
  the second Mega Lucario ex — and that +225 is exactly what tips Aura Jab (355) over Mega Brave
  (230). Value each recovered `{F}` by whether it moves a benched line-member **across its attack
  cost**. Add successor-insurance when `active_doomed` (the bank is the only thing that survives).
  The repo already knows this asymmetry — ml f87 produced a rule that "loading discard-{F} onto
  Solrock is inert" — but that rule lives at the **placement** select, after we have already
  committed to Aura Jab.

**Not changing:** `fire-lunar-cycle` stays as-is. Its "the discarded {F} is Aura Jab fuel" premise is
never verified against Aura Jab being reachable, but the user ruled the premise holds in practice
(4 Riolu, the Mega is the wincon).

**Evidence discipline.** Probe **real frames** (mega_lucario Mega Brave; mega_starmie Cinderace ex
Flare Strike 280, also a same-attack lock) — never hand-built menus, per
`[[isolated-probe-phantom-misplays]]`. The `_LOCK_COST` defect is provable from card text regardless.

---

### ADR-0062 — Energy denial is a closed-form denial oracle

**Card facts (verified at source).**
- **Crushing Hammer** (1120, Item): *"Flip a coin. If heads, discard an Energy from **1 of your
  opponent's Pokémon**."* — **4 copies in dragapult_ex AND mega_starmie.**
- **Enhanced Hammer** (1081, Item): *"Discard a Special Energy from **1 of your opponent's Pokémon**."*

**Engine confirms Active *or* Bench.** `op_trash_energy_enemy` in the trace-verified twin
(`src/cgpy/chain.py:562`) builds the option list from ACTIVE + BENCH; `activeOnly` is a *different*
flavor (the attack-rider one) that Crushing Hammer does not set. Pinned against real traces
(`ml_dx_2001 f175`, `ml_dx_2000 f95`, `ms_mirror_1001 f83`, `ms_mirror_1002 f14`).

**Three defects, each independently causing waste:**

1. **The presence gate is narrower than the card.** `play-energy-denial`
   (`baseline_disruption.py:40`) gates on `opp_active_has_energy`, so we **stand down entirely when
   their Active is bare but their bench is loaded** — the standard TCG pattern (power up on the
   bench, promote later). Against a bench-loading deck, 4 Hammers sit dead in hand all game. The f37
   fix (ep82753102) cured a real whiff, but by checking the wrong pile. **`opp_has_energy_in_play`
   is the gate the card and the engine actually support.**
2. **No whiff model.** Stripping 1 energy from a body carrying 4 whose attack costs 2 accomplishes
   nothing — but the rung fires anyway (+20, flat). And it is a **coin flip**: half of all Hammers do
   nothing regardless, and nothing prices that.
3. **The target select is unscored.** **Zero rungs anywhere fire on `DISCARD_ENERGY`.** When a Hammer
   wins its flip, every option scores 0 and the argmax falls through to index 0 — which the engine
   orders **oldest-attach first**. We strip whatever energy landed first, which can be a Basic on a
   benched support mon. This is the literal waste.

**Build one closed-form oracle covering all three,** same shape as the KO oracle:
- **Presence:** `opp_has_energy_in_play` (Active OR Bench).
- **Denial value:** for each candidate energy, does removing it drop that Pokémon **below the cost of
  the attack it would use**? Closed-form off `_attack_cost` + their visible energies. **If nothing
  crosses a threshold — they have surplus energy everywhere — the Hammer is worthless and we HOLD
  it.** That is the waste-prevention.
- **Target select:** score `DISCARD_ENERGY` so a won flip strips the energy that actually turns an
  attacker off. Rank by denial value: **Active first, bench when the math says so** (a benched body
  one energy short of a lethal attack, about to be promoted, is a bigger deny than shaving a surplus
  energy off an Active that can attack anyway).
- **Coin:** halve for the 50%. (Enhanced Hammer has no flip, but is Special-Energy-only.)

---

## Cleanup work packages

### WP1 — Snipe fossil + the ungated CRITICAL

`Board.bench_threat_present` (`pilot.py:224`, computed `:2873`, helper `:3538`) is a **fossil**. Git
history: introduced `30bcc4a` (2026-06-29) with exactly one consumer,
`snipe-the-strongest-evolving-threat`, which was **retired in `e120d6f`** (2026-06-30) on a
subsumption argument. The field survived; the consumer did not. When `snipe-the-evolving-threat` was
**restored** 2026-07-09 it deliberately came back with a *different* gate
(`not target_forward_form_in_play`) — because CRITICAL correction **ms 85164131 f22** had
established the opposite doctrine: a developing higher-prize wincon pre-evo **outranks** an energized
current attacker.

⚠️ **Wiring the field in would REGRESS f22**, not fix it. Verified by monkey-patching
`and not c.board.bench_threat_present` into the rung's `when()` and re-running every snipe fixture:
`evolving_wincon_on_bench` zeroes Cinderace's three rungs (90→0), `bench_threat_present` would zero
Staryu's rung (45→0), **both targets land at 0.0**, and the argmax degenerates to index order →
picks Cinderace, the exact blunder. Its two docstrings assert a policy the codebase has since reversed.

**Do:**
- Delete the field, its compute, and `_bench_threat_present()`. Behavior-neutral (zero readers).
- **Add the missing pytest.** `ms_snipe_evolving_wincon_over_promotion_stack_f22.json` exists as a
  fixture but **no test consumes it** (`test_snipe_the_real_attacker.py:33` parametrizes only
  f75/f47/f39/f85). The CRITICAL has **no regression gate** — the fossil's lie survived two weeks of
  contradicting doctrine because of exactly this. Pin `decide() == [1]` (Staryu), scores
  `[(Cinderace, 0.0), (Staryu, 45.0)]`.
- Add a **kill-switch counter-test**: with `evolving_wincon_priority=False`, f22 picks `[0]`
  (Cinderace, 90) — pins *why* the switch exists.
- Add a **degeneracy guard**: assert not all snipe targets score 0.0.

### WP2 — Honest annotation of the remaining true orphans

Only two survive the oracles above:
- `brief_is_threat` / `brief_target_role` / `brief_target_ids` (`pilot.py:501-510`) — zero `src/`
  callers, tests only. (Sibling `brief_target_roles` **is** live, feeding `_matchup_plan` — which is
  what makes the threat half easy to miss.)
- `rider_recoil` (`strategy/combat.py:132`) — zero callers, **zero tests**. Siblings `rider_snipe` /
  `rider_spread` are both live.

### WP3 — Close the silent-inert weight trap

`Hypothesis.weight: float = 0.0` (`strategy/strategy.py:68`) means a rung authored **without**
`weight=` is born inert and is **indistinguishable at runtime from a deliberate weight-0 seed**.
Make it required (no default). Field order stays legal (`status` keeps its default and follows).
Verified: **zero call sites in `src/` omit `weight=`** — compile-time-only, no behavior delta. Add a
test that omitting it raises `TypeError`.

The deliberate weight-0 seed pattern is **preserved** — you still author the rung, you just write
`weight=0` explicitly, stating intent. The tuner fits over *all* registered hypotheses, so a
weight-0 seed is still promoted off zero once corrections exercise it. The four current weight-0
rungs (`disrupt-the-tailored-hand` SEED 22, `unfair-stamp-comeback-posture` SEED −18,
`play-safe-when-ahead-on-prizes` SEED −8, `dont-spend-unneeded-supporter` SEED −15) **stay at 0**.
Note `play-safe-when-ahead-on-prizes` is the **only** hypothesis in `baseline_posture.py`, so that
whole cluster is inert.

### WP4 — ADR status truth pass

**Five statuses are demonstrably false:**

| ADR | claims | reality |
|---|---|---|
| 0035, 0036 | "build pending" | `/deck-align` is built and shipped |
| 0047 | "no consumer wired yet" | `opp_resource_reads` is `PROFILE=True` |
| 0050-multistep | "Phase 3 UNBUILT" | `retreat_enabler_lethal` + `disruptor_lock_maneuver` both `PROFILE=True` |
| 0038 | `brief_engine` "wired but default OFF" | **retired** from code (`runtime.py:44` — ADR-0051 `matchup_targeting` supersedes); no superseded marker on 0038 |

**Rewrite ADR-0042's headline.** Its "50% (CI 48–53)" describes the **seed** model, which is **not
what is on disk**. A pipeline bug was found (`tune.py`'s `_build_pilot` dropped the Scout, so
`favorability` was neutral in *every* training row), the model was retrained on 92,454 cross-deck
rows (holdout log-loss 0.5551), and the real A/B was a paired-delta over **48,000 games**:
**−0.55%, CI [−1.27%, +0.16%]**, 5 of 6 matchups negative → parked.

**Add to ADR-0043:** escalation is `search_budget`'s **only** functional consumer. Tier-1 engine sims
(`planner_engine_rank`, `lethal_verify`, `lethal_family`) run **unbudgeted**. Raising `search_budget`
silently re-labels telemetry **and the submission manifest** as Tier-1
(`tests/submit/test_submit_brief.py:79` pins it), which changes the competition writeup narrative.

**Backfill** a one-line `**Status.**` header on the **31** ADRs that have none — including the four
newest (0052, 0054, 0055, 0056).

### WP5 — Stale in-code comments

- `"search_budget": 0,  # 0 = Tier-0 closed-form; >0 = Tier-1 Search` is **false** — fix in
  `dragapult_ex/strategy.py:125`, `mega_lucario/strategy.py:362`, `mega_starmie/strategy.py:55`,
  `runtime.py:29`. Add one-line "why parked" notes on `value_model` and `escalation` in PROFILE.
- `mega_lucario/STRATEGY.md:1021` claims Unfair Stamp is **missing** `shuffle_hand`. It has it
  (`1080 → ["draw","hand_disruption","shuffle_hand"]`).

### WP6 — ADR renumber + index

Three numbers are used twice. Rule: each pair is one **strategy** ADR and one **tooling** ADR, and
the bulk of the inbound prose references point at the strategy one — so **the tooling ADR moves**.

| moves | → | keeps the number | inbound refs to the number |
|---|---|---|---|
| `0022-selfplay-corpus-uses-cabt-env-path` | **0057** | `0022-gust-is-closed-form-lethal-lookahead` | 46 |
| `0033-arena-captures-pvc-on-cabt-env-path` | **0058** | `0033-transient-attack-effects-…` | 32 |
| `0050-cgpy-is-a-trace-verified-python-twin-…` | **0059** | `0050-multi-step-lethal-verification-tool` | 92 |

`0050-glossary.md` **stays** — it is the correctly-numbered companion to the lethal ADR, not a third ADR.

`git mv` (preserves blame), rewrite each H1, sweep inbound refs across `docs/`, `src/` comments,
`tests/`, `tools/`, `.claude/skills/`. Ship **`docs/adr/README.md`**: number → file → title → status,
so the next audit is a grep. Fix `docs/plans/ml-training-build.md:207-209` (claims 0052/0054/0055/0056
live on an "unpushed arch-review branch" and that "next free is 0057" — all four are merged).
**Next free after this plan: 0063.**

### WP7 — Verify

Full `pytest tests/ -q` (2845 + the new gates), green on Windows **and** Linux via CI.

---

## Explicitly NOT doing (decided)

- **`value_model` stays OFF.** The structural argument holds regardless of any A/B: its top weights
  (`prize_diff`, `my_prizes_remaining`, `my_active_hp`, `active_doomed`) are exactly what the
  closed-form leaf already scores, so a general logistic over redundant inputs adds miscalibration,
  not signal. Its only matchup-conditioned features carry weights of **+0.047** and **+0.029**.
  ADR-0053 replaces the artifact wholesale at G2.
- **`escalation` stays OFF.** 44% (CI 41–47) on the one instrument the docs call *valid*, both seats
  sub-50. Root cause (its closed-form two-ply leaf) is unchanged.
- **The four weight-0 seeds stay at 0.**
- **ADR-0053 / ML training WP0–WP6 stays out of scope** — a documented multi-session plan of record,
  not an accidental gap.
- **Supporter-economy opportunity cost** (ADR-0023's deferred seam) — **REFUTED 2026-07-14, do not
  build.** The claim was "one Supporter per turn is a hard rule and nothing prices the slot." False:
  the slot is priced **structurally, by play-ORDER**, in `_finish_turn_last` — tier 0 free Items →
  **tier 1 the one-per-turn Supporter** → tier 2 blind attach → tier 3 hand-shuffle refresh → tier 4
  the turn-ending attack. Its docstring already names the Pokégear-upgrades-your-Supporter argument.
  Checks that pass: a KO-enabling gust Supporter jumps to tier 0 (`gust-for-the-ko`); the tier-3
  shuffle test keys on the **`shuffle_hand` tag**, not `is_supporter`, so **Unfair Stamp (an Item) is
  correctly held behind the attach**; a tier-4 rule stops a setup Supporter burying Boss's Orders
  (dragapult f81); the Planner refuses to plan two Supporters (`planner.py:1561/1626`); and
  within-turn contention needs no rung — both Supporters sit in one menu, argmax picks the better, and
  the engine makes the rest illegal once `supporterPlayed` flips.

  **Evidence:** all **10** human corrections mentioning a Supporter, retested through the real Pilot —
  6 pass, and the 4 "failures" are single-frame-label artifacts (ms 82227388-30: the Pilot plays the
  Pokégear the rationale itself asks for, then attaches; ms 85164605-41: it plays *neither* tutor and
  simply evolves, beating the human's own suggestion).

  **How the phantom arose:** inferred from `dont-spend-unneeded-supporter` sitting at **weight 0**.
  That rung is about holding the *card* for a later decisive turn — not about the slot — and reading
  behavior off a weight is the `[[wroute-satisfied-not-fixed]]` trap running in reverse. It stays at 0:
  no correction demands it.

## Order

ADR-0060 → ADR-0061 → ADR-0062 → WP1 → WP3 → WP2/WP5 → WP4 → WP6 → WP7. One commit per unit.
