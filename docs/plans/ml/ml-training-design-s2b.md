# Build Session 2b Design — Eval Harness (Work Package 2): GRILL SCOPE (not yet locked)

> **STATUS: GRILL SCOPE — decisions are OPEN.** This is the pre-grill agenda for the Build Session 2b design
> session, laid out so the grill starts from verified ground (matching the shape of the LOCKED
> [s2a](ml-training-design-s2a.md) / [s3b](ml-training-design-s3b.md) docs). Every `Q#` below is a
> fork to *resolve*, not a decision. Each carries a **seed** (a recommended answer + why) purely to
> give the grill something to attack — seeds are not locked. When the grill concludes, this file is
> rewritten in place to LOCKED `D#` decisions and the [build ledger](ml-training-build.md) row Build Session 2b
> flips to "design LOCKED".
>
> **Do not build against this doc.** Plumbing that consumes a `Q#` seed before the grill locks it
> is at risk of rework.

**Governing:** [ADR-0053](../adr/0053-ml-training-pipeline-build-plan.md) · scope summary in
[ml-training-build.md §Build Session 2b](ml-training-build.md) · evidence
[research report](../research/ml-training-system.md) findings 6 / eval-methodology block.

**Owns (per build plan):** `tools/sim/eval*` — **new files only**. Reuses (does not modify)
`battle.py`, `paired_ab.py`, `gauntlet_ab.py`, `score_diff.py`, the corpus films.

---

## Grounding (verified at scope time — file:line)

- **No deal seed in the engine.** The only re-entry into a mid/opening state is
  `cg.api.search_begin(agent_observation, your_deck, your_prize, opponent_deck, opponent_prize,
  opponent_hand, opponent_active, manual_coin=False)` (`src/cg/api.py:517`). `manual_coin` is a
  bool controlling coin flips — there is **no shuffle/deal seed argument**. This is the whole reason
  duplicate-deal eval is a *spike*, not a given.
- **Contestant resolution already handles both sources.** `tools/sim/battle.py:368` `resolve(spec,
  rows, *, agents_root, out, into)` → a **build id** extracts `{artifact}.zip` from the Build Ledger
  (`:346`) under `into`; a **name** is the working-tree agent (`:376`), tagged `label:"working-tree"`
  with `_git_short()` provenance. `--builds` defaults to the Build Ledger (`:408`). Work Package 2's contestant
  set + checkpoint pool is a *use* of `resolve`, not new resolution code.
- **Paired-delta stats exist and are ON/OFF-shaped.** `tools/sim/paired_ab.py`: `matchup_delta(on_wins,
  on_n, off_wins, off_n)`, `paired_delta(matchups)` → `{delta, ci_lo, ci_hi, n_matchups}` (equal-weighted
  mean of per-matchup deltas, 95% CI), `flips_on(result, *, crashes, reg_tol=0.01)`. Semantics: per
  directed matchup **D@on vs fixed O − D@off vs O**, which subtracts out the raw deck matchup. NOTE:
  this is a **2-config (on/off) same-contestant** shape; a general candidate-vs-baseline-*agent* +
  checkpoint-pool matrix may need an extension (→ Q4).
- **Neutrality gate exists.** `tools/sim/score_diff.py` `capture`/`diff`, modes `scores`
  (per-option scores + choice identical) vs `choice` (chosen option identical), over corrections
  and replay films. This is the tool the Adoption Gate / D-neutrality invariants lean on — Work Package 2 reuses, doesn't rebuild.
- **Corpus films carry archetype per seat.** `tools/sim/corpus.py:234` `rec.replay(episode_id=eid,
  team_names=names)`; films `{index:06d}_{episode_id}.json.gz` (`:59`). So an eval run over corpus
  frames can stratify/label by true deck without re-deriving it — same fact Build Session 2a / Build Session 3b rely on.
