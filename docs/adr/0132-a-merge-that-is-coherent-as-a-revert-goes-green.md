# ADR-0132 — A merge that is coherent as a revert goes green, and a retired id in a live string literal reads as live

**Status:** Accepted (2026-08-07); BUILT.
**Context:** PR #447 (POC-T4/5, Issue #386) silently reverted PR #432 (Issue #421, the Mega Lucario
mechanism census) on `main`. This ADR records the incident, the restoration, and the two invariants
that make each half of it detectable next time.

---

## 1. What happened

PR #432 merged at `9ee621db` (2026-08-07 09:51Z). PR #447 branched from `364f9598` — the merge
*before* it — and merged at `16abe37d` (17:16Z). Its first commit, `c68ad9e4`, carries
`9ee621db` as its parent and a **tree that predates it**: all eighteen files #432 touched come back
reverted in that one commit, `276 insertions(+), 2041 deletions(-)`.

Nine files landed byte-for-byte identical to their pre-#432 state — `src/common/board_delta.py`,
`src/common/snapshot_coverage.py`, `src/cgpy/chain.py`, `src/cgpy/defs/chain_overrides.json`,
`data/engine/coverage.json`, `src/common/CONTEXT.md`, `src/agents/mega_lucario/STRATEGY.md`,
`tests/parity/test_damage_goldens.py`, `tests/strategy/test_apply_transitions.py`. All five files
#432 *added* were deleted outright (1240 lines of Stadium and cgpy-state tests). The remaining four
were partially overwritten, which is where the visible damage was: in
`src/agents/mega_lucario/strategy.py` the three rungs #432 retired came back —
`aurajab-skip-partnerless-solrock`, `aurajab-load-the-wincon-line`, `gravity-mountain-vs-stage2` —
and the ~30-line measured record that retired them (Issues #425 / #424 / #442 / #443) was gone with
them.

**Nothing went red.** Not the suite, not either ADR-0072 gate, not review. A revert is internally
consistent by construction: it restores a tree that was green, together with the tests that agreed
with it. `test_mega_lucario_triggers.py`'s Gravity Mountain assertion came back at the same time as
the rung it asserts.

That the gates were silent is now measured rather than assumed. After the restoration both are
**byte-identical to what #447 shipped** — Discrimination 61 unruled / 50 ruled / 6 voided, Decision
44 / 28 / 2. So the restoration moves zero gated frames, and neither gate could have caught the
revert in either direction. Both baselines are untouched, per the standing rule that a baseline is a
ruling record.

### The mechanism, and what is inference

Provable from the history: the reverting change is confined to `c68ad9e4`; it covers **all eighteen**
of #432's files including new-file deletions; and the nine preceding merges into `main` (#445, #439,
#438, #437, #436, #434, #430, #419) are intact — checked file-by-file against each merge's own first
parent, `reverted=0 of N` for every one. So the blast radius is exactly one PR, and the shape is a
whole-tree replacement rather than a conflict mis-resolution: a rebase that fumbled a conflict would
touch conflicting hunks, not silently drop five added files.

Inferred, not proved: the tree came from an A/B measurement's restore step against the wrong base
SHA — `364f9598` where `9ee621db` was owed. POC-T4/5 ran several revert-measure-restore cycles over
`src/`, and the memory note *"stash-based attribution is unverified"* is about this exact hazard. The
distinction matters for §4: the fix that follows does not depend on the mechanism being right.

## 2. Decision — restore #432 on top of #447, not the reverse

Fourteen files restore cleanly from `9ee621db` (nothing on `main` had touched them since; #447's net
effect on each was the revert alone). Four take a three-way merge, and all four merged with a single
conflict in `tests/strategy/test_attach_decider.py` where both PRs appended a block — resolved by
keeping both, since they cover different seams.

The three retired rungs stay **retired**, which is the point of restoring rather than reverting:
their retirement was measured (70 Corrections replayed both arms, zero decisions moved, the rungs
observed firing in the shipped arm as the positive control), and #447 had no finding against it. It
un-retired them by accident.

`src/common/pilot.py` takes both changes: #447's rung-ladder deletion **and** #432's Stadium leg on
`_boost_lethal_tactical` plus `_stadium_hp_shift`. They are disjoint — one deletes positional rungs,
the other adds a KO-crossing term — and the merge is what makes that visible.

## 3. Decision — delete the two `_finish_turn_last` tiers, and record the loss

Restoring #432 exposed a second, independent defect in #447 that no revert of anything would fix.

`pilot._finish_turn_last` sequenced two things by matching a **rung ID in an inline string literal**:
a KO-enabling gust (`gust-for-the-ko`, `gust-for-the-loaded-equal-ko`) and the sacrificial-wall
retreat (`retreat-to-wall-the-line`). POC-T4/5 deleted all three rungs. Both branches have been
unreachable since that merge, and `baseline/__init__.py` went on asserting in prose that
*"`_finish_turn_last`'s tiers SURVIVE and are still where the ordering claim lives"* — false for
these two on the day it was written, and the sentence shipped inside the very fold record that
deleted their triggers.

Measured against the full 70-rung roster (57 general + 13 deck): all three ids dead, positive control
`attach-solrock-over-line-base` and 69 others live. A first probe read `pilot.strategy.hypotheses`
alone, saw 13 ids, and would have overstated every count in this ADR by a factor of five — recorded
because the instrument was wrong in the direction that *confirms* the finding, which is the direction
that gets believed.

Both branches are **deleted with the loss recorded at the site**, not re-expressed:

* The **gust** tier has nowhere to go. `CLAUSE_WRITES['gust']` is non-empty, so `_covers` refuses the
  transition (Issue #300) and the composer cannot price a gust either. Rung, tier and leaf are all
  silent on it — a total hole, already filed with its two corpus frames in `poc_t4_flips.py`.
* The **retreat** tier's claim *is* what the composer scores in-sequence, on the 63.4% of MAIN frames
  it decides (ADR-0131). On the rest the retreat falls to `_TIER_ENDER` with every other retreat: a
  narrowing, not a break. The maneuver's other half is untouched —
  `Board.can_wall_line_with_disruptor` still feeds the live `feed-the-line-for-disruptor-lock`.

Re-expressing either needs a measurement this merge has no standing to make.

## 4. Decision — the two invariants

### 4a. A rung id that production code matches on must be a rung some Strategy ships

`tests/strategy/test_rung_id_literals_are_live.py`. An AST walk over `src/` (excluding `src/cg/`)
collects every string literal compared against a Hypothesis `id` — `h.id == "x"`,
`getattr(h, "id", None) in (...)`, `!=`, `not in` — plus the two named frozensets whose membership
*is* the comparison, and asserts each names a live rung.

The walk is an AST walk and not a grep on purpose: a fold record naming a deleted rung in prose must
stay green, or the audit trail would have to be deleted to keep CI happy.

It found more than the two tiers. `planner._CLASS_B_SPEND_IDS` named **thirteen** rungs nothing ships
and `_ABILITY_FIRE_IDS` one, so ADR-0069's spend account was summing over a vocabulary two thirds of
which could not occur. Removing them is a provable no-op — an id no Strategy ships can never appear
in `OptionTrace.fired` — which is exactly why it went unnoticed for a whole PR cycle.

Two consequences worth naming, because both are the invariant paying for itself immediately:

* Cleaning the sets, I pruned `dont-rush-evolve-without-target`, which is **live** and whose
  membership `baseline_evolution.py` explicitly requires. The first version of this test could not
  catch that: *"no dead members"* is satisfied perfectly by an empty set. It now asserts the
  symmetric half too.
* `test_line_account_ignores_wrong_sign` was **vacuous**. Its spend leg named
  `dont-waste-discard-energy`, which is in neither the set nor the roster — so the id was ignored
  because the set never contained it, not because the sign filter dropped it, and the assertion would
  have passed against a `_line_account` with no sign test at all. Both legs now name real members,
  and the membership is asserted as the premise it is.

And the roster loader owes a note of its own, because its first version was green in isolation and
broke only under the full suite. It reached the deck strategies as `agents.<deck>.strategy`;
`kaggle_environments` ships a top-level `agents` module (`envs/lux_ai_s3/agents.py`), whichever
import lands first owns the name, and the loser gets `ImportError`. It also took a live-engine test
down with it — `test_planner_engine.py`'s composer smoke drives the `cg.dll` singleton and failed as
collateral, which is worth naming because that failure looked like a decider regression and was not.
`train.tune._build_pilot` had already solved this with `importlib.util.spec_from_file_location`; the
loader now uses the same idiom, so there is one way to load a deck strategy rather than two.
Attribution is empirical, not argued: with the loader fixed the full suite is **5442 passed, 0
failed**, and both tests come back on their own.

### 4b. Prose about what survives a deletion is a claim, and claims get checked

The false *"the tiers SURVIVE"* sentence is corrected in place rather than quietly rewritten, with
the reason it was invisible attached, because that is the fold record `tools/train/reviewed_audit.py`
reads. `gust-for-the-loaded-equal-ko` is added to the map, which had omitted it entirely.

## 5. What is NOT decided here

* **Whether either deleted tier should be rebuilt.** Both are ordering claims a state function cannot
  express (ADR-0131's own consequence), so the composer is not automatically their new home. That is
  a scoring call needing corpus measurement.
* **Why `c68ad9e4` carried a stale tree.** §1 marks the A/B-restore explanation as inference. The
  invariants in §4 do not depend on it, and neither does the restoration.
* **A CI guard against silent reverts as a class.** The file-by-file scan in §1 (for each merge, does
  `main` still differ from that merge's first parent?) is cheap and mechanical, and would have caught
  this within one push. It is not built here; the two invariants above address the *consequences* that
  reached shipped behaviour, not the merge hygiene that let them in.