- **C3 report format is FROZEN** ([contracts.md §C3](ml-training-contracts.md)): `report_version:1`,
  fields `baseline`/`candidate` `{agent,label,config}`, `matchups[{opponent,seat,n,candidate_wins,
  baseline_wins,draws}]`, `paired_delta{win_delta,ci_low,ci_high,method}`, `strata[{name,n,win_delta,
  ci_low,ci_high}]` (or `[]` if the spike didn't land), `checkpoints[{build_id,n,candidate_wins}]`,
  `aivat{variance_reduction,corrected_delta}|null`, `verdict pass|fail|inconclusive`. **The grill may
  NOT silently change these** — a removed/renamed field bumps `report_version` and is a contract amendment.

---

## The tension the grill must reconcile (frame first)

The local hard-won lesson — **"gauntlet invalid — ladder only"** (cross-deck gauntlet proves nothing
about *gain*; Kaggle ladder + user feedback are the only valid signal) — sits against the research
report's claim that the fix is **"gauntlet done right"** (finding 6 + eval-methodology: duplicate
deals + matchup/seat balancing + skill-sensitivity stratification + AIVAT ≈ 10× sample-efficiency).

These are not actually opposed — the local lesson killed *raw aggregate winrate*; the research
prescribes *stratified, variance-corrected, balanced* measurement as an offline **pre-filter**, with
ladder still the final arbiter (build plan already says "ladder stays the final arbiter"). **The grill's
job is to state precisely what Work Package 2 is allowed to certify** (regression screen? adoption pre-filter for
the Adoption Gate? nothing without a stratum hit?) so we never re-import the invalid-signal mistake. This framing
gates Q2/Q3 — a stratum that doesn't separate skill is the exact failure mode the local lesson names.

---

## Open questions to grill

### Q1 — Duplicate-deal fork-replay spike: does it hold, and what exactly is captured? *(the headline fork)*

The C3 `strata` field and AIVAT's power both hinge on replaying the **same deal** under both
contestants. Engine has no deal seed, so the only lever is `search_begin` re-entry.

- **Sub-forks the grill must settle:** (a) *What is captured* — a full opening state from a self-play
  film (both sides known: decks, prizes, hands, actives) is exactly `search_begin`'s argument list, so
  in principle re-enterable. But is a *pre-game* deal capturable, or only post-setup (setup coin +
  mulligans already resolved)? (b) *Does it hold for a whole game* or diverge after the first hidden
  draw/shuffle mid-game (search effects that reshuffle)? (c) `manual_coin=True` — does forcing coin
  outcomes make a deal deterministically replayable end-to-end, or only the first flip?
- **Timebox:** the build plan already bounds this at **~half a session**. The grill's output is a
  go/no-go criterion + the capture spec, not the implementation.
- **Seed (attack me):** expect fork-replay to hold from a **post-setup** captured state with
  `manual_coin` driving flips, but to **degrade on any mid-game reshuffle** — so scope duplicate-deal
  to *opening-state* variance reduction (the highest-variance phase) and accept divergence tolerance
  downstream. Fallback if even that fails → Q2's proxy path. *Why seeded this way:* it's the minimum
  that could still deliver the stratification win without pretending the engine is fully deterministic.

### Q2 — Skill-sensitivity stratification: cheating-agent gap vs proxy?

Research (ISMCTS deal-stratification): pre-classify deals by whether a **perfect-info cheating agent**
significantly beats the baseline — real algorithm differences show up only on the skill-sensitive
stratum; aggregate winrate masks them.

- **Fork:** (a) build a perfect-info "cheat" contestant (feasible — self-play controls both sides; a
  Pilot variant that reads the opponent's true hand/deck) and stratify by its gap vs baseline; vs
  (b) a cheap **proxy** — the seed value-model's P(win) swing across the game (build plan's fallback),
  no cheat agent needed.
- **Dependency:** (a) is far more valuable but only pays off if Q1's duplicate-deal replay lands (you
  need the *same* deal under cheat and baseline). If Q1 is no-go, (b) is the only option.
- **Seed:** gate on Q1 — **cheat-agent stratum if duplicate-deal holds, else value-swing proxy**, and
  in EITHER case emit the stratum into C3 `strata` so the Adoption Gate can read the skill-sensitive cell specifically
  (the local lesson says the *aggregate* cell is not trustworthy on its own).

### Q3 — AIVAT: how much now, how much stubbed until Work Package 1?

C3 has an `aivat{variance_reduction,corrected_delta}|null` field; build plan says **stub the
interface now, fill after Work Package 1** (the value net supplies the per-decision value estimates AIVAT needs;
research notes the synergy — decision-time values serve as AIVAT baselines "for free").

- **Fork:** define the plug-in interface precisely now (input = per-decision value estimates over the
  eval logs; output = corrected delta + variance-reduction ratio) and ship it returning `null` until a
  a Value-Net-Gate-passed net exists — vs defer the interface entirely.
- **Seed:** **define + stub the interface this session** (it's a contract other tracks read), wire the
  computation after the Value-Net Gate. Low cost now, avoids a second C3 touch later. Explicitly NOT required for the
  harness to be usable (build plan).

### Q4 — Contestant matrix + checkpoint pool: extend `paired_ab`, or new emitter?

C3's `baseline`/`candidate` are general `{agent,label,config}` descriptors and `checkpoints[]` is a
frozen-build opponent pool (the deferred Work Package 5 stand-in, catches regression + non-transitivity drift).
But `paired_ab.py` is a **2-config on/off** shape.

- **Fork:** (a) reuse `paired_ab` as-is by treating candidate/baseline as the two "configs" per fixed
  opponent (fits its subtraction model when candidate/baseline are the SAME deck with weights on/off —
  which is exactly the Adoption Gate use-case); vs (b) a new `eval*` emitter that generalizes to distinct
  contestant *agents* + an N-build checkpoint pool, with `paired_ab.paired_delta` reused only for the
  per-matchup CI math.
- **Seed:** **(b) new thin emitter, reusing `paired_delta` for the stats core.** The Adoption Gate primary
  comparison (weights on vs off, same deck) fits `paired_ab` directly, but the checkpoint pool +
  matchup×seat matrix is broader than on/off — build the emitter around the frozen C3 shape and call
  `paired_delta` per cell. Keeps `paired_ab` untouched (other consumers depend on it).

### Q5 — Sample size for our effect sizes *(research open question #1, made concrete)*

Research: Hearthstone bar was **45k matches/pairing raw**; AIVAT claims ~10× fewer for significance.

- **Fork:** what N (duplicate-dealt + stratified + AIVAT-corrected) detects a **2–3% winrate delta**
  at 95%? This sets the eval run's default `--n` and whether the Adoption Gate is affordable at ~1000 games/min.
- **Seed:** derive it in-session from `paired_delta`'s variance formula (`Σ var_i / k²`) under the
  stratified design — a computed number, not a guess. Record the target N + the wall-clock at
  1000 games/min so the Adoption Gate's cost is known before Build Session 3b lands.

---

## What "locked" looks like (grill exit criteria)

The grill is done when this doc can state, as `D#` decisions:

1. Fork-replay spike **go/no-go** + the exact capture spec (Q1) — and the C3 `strata` behavior in
   both branches.
2. The stratification method chosen (Q2) and what stratum the Adoption Gate is permitted to read.
3. The AIVAT interface signature + now-vs-after-Value-Net-Gate split (Q3).
4. The emitter shape + which existing stats code it reuses (Q4).
5. The default eval N + its wall-clock, tied to the Adoption Gate affordability check (Q5).
6. A one-paragraph **certification charter**: exactly what a Work Package 2 report is allowed to claim, closing
   the "gauntlet invalid vs gauntlet done right" tension so the Adoption Gate can't re-import the invalid signal.

## Non-goals (out of scope for the Build Session 2b grill)

- League / exploiter probe (Work Package 5, deferred until Work Package 4 ships checkpoints) — Work Package 2's checkpoint pool is the
  interim stand-in, not the league.
- The value net itself (Work Package 1 / Build Session 2a) and expert-iteration (Work Package 4 / Build Session 3b) — Build Session 2b measures them, doesn't build them.
- Touching `src/cg/` or any frozen C1/C2/C3 field without a contract amendment.
- Modifying `paired_ab.py` / `gauntlet_ab.py` / `battle.py` behavior — reuse only.
